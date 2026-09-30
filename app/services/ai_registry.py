"""AI provider registry — resolves *which* model answers, from user settings.

Tier ladder (MASTER_SPEC §12 / binding principle 5, unchanged):

    Tier 0  no-ai        deterministic, zero keys — always available
    Tier 1  rule-based   templates over confirmed facts — always available
    Tier 2  gemini       BYOK cloud key (Gemini first, user decision)
    Tier 3  local        any OpenAI-compatible server, path + model name

The user picks ``auto`` (default) or pins one explicitly. Resolution order for
``auto``: configured Gemini key → configured local model → rule-based. Nothing
is ever *required*; every tier degrades visibly and honestly.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.adapters.ai_providers import NoAIProvider, RuleBasedProvider
from app.adapters.local_llm_provider import LOCAL_PRESETS, LocalLLMProvider
from app.adapters.settings_store import SettingsStore

__all__ = ["AIConfig", "AIRegistry", "PROVIDER_CHOICES"]

PROVIDER_CHOICES = ("auto", "gemini", "local", "rule")

# Google retires model IDs without notice: gemini-2.0-flash and
# gemini-1.5-flash now 404 for every key, so the old default made a working
# key look broken. Every id below was called against the live API with this
# app's own smoke-test prompt before being offered here.
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
_GEMINI_CHOICES = ("gemini-2.5-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash")


@dataclass
class AIConfig:
    """Non-secret AI settings (persisted through SettingsStore.set)."""

    provider: str = "auto"
    gemini_model: str = DEFAULT_GEMINI_MODEL
    local_endpoint: str = ""
    local_model: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, settings: SettingsStore) -> AIConfig:
        raw_provider = str(settings.get("ai_provider", "auto") or "auto")
        model = str(settings.get("gemini_model", DEFAULT_GEMINI_MODEL) or "")
        if model not in _GEMINI_CHOICES:
            # The model field is a closed <select>, so a value outside the list
            # can only be a retired id we used to offer — Google 404s those.
            # Correct it once (this write stops happening on later loads)
            # instead of leaving every request failing against a dead model.
            model = DEFAULT_GEMINI_MODEL
            settings.set("gemini_model", model)
        return cls(
            provider=raw_provider if raw_provider in PROVIDER_CHOICES else "auto",
            gemini_model=model,
            local_endpoint=str(settings.get("local_llm_endpoint", "") or ""),
            local_model=str(settings.get("local_llm_model", "") or ""),
        )

    def save(self, settings: SettingsStore) -> None:
        settings.set("ai_provider", self.provider)
        settings.set("gemini_model", self.gemini_model)
        settings.set("local_llm_endpoint", self.local_endpoint)
        settings.set("local_llm_model", self.local_model)


class AIRegistry:
    """Facade the UI talks to (settings + provider construction + smoke test)."""

    def __init__(self, settings: SettingsStore) -> None:
        self.settings = settings

    # -- configuration ----------------------------------------------------

    def config(self) -> AIConfig:
        return AIConfig.load(self.settings)

    def save_config(self, payload: dict[str, Any]) -> AIConfig:
        """Validate + persist the AI settings page (secrets handled separately)."""
        cfg = self.config()
        provider = str(payload.get("provider", cfg.provider) or "auto")
        if provider not in PROVIDER_CHOICES:
            raise ValueError(f"provider must be one of {PROVIDER_CHOICES}")
        cfg.provider = provider
        if "gemini_model" in payload:
            model = str(payload["gemini_model"]).strip()
            if model:
                cfg.gemini_model = model
        if "local_endpoint" in payload:
            cfg.local_endpoint = str(payload["local_endpoint"]).strip()
        if "local_model" in payload:
            cfg.local_model = str(payload["local_model"]).strip()
        cfg.save(self.settings)

        # Write-only secrets: only stored when the browser actually sent one.
        key = str(payload.get("gemini_api_key") or "").strip()
        if key:
            self.settings.set_secret("gemini_api_key", key)
        local_key = str(payload.get("local_llm_api_key") or "").strip()
        if local_key:
            self.settings.set_secret("local_llm_api_key", local_key)
        if payload.get("clear_gemini_key"):
            self.settings.delete_secret("gemini_api_key")
        if payload.get("clear_local_key"):
            self.settings.delete_secret("local_llm_api_key")
        return cfg

    # -- providers --------------------------------------------------------

    def gemini(self) -> Any:
        from app.adapters.gemini_provider import GeminiProvider

        return GeminiProvider(
            api_key=self.settings.get_secret("gemini_api_key") or "",
            model=self.config().gemini_model or DEFAULT_GEMINI_MODEL,
        )

    def local(self) -> LocalLLMProvider:
        cfg = self.config()
        return LocalLLMProvider(
            cfg.local_endpoint,
            cfg.local_model,
            api_key=self.settings.get_secret("local_llm_api_key"),
        )

    def resolve(self) -> Any:
        """The provider that will actually answer right now (never raises)."""
        cfg = self.config()
        if cfg.provider == "gemini":
            return self.gemini() if self.gemini().available() else NoAIProvider()
        if cfg.provider == "local":
            return self.local() if self.local().available() else NoAIProvider()
        if cfg.provider == "rule":
            return RuleBasedProvider()
        # auto
        gemini = self.gemini()
        if gemini.available():
            return gemini
        local = self.local()
        if local.available():
            return local
        return RuleBasedProvider()

    def active_key(self) -> str:
        """Short label for the UI ('gemini', 'local', 'rule', 'none')."""
        provider = self.resolve()
        name = getattr(provider, "name", "")
        if name.startswith("gemini"):
            return "gemini"
        if name.startswith("local:"):
            return "local"
        if name == "rule-based":
            return "rule"
        return "none"

    # -- reporting --------------------------------------------------------

    def status(self) -> dict[str, Any]:
        cfg = self.config()
        gemini = self.gemini()
        local = self.local()
        gemini_backend = self.settings.secret_backend("gemini_api_key")
        local_backend = self.settings.secret_backend("local_llm_api_key")
        return {
            "provider_choices": list(PROVIDER_CHOICES),
            "gemini_models": list(_GEMINI_CHOICES),
            "presets": [dict(p) for p in LOCAL_PRESETS],
            "config": asdict(cfg),
            "active": self.active_key(),
            "providers": {
                "gemini": {
                    "label": "Google Gemini (cloud, bring your own key)",
                    "configured": gemini.available(),
                    "key_backend": gemini_backend,
                    "model": cfg.gemini_model,
                    "privacy": gemini.privacy_info(),
                },
                "local": {
                    "label": "Local / OpenAI-compatible server",
                    "configured": local.available(),
                    "key_backend": local_backend,
                    "endpoint": local.base_url,
                    "model": cfg.local_model,
                    "path": local.model_path,
                    "path_exists": (
                        local.model_path is not None and _path_exists(local.model_path)
                    ),
                    "privacy": local.privacy_info(),
                },
                "rule": {
                    "label": "Rule-based (no AI, zero keys)",
                    "configured": True,
                    "key_backend": "none",
                    "privacy": RuleBasedProvider().privacy_info(),
                },
            },
        }

    async def test_async(self) -> dict[str, Any]:
        """Round-trip smoke test of the *resolved* provider (honest errors)."""
        provider = self.resolve()
        name = getattr(provider, "name", "unknown")
        # Local models expose chat_async, Gemini exposes complete_async. Only
        # testing for the former made a *configured* Gemini key report "No
        # provider configured; using deterministic fallback" while never
        # contacting Google — so a green tick meant nothing at all.
        method = getattr(provider, "chat_async", None) or getattr(
            provider, "complete_async", None
        )
        if method is None:
            return {
                "ok": provider.available(),
                "provider": name,
                "latency_ms": 0,
                "message": (
                    "Rule-based provider: no network call needed — always available."
                    if name == "rule-based"
                    else "No provider configured; using deterministic fallback."
                ),
            }
        started = time.perf_counter()
        try:
            text = await method(
                "Reply with exactly: OK",
                system="You are a connectivity check.",
                max_tokens=8,
                temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the user
            return {
                "ok": False,
                "provider": name,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "message": str(exc),
            }
        return {
            "ok": True,
            "provider": name,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "message": f"responded: {text.strip()[:80]}",
        }

    async def probe_local_async(self) -> dict[str, Any]:
        return await self.local().probe_async()

    async def complete_async(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        json_mode: bool = False,
        timeout_s: float | None = None,
    ) -> tuple[str, str]:
        """Uniform one-shot completion over the resolved provider.

        Returns ``(text, provider_label)``. Raises ProviderUnavailableError when
        no AI tier can answer — callers must degrade visibly, never silently.
        """
        from app.domain.errors import ProviderUnavailableError

        provider = self.resolve()
        method = getattr(provider, "chat_async", None) or getattr(provider, "complete_async", None)
        if method is None:
            raise ProviderUnavailableError(
                stage="ai.chat",
                reason="no AI provider configured (rule-based tier produces no new text)",
                user_action="Settings → AI → add a Gemini key or point at a local model.",
            )
        text = await method(
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=json_mode,
            timeout_s=timeout_s,
        )
        return text, str(getattr(provider, "name", "unknown"))


def _path_exists(path: str | None) -> bool:
    if not path:
        return False
    try:
        return Path(path).exists()
    except OSError:  # pragma: no cover - invalid path characters
        return False
