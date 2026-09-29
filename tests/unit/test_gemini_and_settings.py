"""Unit tests: settings store (secrets) + Gemini BYOK provider (mock transport)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.adapters.gemini_provider import GeminiProvider
from app.adapters.settings_store import SettingsStore
from app.domain.errors import ProviderUnavailableError
from app.ports import GenerationRequest


class TestSettingsStore:
    def test_secret_never_in_settings_file(self, tmp_path: Any) -> None:
        store = SettingsStore(tmp_path)
        store.set_secret("gemini_api_key", "AIza-secret-value")
        settings_text = (tmp_path / "settings.json").read_text(encoding="utf-8")
        assert "AIza-secret-value" not in settings_text  # value never in settings
        assert store.get("gemini_api_key__backend") in ("file", "keyring")

    def test_secret_roundtrip_file_backend(self, tmp_path: Any) -> None:
        store = SettingsStore(tmp_path)
        store.set_secret("gemini_api_key", "key-123")
        assert store.get_secret("gemini_api_key") == "key-123"
        assert store.secret_backend("gemini_api_key") == "file"

    def test_delete_secret(self, tmp_path: Any) -> None:
        store = SettingsStore(tmp_path)
        store.set_secret("gemini_api_key", "key-123")
        store.delete_secret("gemini_api_key")
        assert store.get_secret("gemini_api_key") is None

    def test_rejects_unknown_and_empty_secrets(self, tmp_path: Any) -> None:
        store = SettingsStore(tmp_path)
        with pytest.raises(ValueError, match="unknown secret"):
            store.set_secret("not_a_key", "x")
        with pytest.raises(ValueError, match="empty"):
            store.set_secret("gemini_api_key", "  ")

    def test_plain_settings_reject_secret_keys(self, tmp_path: Any) -> None:
        store = SettingsStore(tmp_path)
        with pytest.raises(ValueError, match="set_secret"):
            store.set("gemini_api_key", "leak")

    def test_secrets_file_is_gitignored_name(self, tmp_path: Any) -> None:
        # fallback backend writes to secrets.json which root .gitignore covers
        store = SettingsStore(tmp_path)
        store.set_secret("gemini_api_key", "k")
        assert (tmp_path / "secrets.json").exists()


_OK_RESPONSE = {"candidates": [{"content": {"parts": [{"text": "Generated draft text"}]}}]}


class TestGeminiProvider:
    def _provider(self, handler: Any) -> GeminiProvider:
        transport = httpx.MockTransport(handler)
        return GeminiProvider("test-key-123", transport=transport)

    async def test_generate_success(self) -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["key_header"] = request.headers.get("x-goog-api-key")
            captured["body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_OK_RESPONSE)

        provider = self._provider(handler)
        request = GenerationRequest(
            task="email_draft",
            instructions="write",
            facts_payload="skills=Python",
            job_payload="title=Dev",
            max_chars=2000,
        )
        result = await provider.generate_async(request)
        assert result.text == "Generated draft text"
        assert "gemini" in result.provider
        # key in header, never in URL
        assert captured["key_header"] == "test-key-123"
        assert "test-key-123" not in captured["url"]
        # payload contains facts + job, not the key
        body_text = json.dumps(captured["body"])
        assert "test-key-123" not in body_text
        assert "skills=Python" in body_text

    async def test_invalid_key_raises_actionable_error(self) -> None:
        provider = self._provider(lambda request: httpx.Response(403, json={"error": {}}))
        request = GenerationRequest("t", "i", "f", "j")
        with pytest.raises(ProviderUnavailableError, match="check the key"):
            await provider.generate_async(request)

    async def test_rate_limit_is_retryable(self) -> None:
        provider = self._provider(lambda request: httpx.Response(429, json={}))
        with pytest.raises(ProviderUnavailableError, match="rate limited"):
            await provider.generate_async(GenerationRequest("t", "i", "f", "j"))

    async def test_malformed_response_mapped(self) -> None:
        provider = self._provider(lambda request: httpx.Response(200, json={"weird": True}))
        with pytest.raises(ProviderUnavailableError, match="malformed"):
            await provider.generate_async(GenerationRequest("t", "i", "f", "j"))

    async def test_no_key_fails_fast(self) -> None:
        provider = GeminiProvider("", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
        assert provider.available() is False
        with pytest.raises(ProviderUnavailableError, match="no API key"):
            await provider.generate_async(GenerationRequest("t", "i", "f", "j"))

    def test_privacy_info_discloses_destination_and_never_sent(self) -> None:
        provider = GeminiProvider("k")
        info = provider.privacy_info()
        assert info["sends_data_off_device"] is True
        assert "generativelanguage.googleapis.com" in info["destination"]
        assert "full resume file" in info["never_sent"]
