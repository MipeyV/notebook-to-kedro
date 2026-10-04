"""Request and validate a code proposal without executing or persisting it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from notebook_to_kedro.generation.code.assembly import (
    NODE_BODY_ASSEMBLY_VERSION,
    assemble_node_body,
)
from notebook_to_kedro.generation.code.contracts import NodeBodyResponse, NodeCodeResponse
from notebook_to_kedro.generation.code.evidence import build_parameter_evidence
from notebook_to_kedro.generation.code.validation import validate_node_code

if TYPE_CHECKING:
    from notebook_to_kedro.generation.code.contracts import NodeCodeRequest
    from notebook_to_kedro.generation.code.providers import NodeBodyProvider, NodeCodeProvider


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


@dataclass(frozen=True, slots=True)
class NodeBodyResult:
    """Accepted body and assembled response with exact raw JSON and provider provenance."""

    request: NodeCodeRequest
    body_response: NodeBodyResponse
    response: NodeCodeResponse
    raw_response_json: str
    provider_name: str
    model_name: str
    prompt_version: str
    assembly_version: str = NODE_BODY_ASSEMBLY_VERSION


def request_node_body(request: NodeCodeRequest, provider: NodeBodyProvider) -> NodeBodyResult:
    """Preflight evidence, request one body and validate its assembly without execution."""
    build_parameter_evidence(request)
    provider_name, model_name, prompt_version = (
        provider.provider_name,
        provider.model_name,
        provider.prompt_version,
    )
    raw_response_json = provider.complete(request)
    body_response = NodeBodyResponse.from_json(raw_response_json)
    response = assemble_node_body(request, body_response)
    return NodeBodyResult(
        request,
        body_response,
        response,
        raw_response_json,
        provider_name,
        model_name,
        prompt_version,
    )
