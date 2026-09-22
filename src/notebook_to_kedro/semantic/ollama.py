"""Local Ollama transport for structured semantic planning completions."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from math import isfinite
from typing import TYPE_CHECKING, Protocol, Self, TypeAlias, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from notebook_to_kedro.exceptions import SemanticProviderError

if TYPE_CHECKING:
    from notebook_to_kedro.semantic.providers import SemanticProviderRequest

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 120.0
DEFAULT_OLLAMA_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class _HttpResponse(Protocol):
    def read(self, amount: int = -1) -> bytes: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...


OllamaHttpTransport: TypeAlias = Callable[[Request, float], AbstractContextManager[_HttpResponse]]


def _stdlib_http_transport(
    request: Request, timeout_seconds: float
) -> AbstractContextManager[_HttpResponse]:
    return cast(
        "AbstractContextManager[_HttpResponse]",
        urlopen(request, timeout=timeout_seconds),
    )


@dataclass(slots=True)
class OllamaSemanticPlanningProvider:
    """Call a local Ollama chat endpoint with structured output enabled."""

    model_name: str
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS
    max_response_bytes: int = DEFAULT_OLLAMA_MAX_RESPONSE_BYTES
    _transport: OllamaHttpTransport = field(
        default=_stdlib_http_transport,
        repr=False,
        compare=False,
    )
    provider_name: str = field(default="ollama", init=False)

    def __post_init__(self) -> None:
        if not self.model_name:
            raise ValueError("model_name must not be empty")
        if _looks_like_cloud_model(self.model_name):
            message = "model_name must identify a downloaded local model, not an Ollama cloud tag"
            raise ValueError(message)
        self.base_url = _normalize_local_base_url(self.base_url)
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive finite number")
        if self.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be greater than zero")

    def complete(self, request: SemanticProviderRequest) -> str:
        """Return the assistant JSON content from one non-streaming chat call."""
        body = json.dumps(
            {
                "model": self.model_name,
                "messages": [{"role": "user", "content": request.prompt}],
                "stream": False,
                "format": dict(request.response_schema),
                "options": {"temperature": 0},
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        http_request = Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )

        try:
            with self._transport(http_request, self.timeout_seconds) as response:
                response_body = response.read(self.max_response_bytes + 1)
        except HTTPError as error:
            raise SemanticProviderError(
                "ollama_http_error",
                f"HTTP {error.code}: {_http_error_detail(error)}",
            ) from error
        except TimeoutError as error:
            raise SemanticProviderError(
                "ollama_timeout",
                f"request exceeded {self.timeout_seconds:g} seconds",
            ) from error
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise SemanticProviderError(
                    "ollama_timeout",
                    f"request exceeded {self.timeout_seconds:g} seconds",
                ) from error
            raise SemanticProviderError(
                "ollama_unavailable",
                f"local Ollama server is unavailable: {error.reason}",
            ) from error

        if len(response_body) > self.max_response_bytes:
            raise SemanticProviderError(
                "ollama_response_too_large",
                f"response exceeds {self.max_response_bytes} bytes",
            )
        return _assistant_content(response_body)


def _normalize_local_base_url(value: str) -> str:
    if not value:
        raise ValueError("base_url must not be empty")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("base_url must be a valid local HTTP URL") from error
    if (
        parsed.scheme != "http"
        or parsed.hostname not in _LOCAL_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        message = "base_url must target a local Ollama HTTP server without a path"
        raise ValueError(message)
    if port is None:
        return f"http://{_formatted_host(parsed.hostname)}"
    return f"http://{_formatted_host(parsed.hostname)}:{port}"


def _looks_like_cloud_model(model_name: str) -> bool:
    tag = model_name.rpartition(":")[2]
    return tag == "cloud" or tag.endswith("-cloud")


def _formatted_host(hostname: str | None) -> str:
    if hostname == "::1":
        return "[::1]"
    return cast("str", hostname)


def _http_error_detail(error: HTTPError) -> str:
    try:
        body = error.read(DEFAULT_OLLAMA_MAX_RESPONSE_BYTES)
        decoded: object = json.loads(body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return str(error.reason)
    if isinstance(decoded, Mapping):
        message = decoded.get("error")
        if isinstance(message, str) and message:
            return message
    return str(error.reason)


def _assistant_content(response_body: bytes) -> str:
    try:
        decoded: object = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SemanticProviderError(
            "ollama_invalid_response", "response body is not valid UTF-8 JSON"
        ) from error
    if not isinstance(decoded, Mapping):
        raise SemanticProviderError(
            "ollama_invalid_response", "response body must be a JSON object"
        )
    provider_error = decoded.get("error")
    if isinstance(provider_error, str) and provider_error:
        raise SemanticProviderError("ollama_generation_error", provider_error)
    message = decoded.get("message")
    if not isinstance(message, Mapping):
        raise SemanticProviderError(
            "ollama_invalid_response", "response must contain a message object"
        )
    content = message.get("content")
    if not isinstance(content, str) or not content:
        raise SemanticProviderError(
            "ollama_invalid_response", "response message content must be a non-empty string"
        )
    return content
