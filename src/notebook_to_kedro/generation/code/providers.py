"""Transport protocol and deterministic provider for node code proposals."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from notebook_to_kedro.generation.code.contracts import NodeCodeRequest


class NodeCodeProvider(Protocol):
    """Return raw response JSON; validation belongs to the application."""

    provider_name: str
    model_name: str

    def complete(self, request: NodeCodeRequest) -> str:
        """Propose code for exactly one task without writing a project."""
        ...


class FakeNodeCodeProvider:
    """Record requests and return fixed JSON or raise a configured failure."""

    provider_name = "fake"

    def __init__(
        self,
        *,
        response_json: str | None = None,
        error: RuntimeError | None = None,
        model_name: str = "fixed-response",
    ) -> None:
        """Configure exactly one response behavior for offline tests."""
        if (response_json is None) == (error is None):
            raise ValueError("exactly one of response_json or error must be provided")
        if not model_name.strip():
            raise ValueError("model_name must not be empty")
        self.model_name = model_name
        self._response_json = response_json
        self._error = error
        self._requests: list[NodeCodeRequest] = []

    @property
    def requests(self) -> tuple[NodeCodeRequest, ...]:
        """Return recorded requests in invocation order."""
        return tuple(self._requests)

    def complete(self, request: NodeCodeRequest) -> str:
        """Return the configured result without network or filesystem I/O."""
        self._requests.append(request)
        if self._error is not None:
            raise self._error
        return cast("str", self._response_json)
