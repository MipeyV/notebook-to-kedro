"""Tests for the local Ollama semantic planning transport."""

from __future__ import annotations

import json
from dataclasses import replace
from email.message import Message
from io import BytesIO
from math import inf, nan
from typing import TYPE_CHECKING, Self, cast
from urllib.error import HTTPError, URLError

import pytest

from notebook_to_kedro.exceptions import SemanticProviderError
from notebook_to_kedro.semantic import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MAX_RESPONSE_BYTES,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    OllamaSemanticPlanningProvider,
    SemanticGroupingResponse,
    SemanticPlanningProvider,
    SemanticPlanningRequest,
    SemanticPlanningResponse,
    SemanticProviderRequest,
    request_semantic_planning,
)
from notebook_to_kedro.semantic import ollama as ollama_module

if TYPE_CHECKING:
    from urllib.request import Request


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.read_amounts: list[int] = []
        self.exited = False

    def read(self, amount: int = -1) -> bytes:
        self.read_amounts.append(amount)
        return self.body if amount < 0 else self.body[:amount]

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.exited = True


class _RecordingTransport:
    def __init__(
        self,
        response: _Response | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[Request, float]] = []

    def __call__(self, request: Request, timeout: float) -> _Response:
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("test transport has no response")
        return self.response


def _provider_request(prompt: str = "Structure this notebook.") -> SemanticProviderRequest:
    return SemanticProviderRequest(
        request_id="request-0001",
        prompt=prompt,
        response_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
        },
    )


def _ollama_envelope(content: str) -> bytes:
    return json.dumps({"message": {"role": "assistant", "content": content}}).encode()


def test_provider_posts_non_streaming_structured_chat_request() -> None:
    response = _Response(_ollama_envelope('{"answer":"ok"}'))
    transport = _RecordingTransport(response=response)
    provider: SemanticPlanningProvider = OllamaSemanticPlanningProvider(
        model_name="qwen-test:latest",
        base_url="http://127.0.0.1:11434/",
        timeout_seconds=15,
        max_response_bytes=1024,
        _transport=transport,
    )
    provider_request = _provider_request()

    content = provider.complete(provider_request)

    assert content == '{"answer":"ok"}'
    assert provider.provider_name == "ollama"
    assert provider.model_name == "qwen-test:latest"
    assert isinstance(provider, OllamaSemanticPlanningProvider)
    assert provider.base_url == "http://127.0.0.1:11434"
    assert len(transport.calls) == 1
    request, timeout = transport.calls[0]
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    assert request.get_method() == "POST"
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("Content-type") == "application/json"
    assert timeout == 15
    assert json.loads(cast("bytes", request.data)) == {
        "model": "qwen-test:latest",
        "messages": [{"role": "user", "content": provider_request.prompt}],
        "stream": False,
        "think": False,
        "format": dict(provider_request.response_schema),
        "options": {"temperature": 0},
    }
    assert response.read_amounts == [1025]
    assert response.exited is True


def test_provider_defaults_are_local_and_bounded() -> None:
    provider = OllamaSemanticPlanningProvider(model_name="local-model")

    assert provider.base_url == DEFAULT_OLLAMA_BASE_URL
    assert provider.timeout_seconds == DEFAULT_OLLAMA_TIMEOUT_SECONDS
    assert provider.max_response_bytes == DEFAULT_OLLAMA_MAX_RESPONSE_BYTES


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("http://localhost", "http://localhost"),
        ("http://localhost:1234/", "http://localhost:1234"),
        ("http://[::1]:11434", "http://[::1]:11434"),
    ],
)
def test_provider_normalizes_supported_loopback_urls(base_url: str, expected: str) -> None:
    provider = OllamaSemanticPlanningProvider(model_name="model", base_url=base_url)

    assert provider.base_url == expected


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "https://localhost:11434",
        "http://example.com:11434",
        "http://user@localhost:11434",
        "http://localhost:11434/api",
        "http://localhost:11434?query=yes",
        "http://localhost:11434#fragment",
        "http://localhost:not-a-port",
        "http://[::1",
    ],
)
def test_provider_rejects_nonlocal_or_malformed_urls(base_url: str) -> None:
    with pytest.raises(ValueError, match="base_url"):
        OllamaSemanticPlanningProvider(model_name="model", base_url=base_url)


def test_provider_rejects_credentials_in_base_url() -> None:
    with pytest.raises(ValueError, match="local Ollama HTTP server"):
        OllamaSemanticPlanningProvider(
            model_name="model", base_url="http://user:password@localhost:11434"
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"model_name": ""}, "model_name must not be empty"),
        ({"model_name": "gemma4:cloud"}, "downloaded local model"),
        ({"model_name": "gpt-oss:120b-cloud"}, "downloaded local model"),
        ({"timeout_seconds": 0}, "positive finite"),
        ({"timeout_seconds": -1}, "positive finite"),
        ({"timeout_seconds": inf}, "positive finite"),
        ({"timeout_seconds": nan}, "positive finite"),
        ({"max_response_bytes": 0}, "greater than zero"),
    ],
)
def test_provider_rejects_invalid_configuration(changes: dict[str, object], message: str) -> None:
    values: dict[str, object] = {"model_name": "model"}
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        OllamaSemanticPlanningProvider(**values)  # type: ignore[arg-type]


def test_provider_uses_standard_library_transport_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _Response(_ollama_envelope("{}"))
    calls: list[tuple[Request, float]] = []

    def fake_urlopen(request: Request, *, timeout: float) -> _Response:
        calls.append((request, timeout))
        return response

    monkeypatch.setattr(ollama_module, "urlopen", fake_urlopen)
    provider = OllamaSemanticPlanningProvider(model_name="model", timeout_seconds=3)

    assert provider.complete(_provider_request()) == "{}"
    assert calls[0][1] == 3


def test_provider_integrates_with_semantic_orchestration(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
    semantic_grouping_response: SemanticGroupingResponse,
) -> None:
    transport = _RecordingTransport(
        response=_Response(_ollama_envelope(semantic_grouping_response.to_json(indent=None)))
    )
    provider = OllamaSemanticPlanningProvider(
        model_name="semantic-model",
        _transport=transport,
    )

    outcome = request_semantic_planning(semantic_request, provider)

    assert outcome.used_fallback is False
    assert outcome.result is not None
    assert outcome.result.response == replace(semantic_response, review_notes=())
    assert outcome.trace.provider_name == "ollama"
    assert outcome.trace.model_name == "semantic-model"


def test_provider_normalizes_json_http_errors() -> None:
    error = HTTPError(
        "http://localhost:11434/api/chat",
        404,
        "Not Found",
        hdrs=Message(),
        fp=BytesIO(b'{"error":"model not found"}'),
    )
    provider = OllamaSemanticPlanningProvider(
        model_name="missing-model",
        _transport=_RecordingTransport(error=error),
    )

    with pytest.raises(SemanticProviderError) as error_info:
        provider.complete(_provider_request())

    assert error_info.value.code == "ollama_http_error"
    assert error_info.value.message == "HTTP 404: model not found"


@pytest.mark.parametrize(
    "body",
    [b"not-json", b"[]", b"{}", b'{"error":""}', b'{"error":1}', b"\xff"],
)
def test_provider_uses_http_reason_for_unstructured_http_errors(body: bytes) -> None:
    error = HTTPError(
        "http://localhost:11434/api/chat",
        500,
        "Internal Server Error",
        hdrs=Message(),
        fp=BytesIO(body),
    )
    provider = OllamaSemanticPlanningProvider(
        model_name="model",
        _transport=_RecordingTransport(error=error),
    )

    with pytest.raises(SemanticProviderError, match="HTTP 500: Internal Server Error"):
        provider.complete(_provider_request())


def test_provider_handles_unreadable_http_error_body() -> None:
    class _UnreadableBody:
        def read(self, amount: int = -1) -> bytes:
            raise OSError(amount)

        def close(self) -> None:
            pass

    error = HTTPError(
        "http://localhost:11434/api/chat",
        500,
        "Internal Server Error",
        hdrs=Message(),
        fp=_UnreadableBody(),  # type: ignore[arg-type]
    )
    provider = OllamaSemanticPlanningProvider(
        model_name="model",
        _transport=_RecordingTransport(error=error),
    )

    with pytest.raises(SemanticProviderError, match="Internal Server Error"):
        provider.complete(_provider_request())


@pytest.mark.parametrize(
    ("transport_error", "code"),
    [
        (TimeoutError(), "ollama_timeout"),
        (URLError(TimeoutError()), "ollama_timeout"),
        (URLError(ConnectionRefusedError("refused")), "ollama_unavailable"),
    ],
)
def test_provider_normalizes_connection_failures(transport_error: BaseException, code: str) -> None:
    provider = OllamaSemanticPlanningProvider(
        model_name="model",
        timeout_seconds=7.5,
        _transport=_RecordingTransport(error=transport_error),
    )

    with pytest.raises(SemanticProviderError) as error_info:
        provider.complete(_provider_request())

    assert error_info.value.code == code
    if code == "ollama_timeout":
        assert error_info.value.message == "request exceeded 7.5 seconds"
    else:
        assert "local Ollama server is unavailable" in error_info.value.message


def test_provider_rejects_oversized_response() -> None:
    provider = OllamaSemanticPlanningProvider(
        model_name="model",
        max_response_bytes=10,
        _transport=_RecordingTransport(response=_Response(b"x" * 11)),
    )

    with pytest.raises(SemanticProviderError) as error_info:
        provider.complete(_provider_request())

    assert error_info.value.code == "ollama_response_too_large"
    assert error_info.value.message == "response exceeds 10 bytes"


@pytest.mark.parametrize("body", [b"not-json", b"\xff"])
def test_provider_rejects_non_json_response_body(body: bytes) -> None:
    provider = OllamaSemanticPlanningProvider(
        model_name="model",
        _transport=_RecordingTransport(response=_Response(body)),
    )

    with pytest.raises(SemanticProviderError) as error_info:
        provider.complete(_provider_request())

    assert error_info.value.code == "ollama_invalid_response"
    assert error_info.value.message == "response body is not valid UTF-8 JSON"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "response body must be a JSON object"),
        ({}, "response must contain a message object"),
        ({"error": ""}, "response must contain a message object"),
        ({"message": []}, "response must contain a message object"),
        ({"message": {}}, "response message content must be a non-empty string"),
        ({"message": {"content": ""}}, "response message content must be a non-empty string"),
        ({"message": {"content": 1}}, "response message content must be a non-empty string"),
    ],
)
def test_provider_rejects_invalid_ollama_envelopes(payload: object, message: str) -> None:
    provider = OllamaSemanticPlanningProvider(
        model_name="model",
        _transport=_RecordingTransport(response=_Response(json.dumps(payload).encode("utf-8"))),
    )

    with pytest.raises(SemanticProviderError) as error_info:
        provider.complete(_provider_request())

    assert error_info.value.code == "ollama_invalid_response"
    assert error_info.value.message == message


def test_provider_reports_generation_error_from_successful_http_response() -> None:
    provider = OllamaSemanticPlanningProvider(
        model_name="model",
        _transport=_RecordingTransport(response=_Response(b'{"error":"generation failed"}')),
    )

    with pytest.raises(SemanticProviderError) as error_info:
        provider.complete(_provider_request())

    assert error_info.value.code == "ollama_generation_error"
    assert error_info.value.message == "generation failed"
