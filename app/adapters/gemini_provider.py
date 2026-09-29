"""Gemini BYOK provider (Tier 2; MASTER_SPEC §12; user decision: Gemini first).

Key facts honored from docs (R-TRUTH-4, verified 2026-09-28):
- REST endpoint: POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
- Header: ``x-goog-api-key: <key>`` (preferred over ?key= query param so the
  key never appears in URLs/logs)
- Response: candidates[0].content.parts[*].text
- Sourced from Google's public API docs; re-verify at LOOP-12.

Privacy (R-SEC-3): the privacy panel data below is shown BEFORE activation;
payloads contain ONLY the fact slices the caller passes — never the full
resume. Key never appears in URLs and never in logs (keyring/file backend).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.adapters.fetcher import MAX_RESPONSE_BYTES
from app.domain.errors import ProviderUnavailableError
from app.ports import GenerationRequest, GenerationResult

__all__ = ["GeminiProvider", "GEMINI_MODELS", "DEFAULT_MODEL"]

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_TIMEOUT_S = 30.0
_MAX_OUTPUT_CHARS = 8000

GEMINI_MODELS = ("gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash")
DEFAULT_MODEL = GEMINI_MODELS[0]


class GeminiProvider:
    """BYOK adapter. Constructed with a user key from the settings store."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = _TIMEOUT_S,
    ) -> None:
        self.name = f"gemini:{model}"
        self._api_key = api_key
        self._model = model
        self._transport = transport  # injectable for tests (httpx.MockTransport)
        self._timeout_s = timeout_s

    def available(self) -> bool:
        return bool(self._api_key)

    def privacy_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sends_data_off_device": True,
            "destination": "Google Generative Language API (generativelanguage.googleapis.com)",
            "data_categories": [
                "selected confirmed profile facts",
                "target job title/company/requirements",
            ],
            "never_sent": [
                "full resume file",
                "contact details",
                "other profiles' data",
                "credentials",
            ],
            "retention": "governed by Google's terms; user reviews at activation",
            "key_storage": (
                "OS credential store (keyring) or local secrets file — never in URLs/logs"
            ),
        }

    def estimate_cost(self, request: GenerationRequest) -> dict[str, Any]:
        # Rough char-based estimate; flash models are extremely cheap at this scale.
        approx_tokens = (
            len(request.facts_payload) + len(request.job_payload) + len(request.instructions)
        ) // 4
        return {
            "provider": self.name,
            "approx_input_tokens": approx_tokens,
            "tier": "BYOK-user-account",
        }

    async def generate_async(self, request: GenerationRequest) -> GenerationResult:
        text = await self.complete_async(
            f"{request.instructions}\n\n"
            f"CONFIRMED PROFILE FACTS (use ONLY these; do not invent):\n"
            f"{request.facts_payload}\n\n"
            f"TARGET JOB:\n{request.job_payload}\n\n"
            f"Maximum length: {request.max_chars} characters.",
            max_tokens=min(4096, request.max_chars // 2 + 256),
        )
        return GenerationResult(text=text, provider=self.name)

    async def complete_async(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        json_mode: bool = False,
        timeout_s: float | None = None,
    ) -> str:
        """Raw one-shot completion — symmetric with LocalLLMProvider.chat_async.

        This is the fast resume-parsing path: ONE request, small output budget,
        temperature 0 and (optionally) a strict JSON response mime type.
        """
        if not self._api_key:
            raise ProviderUnavailableError(stage="ai.chat", reason="no API key configured")
        payload: dict[str, Any] = {"contents": [{"parts": [{"text": prompt}]}]}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        config: dict[str, Any] = {"maxOutputTokens": max_tokens, "temperature": temperature}
        if json_mode:
            config["responseMimeType"] = "application/json"
        payload["generationConfig"] = config
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        url = _ENDPOINT.format(model=self._model)
        try:
            async with httpx.AsyncClient(
                timeout=timeout_s or self._timeout_s,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                stage="ai.chat",
                reason=f"network error: {exc.__class__.__name__}",
                retryable=True,
            ) from exc
        if response.status_code in (401, 403):
            raise ProviderUnavailableError(
                stage="ai.chat",
                reason="API key rejected (401/403): check the key in Settings",
                user_action="Settings → AI provider → re-enter a valid key.",
            )
        if response.status_code == 429:
            raise ProviderUnavailableError(
                stage="ai.chat", reason="rate limited (429) — try again later", retryable=True
            )
        if response.status_code >= 400:
            raise ProviderUnavailableError(
                stage="ai.chat", reason=f"provider HTTP {response.status_code}", retryable=False
            )
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ProviderUnavailableError(stage="ai.chat", reason="response exceeds size cap")
        try:
            data = response.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(str(part.get("text", "")) for part in parts)[:_MAX_OUTPUT_CHARS]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError(
                stage="ai.chat", reason=f"malformed provider response: {exc.__class__.__name__}"
            ) from exc
        if not text.strip():
            raise ProviderUnavailableError(stage="ai.chat", reason="provider returned empty text")
        return text
