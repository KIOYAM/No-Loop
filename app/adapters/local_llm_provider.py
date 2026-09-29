"""Universal OpenAI-compatible LLM provider (Tier 3 "local"/BYOK-any).

Design (user requirement 2026-09-29): the provider is configured by **a path
or URL + a model name**, so *any* LLM the user already has on disk can be used
without code changes.

Works against every server that speaks the OpenAI ``/v1/chat/completions``
dialect — Ollama, llama.cpp server, LM Studio, vLLM, text-generation-webui,
llama-cpp-python, Exllama, LocalAI … :

* ``endpoint = "http://127.0.0.1:11434"``            → ``…/v1`` (Ollama)
* ``endpoint = "http://localhost:1234/v1"``           → unchanged (LM Studio)
* ``endpoint = "D:\\models\\Qwen3-4B-Q4_K_M.gguf"``  → a *file path*; the
  provider then expects a server on the llama.cpp default port (see
  ``DEFAULT_LOCAL_BASE``) and reports a clear, actionable probe error if the
  server is not running. No_Loop never installs or launches runtimes itself
  (binding principle: no mandatory paid service / no forced install).

Security note: ``safe_get`` (app.adapters.fetcher) blocks loopback because it
guards *untrusted external* content. This adapter talks to a **user-configured
local** endpoint over plain HTTP — by definition loopback/private. It still
enforces: http(s) only, a response size cap, a bounded timeout, and the URL
never appears in a query string (so keys cannot leak into logs).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from app.adapters.fetcher import MAX_RESPONSE_BYTES
from app.domain.errors import ProviderUnavailableError
from app.ports import GenerationRequest, GenerationResult

__all__ = ["LocalLLMProvider", "normalize_endpoint", "DEFAULT_LOCAL_BASE", "LOCAL_PRESETS"]

DEFAULT_LOCAL_BASE = "http://127.0.0.1:8080/v1"
_TIMEOUT_S = 45.0
_PROBE_TIMEOUT_S = 4.0
_MAX_OUTPUT_CHARS = 8000
_VERSION_SEGMENT = re.compile(r"v\d+(?:\.\d+)?")

#: Display-only hints for the Settings UI (never executed, never installed).
LOCAL_PRESETS: tuple[dict[str, str], ...] = (
    {"key": "llamacpp", "label": "llama.cpp server", "endpoint": "http://127.0.0.1:8080"},
    {"key": "ollama", "label": "Ollama", "endpoint": "http://127.0.0.1:11434"},
    {"key": "lmstudio", "label": "LM Studio", "endpoint": "http://localhost:1234/v1"},
    {"key": "vllm", "label": "vLLM / TGI", "endpoint": "http://127.0.0.1:8000/v1"},
)


def normalize_endpoint(endpoint: str) -> tuple[str, str | None]:
    """Resolve the user's *path or URL* into ``(openai_base_url, model_path)``.

    ``model_path`` is non-None only when the value points at a file/directory on
    disk (a ``.gguf`` or a model folder) — kept so the UI can show what the
    configured path holds and validate that it still exists.
    """
    raw = (endpoint or "").strip()
    if not raw:
        return DEFAULT_LOCAL_BASE, None

    if raw.lower().startswith(("http://", "https://")):
        url = raw.rstrip("/")
        for suffix in ("/chat/completions", "/completions", "/models"):
            if url.lower().endswith(suffix):
                url = url[: -len(suffix)]
        parsed = urlparse(url)
        segments = [s for s in parsed.path.split("/") if s]
        if any(_VERSION_SEGMENT.match(seg) for seg in segments):
            return urlunparse(parsed._replace(path=parsed.path.rstrip("/"))), None
        return urlunparse(parsed._replace(path=parsed.path.rstrip("/") + "/v1")), None

    # Not a URL => a filesystem path to an LLM (file or folder).
    return DEFAULT_LOCAL_BASE, raw


class LocalLLMProvider:
    """OpenAI-compatible chat-completions client (sync ``generate`` + async)."""

    def __init__(
        self,
        endpoint: str = "",
        model: str = "",
        *,
        api_key: str | None = None,
        timeout_s: float = _TIMEOUT_S,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url, self.model_path = normalize_endpoint(endpoint)
        self.model = (model or "").strip()
        self._api_key = (api_key or "").strip() or None
        self._timeout_s = timeout_s
        self._transport = transport
        label = self.model or (Path(self.model_path).stem if self.model_path else "model")
        self.name = f"local:{label}"

    # -- contract ---------------------------------------------------------

    def available(self) -> bool:
        return bool(self.model)

    def privacy_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sends_data_off_device": False,
            "data_categories": ["prompt text sent to the configured endpoint only"],
            "destination": self.base_url,
            "retention": "depends on the local runtime; nothing stored by No_Loop",
            "never_sent": ["your API keys", "other profiles' data", "the resume file itself"],
        }

    def estimate_cost(self, request: GenerationRequest) -> dict[str, Any]:
        approx_tokens = (
            len(request.facts_payload) + len(request.job_payload) + len(request.instructions)
        ) // 4
        return {
            "provider": self.name,
            "approx_input_tokens": approx_tokens,
            "tier": "local-free",
            "money": 0.0,
        }

    # -- HTTP -------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def chat_async(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        json_mode: bool = False,
        timeout_s: float | None = None,
    ) -> str:
        """One round-trip completion. Raises ProviderUnavailableError (honest)."""
        if not self.base_url:
            raise ProviderUnavailableError(
                stage="ai.chat", reason="no local endpoint configured (Settings → AI)"
            )
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": self.model or "default",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self.base_url}/chat/completions"
        text = await self._post(url, payload, timeout_s=timeout_s, json_mode=json_mode)
        if text is None and json_mode:
            # Many local servers reject response_format (400/422) — retry once, plainly.
            payload.pop("response_format", None)
            text = await self._post(url, payload, timeout_s=timeout_s)
        if not text or not text.strip():
            raise ProviderUnavailableError(
                stage="ai.chat", reason="local model returned empty text"
            )
        return text[:_MAX_OUTPUT_CHARS]

    async def _post(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        timeout_s: float | None,
        json_mode: bool = False,
    ) -> str | None:
        try:
            async with httpx.AsyncClient(
                timeout=timeout_s or self._timeout_s,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(url, json=payload, headers=self._headers())
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                stage="ai.chat",
                reason=(
                    f"local endpoint unreachable ({exc.__class__.__name__}) at {self.base_url} "
                    "— start your LLM server or fix the path in Settings → AI"
                ),
                retryable=True,
                user_action="Settings → AI → local model → Test connection.",
            ) from exc

        if response.status_code in (401, 403):
            raise ProviderUnavailableError(
                stage="ai.chat",
                reason="local endpoint rejected the key (401/403)",
                user_action="Clear or correct the local API key in Settings → AI.",
            )
        if json_mode and response.status_code in (400, 404, 422):
            return None  # endpoint shape unknown; caller retries without response_format
        if response.status_code >= 400:
            raise ProviderUnavailableError(
                stage="ai.chat",
                reason=f"local endpoint HTTP {response.status_code}: {response.text[:160]}",
                retryable=response.status_code in (429, 500, 502, 503),
            )
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ProviderUnavailableError(stage="ai.chat", reason="response exceeds size cap")
        try:
            data = response.json()
            choices = data.get("choices") or []
            message = choices[0].get("message", {}) if choices else {}
            content = message.get("content")
            if isinstance(content, list):  # some servers return parts
                content = "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
            return str(content) if content is not None else None
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError(
                stage="ai.chat",
                reason=f"malformed local response: {exc.__class__.__name__}",
            ) from exc

    async def probe_async(self) -> dict[str, Any]:
        """Health check used by the Settings UI (no secrets in the payload)."""
        started = time.perf_counter()
        url = f"{self.base_url}/models"
        try:
            async with httpx.AsyncClient(
                timeout=_PROBE_TIMEOUT_S, transport=self._transport, follow_redirects=False
            ) as client:
                response = await client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            return {
                "reachable": False,
                "endpoint": self.base_url,
                "model": self.model,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "error": f"{exc.__class__.__name__}: start your LLM server, then Test again.",
                "models": [],
            }
        latency = round((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            return {
                "reachable": False,
                "endpoint": self.base_url,
                "model": self.model,
                "latency_ms": latency,
                "error": f"HTTP {response.status_code} from {url}",
                "models": [],
            }
        models: list[str] = []
        try:
            for item in response.json().get("data") or []:
                mid = item.get("id")
                if isinstance(mid, str):
                    models.append(mid)
        except (ValueError, AttributeError, TypeError):
            models = []
        return {
            "reachable": True,
            "endpoint": self.base_url,
            "model": self.model,
            "latency_ms": latency,
            "error": None,
            "models": models,
            "model_configured": self.model in models if models else bool(self.model),
        }

    # -- sync convenience (AIProvider protocol parity) ---------------------

    def generate(self, request: GenerationRequest) -> GenerationResult:
        import asyncio

        prompt = (
            f"{request.instructions}\n\n"
            f"CONFIRMED PROFILE FACTS (use ONLY these; do not invent):\n"
            f"{request.facts_payload}\n\n"
            f"TARGET JOB:\n{request.job_payload}\n\n"
            f"Maximum length: {request.max_chars} characters."
        )
        text = asyncio.run(self.chat_async(prompt, max_tokens=min(4096, request.max_chars)))
        return GenerationResult(text=text, provider=self.name)
