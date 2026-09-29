"""Unit tests: universal OpenAI-compatible local LLM provider (mock transport).

Covers the "path or URL + model name" contract (any LLM already on disk works
without code changes) plus the honesty rules: an unreachable endpoint is a
reported failure with an action, never a hang or a fabricated answer.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.adapters.local_llm_provider import (
    DEFAULT_LOCAL_BASE,
    LocalLLMProvider,
    normalize_endpoint,
)
from app.domain.errors import ProviderUnavailableError
from app.ports import GenerationRequest

_OK = {"choices": [{"message": {"content": "Hello from the local model"}}]}


def _provider(
    handler: Any, endpoint: str = "http://127.0.0.1:8080/v1", **kw: Any
) -> LocalLLMProvider:
    return LocalLLMProvider(
        endpoint, kw.pop("model", "qwen2.5-3b"), transport=httpx.MockTransport(handler), **kw
    )


class TestNormalizeEndpoint:
    """The endpoint field accepts a URL *or* a file/folder on disk."""

    def test_empty_falls_back_to_default_base(self) -> None:
        assert normalize_endpoint("") == (DEFAULT_LOCAL_BASE, None)
        assert normalize_endpoint("   ") == (DEFAULT_LOCAL_BASE, None)

    def test_bare_host_gains_version_segment(self) -> None:
        # Ollama-style base without /v1
        assert normalize_endpoint("http://127.0.0.1:11434") == ("http://127.0.0.1:11434/v1", None)

    def test_existing_version_segment_kept(self) -> None:
        assert normalize_endpoint("http://localhost:1234/v1") == ("http://localhost:1234/v1", None)

    def test_trailing_slash_tolerated(self) -> None:
        assert normalize_endpoint("http://127.0.0.1:8080/v1/") == ("http://127.0.0.1:8080/v1", None)

    def test_chat_completions_suffix_stripped(self) -> None:
        # pasting the full path from a client config must not double it up
        assert normalize_endpoint("http://127.0.0.1:8080/v1/chat/completions") == (
            "http://127.0.0.1:8080/v1",
            None,
        )

    def test_gguf_file_becomes_a_model_path(self) -> None:
        base, path = normalize_endpoint(r"D:\models\Qwen3-4B-Q4_K_M.gguf")
        assert base == DEFAULT_LOCAL_BASE
        assert path == r"D:\models\Qwen3-4B-Q4_K_M.gguf"

    def test_model_directory_accepted(self) -> None:
        base, path = normalize_endpoint("D:/models/my-model-folder")
        assert (base, path) == (DEFAULT_LOCAL_BASE, "D:/models/my-model-folder")


class TestProviderContract:
    def test_unavailable_without_a_model_name(self) -> None:
        assert LocalLLMProvider("http://127.0.0.1:8080/v1", "").available() is False

    def test_available_once_a_model_is_named(self) -> None:
        assert LocalLLMProvider("", "qwen2.5-3b").available() is True

    def test_privacy_stays_on_device(self) -> None:
        info = LocalLLMProvider("http://127.0.0.1:8080/v1", "m").privacy_info()
        assert info["sends_data_off_device"] is False
        assert info["destination"] == "http://127.0.0.1:8080/v1"
        assert "your API keys" in info["never_sent"]
        assert "the resume file itself" in info["never_sent"]

    def test_local_generation_costs_no_money(self) -> None:
        cost = LocalLLMProvider("", "m").estimate_cost(GenerationRequest("t", "i", "f", "j"))
        assert cost["money"] == 0.0
        assert cost["tier"] == "local-free"

    def test_name_identifies_the_model(self) -> None:
        assert LocalLLMProvider("", "qwen2.5-3b").name == "local:qwen2.5-3b"


class TestChat:
    async def test_success_returns_message_content(self) -> None:
        provider = _provider(lambda request: httpx.Response(200, json=_OK))
        assert await provider.chat_async("hi") == "Hello from the local model"

    async def test_posts_to_chat_completions_under_the_base_url(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_OK)

        # bare Ollama-style host: /v1 must be inserted exactly once
        provider = _provider(handler, endpoint="http://127.0.0.1:11434")
        await provider.chat_async("hi", system="be terse")
        assert seen["url"] == "http://127.0.0.1:11434/v1/chat/completions"
        assert seen["body"]["model"] == "qwen2.5-3b"
        assert seen["body"]["messages"][0] == {"role": "system", "content": "be terse"}
        assert seen["body"]["temperature"] == 0.2

    async def test_api_key_is_a_header_and_never_a_query_param(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("authorization")
            seen["url"] = str(request.url)
            return httpx.Response(200, json=_OK)

        provider = _provider(handler, api_key="sekret-value")
        await provider.chat_async("hi")
        assert seen["auth"] == "Bearer sekret-value"
        assert "sekret-value" not in seen["url"]  # keys must not reach logs

    async def test_no_authorization_header_when_key_is_absent(self) -> None:
        seen: dict[str, str | None] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json=_OK)

        await _provider(handler).chat_async("hi")
        assert seen["auth"] is None

    async def test_json_mode_is_retried_plain_when_rejected(self) -> None:
        # many local servers do not implement response_format
        bodies: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            bodies.append(body)
            if "response_format" in body:
                return httpx.Response(400, json={"error": "unsupported"})
            return httpx.Response(200, json=_OK)

        text = await _provider(handler).chat_async("hi", json_mode=True)
        assert text == "Hello from the local model"
        assert len(bodies) == 2
        assert bodies[0]["response_format"] == {"type": "json_object"}
        assert "response_format" not in bodies[1]

    async def test_unauthorized_is_reported_with_the_status(self) -> None:
        provider = _provider(lambda request: httpx.Response(401, json={}))
        with pytest.raises(ProviderUnavailableError, match="401"):
            await provider.chat_async("hi")

    async def test_server_error_names_the_status(self) -> None:
        provider = _provider(lambda request: httpx.Response(500, text="boom"))
        with pytest.raises(ProviderUnavailableError, match="HTTP 500"):
            await provider.chat_async("hi")

    async def test_unreachable_endpoint_is_retryable_and_names_the_base(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        provider = _provider(handler)
        with pytest.raises(ProviderUnavailableError) as excinfo:
            await provider.chat_async("hi")
        assert excinfo.value.retryable is True
        assert "127.0.0.1" in excinfo.value.reason  # tell the user where to look
        assert "start your LLM server" in excinfo.value.reason
        assert "Settings" in (excinfo.value.user_action or "")  # and what to do

    async def test_empty_completion_is_an_error_not_silence(self) -> None:
        provider = _provider(
            lambda request: httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})
        )
        with pytest.raises(ProviderUnavailableError, match="empty"):
            await provider.chat_async("hi")

    async def test_malformed_body_is_mapped(self) -> None:
        provider = _provider(lambda request: httpx.Response(200, text="<html>not json</html>"))
        with pytest.raises(ProviderUnavailableError, match="malformed"):
            await provider.chat_async("hi")

    async def test_content_parts_list_is_joined(self) -> None:
        # some servers return content as a list of typed parts
        payload = {
            "choices": [{"message": {"content": [{"text": "part-one "}, {"text": "part-two"}]}}]
        }
        provider = _provider(lambda request: httpx.Response(200, json=payload))
        assert await provider.chat_async("hi") == "part-one part-two"

    async def test_output_is_capped(self) -> None:
        payload = {"choices": [{"message": {"content": "x" * 50_000}}]}
        provider = _provider(lambda request: httpx.Response(200, json=payload))
        assert len(await provider.chat_async("hi")) <= 8000


class TestProbe:
    async def test_reachable_reports_latency_and_models(self) -> None:
        payload = {"data": [{"id": "qwen2.5-3b"}, {"id": "llama-3.2-1b"}]}

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/models")  # health check, not a completion
            return httpx.Response(200, json=payload)

        probe = await _provider(handler).probe_async()
        assert probe["reachable"] is True
        assert probe["models"] == ["qwen2.5-3b", "llama-3.2-1b"]
        assert probe["model_configured"] is True
        assert probe["error"] is None
        assert isinstance(probe["latency_ms"], int)

    async def test_unreachable_is_honest_not_an_exception(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        probe = await _provider(handler).probe_async()
        assert probe["reachable"] is False
        assert "start your LLM server" in probe["error"]
        assert probe["models"] == []

    async def test_http_error_status_is_surfaced(self) -> None:
        probe = await _provider(lambda request: httpx.Response(404, text="nope")).probe_async()
        assert probe["reachable"] is False
        assert "404" in probe["error"]

    async def test_configured_model_missing_from_server_list_is_flagged(self) -> None:
        probe = await _provider(
            lambda request: httpx.Response(200, json={"data": [{"id": "other-model"}]})
        ).probe_async()
        assert probe["reachable"] is True
        assert probe["model_configured"] is False
