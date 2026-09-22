"""Versioned contracts for provider-neutral semantic planning suggestions."""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan, NotebookFacts

SEMANTIC_PLANNING_SCHEMA_VERSION = "1.0"
_PUBLIC_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        message = f"{field_name} must not be empty"
        raise ValueError(message)


def _require_string_items(values: tuple[str, ...], field_name: str) -> None:
    if any(not value for value in values):
        message = f"{field_name} must not contain empty values"
        raise ValueError(message)
    if len(values) != len(set(values)):
        message = f"{field_name} must contain unique values"
        raise ValueError(message)


def _require_public_identifier(value: str, field_name: str) -> None:
    if _PUBLIC_IDENTIFIER.fullmatch(value) is None or keyword.iskeyword(value):
        message = f"{field_name} must be a public ASCII Python identifier"
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class SemanticPlanningRequest:
    """Deterministic context supplied to a semantic planning provider."""

    schema_version: str
    request_id: str
    prompt_version: str
    facts: NotebookFacts
    baseline_plan: ConversionPlan

    def __post_init__(self) -> None:
        if self.schema_version != SEMANTIC_PLANNING_SCHEMA_VERSION:
            message = f"schema_version must be {SEMANTIC_PLANNING_SCHEMA_VERSION!r}"
            raise ValueError(message)
        _require_non_empty(self.request_id, "request_id")
        _require_non_empty(self.prompt_version, "prompt_version")
        if self.baseline_plan.notebook_path != self.facts.notebook.path:
            message = "baseline_plan notebook path must match notebook facts"
            raise ValueError(message)

    def to_dict(self) -> dict[str, object]:
        """Return the deterministic provider request payload."""
        from notebook_to_kedro.semantic.serialization import (  # noqa: PLC0415
            semantic_planning_request_to_dict,
        )

        return semantic_planning_request_to_dict(self)

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize the provider request as deterministic JSON."""
        from notebook_to_kedro.semantic.serialization import (  # noqa: PLC0415
            semantic_planning_request_to_json,
        )

        return semantic_planning_request_to_json(self, indent=indent)


@dataclass(frozen=True, slots=True)
class SemanticTaskSuggestion:
    """One model-proposed node boundary with source provenance."""

    source_cell_ids: tuple[str, ...]
    statement_ids: tuple[str, ...]
    node_name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    parameter_names: tuple[str, ...]
    pipeline_id: str
    review_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_cell_ids:
            message = "source_cell_ids must not be empty"
            raise ValueError(message)
        if not self.statement_ids:
            message = "statement_ids must not be empty"
            raise ValueError(message)
        _require_string_items(self.source_cell_ids, "source_cell_ids")
        _require_string_items(self.statement_ids, "statement_ids")
        _require_string_items(self.inputs, "inputs")
        _require_string_items(self.outputs, "outputs")
        _require_string_items(self.parameter_names, "parameter_names")
        _require_string_items(self.review_notes, "review_notes")
        _require_public_identifier(self.node_name, "node_name")
        _require_public_identifier(self.pipeline_id, "pipeline_id")


@dataclass(frozen=True, slots=True)
class SemanticPlanningResponse:
    """Strict structured output returned by a semantic planning provider."""

    schema_version: str
    request_id: str
    tasks: tuple[SemanticTaskSuggestion, ...]
    review_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != SEMANTIC_PLANNING_SCHEMA_VERSION:
            message = f"schema_version must be {SEMANTIC_PLANNING_SCHEMA_VERSION!r}"
            raise ValueError(message)
        _require_non_empty(self.request_id, "request_id")
        _require_string_items(self.review_notes, "review_notes")
        node_names = tuple(task.node_name for task in self.tasks)
        if len(node_names) != len(set(node_names)):
            message = "task node names must be unique"
            raise ValueError(message)

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-compatible response payload."""
        from notebook_to_kedro.semantic.serialization import (  # noqa: PLC0415
            semantic_planning_response_to_dict,
        )

        return semantic_planning_response_to_dict(self)

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize the response as deterministic JSON."""
        from notebook_to_kedro.semantic.serialization import (  # noqa: PLC0415
            semantic_planning_response_to_json,
        )

        return semantic_planning_response_to_json(self, indent=indent)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> Self:
        """Parse and validate a decoded provider response."""
        from notebook_to_kedro.semantic.serialization import (  # noqa: PLC0415
            semantic_planning_response_from_dict,
        )

        response = semantic_planning_response_from_dict(payload)
        if cls is not SemanticPlanningResponse:
            message = "SemanticPlanningResponse deserialization does not support subclasses"
            raise TypeError(message)
        return response  # type: ignore[return-value]

    @classmethod
    def from_json(cls, payload: str) -> Self:
        """Decode and validate a provider response."""
        from notebook_to_kedro.semantic.serialization import (  # noqa: PLC0415
            semantic_planning_response_from_json,
        )

        response = semantic_planning_response_from_json(payload)
        if cls is not SemanticPlanningResponse:
            message = "SemanticPlanningResponse deserialization does not support subclasses"
            raise TypeError(message)
        return response  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class SemanticPlanningTrace:
    """Provider and prompt metadata recorded outside model-generated content."""

    request_id: str
    prompt_version: str
    provider_name: str
    model_name: str

    def __post_init__(self) -> None:
        _require_non_empty(self.request_id, "request_id")
        _require_non_empty(self.prompt_version, "prompt_version")
        _require_non_empty(self.provider_name, "provider_name")
        _require_non_empty(self.model_name, "model_name")


@dataclass(frozen=True, slots=True)
class SemanticPlanningResult:
    """Auditable pairing of one request, response, and invocation trace."""

    request: SemanticPlanningRequest
    response: SemanticPlanningResponse
    trace: SemanticPlanningTrace

    def __post_init__(self) -> None:
        request_ids = {self.request.request_id, self.response.request_id, self.trace.request_id}
        if len(request_ids) != 1:
            message = "request, response, and trace request IDs must match"
            raise ValueError(message)
        if self.trace.prompt_version != self.request.prompt_version:
            message = "trace prompt_version must match the request"
            raise ValueError(message)
