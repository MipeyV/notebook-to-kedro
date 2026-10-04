"""Opt-in local Ollama adapter for body-only node proposals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import NodeCodeProviderError, SemanticProviderError
from notebook_to_kedro.generation.code.body_prompting import (
    NODE_BODY_PROMPT_VERSION,
    render_node_body_prompt,
)
from notebook_to_kedro.generation.code.schemas import NODE_BODY_RESPONSE_JSON_SCHEMA
from notebook_to_kedro.semantic.ollama import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MAX_RESPONSE_BYTES,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    OllamaSemanticPlanningProvider,
)
from notebook_to_kedro.semantic.providers import SemanticProviderRequest

if TYPE_CHECKING:
    from notebook_to_kedro.generation.code.contracts import NodeCodeRequest
    from notebook_to_kedro.semantic.ollama import OllamaHttpTransport


class OllamaNodeBodyProvider:
    """Request raw body JSON through the existing bounded loopback transport."""

    provider_name = "ollama"

    def __init__(
        self,
        model_name: str,
        *,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_OLLAMA_MAX_RESPONSE_BYTES,
        _transport: OllamaHttpTransport | None = None,
    ) -> None:
        """Configure a downloaded local model without pulling or invoking it."""
        if not model_name.strip():
            raise ValueError("model_name must not be empty")
        self._client = OllamaSemanticPlanningProvider(
            model_name=model_name,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
        if _transport is not None:
            self._client._transport = _transport

    @property
    def model_name(self) -> str:
        """Identify the configured local model."""
        return self._client.model_name

    @property
    def prompt_version(self) -> str:
        """Identify the body-only prompt for application-owned provenance."""
        return NODE_BODY_PROMPT_VERSION

    def complete(self, request: NodeCodeRequest) -> str:
        """Return raw body JSON; use request_node_body to assemble and validate it."""
        provider_request = SemanticProviderRequest(
            request_id=request.request_id,
            prompt=render_node_body_prompt(request),
            response_schema=NODE_BODY_RESPONSE_JSON_SCHEMA,
        )
        try:
            return self._client.complete(provider_request)
        except SemanticProviderError as error:
            raise NodeCodeProviderError(error.code, error.message) from error
