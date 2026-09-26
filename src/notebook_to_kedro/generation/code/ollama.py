"""Opt-in local Ollama adapter for node code proposals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import NodeCodeProviderError, SemanticProviderError
from notebook_to_kedro.generation.code.prompting import render_node_code_prompt
from notebook_to_kedro.generation.code.schemas import NODE_CODE_RESPONSE_JSON_SCHEMA
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


class OllamaNodeCodeProvider:
    """Reuse the bounded local chat transport; do not run or persist proposed code."""

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
        """Configure one explicit local model with no automatic pull or fallback."""
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
        """Return the configured model for application-owned provenance."""
        return self._client.model_name

    def complete(self, request: NodeCodeRequest) -> str:
        """Return raw assistant JSON; use request_node_code for static validation."""
        provider_request = SemanticProviderRequest(
            request_id=request.request_id,
            prompt=render_node_code_prompt(request),
            response_schema=NODE_CODE_RESPONSE_JSON_SCHEMA,
        )
        try:
            return self._client.complete(provider_request)
        except SemanticProviderError as error:
            raise NodeCodeProviderError(error.code, error.message) from error
