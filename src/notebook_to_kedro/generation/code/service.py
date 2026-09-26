"""Request and validate a code proposal without executing or persisting it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from notebook_to_kedro.generation.code.contracts import NodeCodeResponse
from notebook_to_kedro.generation.code.validation import validate_node_code

if TYPE_CHECKING:
    from notebook_to_kedro.generation.code.contracts import NodeCodeRequest
    from notebook_to_kedro.generation.code.providers import NodeCodeProvider


@dataclass(frozen=True, slots=True)
class NodeCodeResult:
    """Structurally validated proposal with application-owned provider provenance."""

    request: NodeCodeRequest
    response: NodeCodeResponse
    provider_name: str
    model_name: str


def request_node_code(request: NodeCodeRequest, provider: NodeCodeProvider) -> NodeCodeResult:
    """Return an accepted proposal or propagate parsing, validation or provider failures."""
    provider_name, model_name = provider.provider_name, provider.model_name
    response = NodeCodeResponse.from_json(provider.complete(request))
    validate_node_code(request, response)
    return NodeCodeResult(request, response, provider_name, model_name)
