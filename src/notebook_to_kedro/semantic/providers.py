"""Provider transport contracts and deterministic test provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

    from notebook_to_kedro.exceptions import SemanticProviderError


@dataclass(frozen=True, slots=True)
class SemanticProviderRequest:
    """Provider-ready prompt and structured-output schema."""

    request_id: str
    prompt: str
    response_schema: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id must not be empty")
        if not self.prompt:
            raise ValueError("prompt must not be empty")
        if not self.response_schema:
            raise ValueError("response_schema must not be empty")


class FakeSemanticPlanningProvider:
    """Return fixed output or a fixed expected failure without I/O."""

    provider_name = "fake"

    def __init__(
        self,
        *,
        response_json: str | None = None,
        error: SemanticProviderError | None = None,
        model_name: str = "fixed-response",
    ) -> None:
        """Configure exactly one deterministic response behavior."""
        if (response_json is None) == (error is None):
            message = "exactly one of response_json or error must be provided"
            raise ValueError(message)
        if not model_name:
            raise ValueError("model_name must not be empty")
        self.model_name = model_name
        self._response_json = response_json
        self._error = error
        self._requests: list[SemanticProviderRequest] = []

    @property
    def requests(self) -> tuple[SemanticProviderRequest, ...]:
        """Return provider requests in call order for deterministic assertions."""
        return tuple(self._requests)

    def complete(self, request: SemanticProviderRequest) -> str:
        """Record the request, then return or raise the configured result."""
        self._requests.append(request)
        if self._error is not None:
            raise self._error
        return cast("str", self._response_json)
