"""Versioned immutable inputs and untrusted outputs for one node code proposal."""

from __future__ import annotations

import keyword
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Self

from notebook_to_kedro.generation.code.serialization import decode_object, encode_object
from notebook_to_kedro.semantic.validation import validate_conversion_plan

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan

NODE_CODE_SCHEMA_VERSION = "1.0"
_RESPONSE_STRINGS = ("schema_version", "request_id", "task_id", "function_code")
_RESPONSE_ARRAYS = ("imports", "review_notes")
_REQUEST_STRINGS = ("schema_version", "request_id", "task_id", "node_name", "raw_source")
_REQUEST_ARRAYS = (
    "source_cell_ids",
    "statement_ids",
    "inputs",
    "outputs",
    "parameter_names",
    "parameter_arguments",
    "allowed_imports",
)


def _identity(schema_version: str, request_id: str, task_id: str) -> None:
    if schema_version != NODE_CODE_SCHEMA_VERSION:
        raise ValueError("unsupported node code schema_version")
    if not request_id.strip() or not task_id.strip():
        raise ValueError("request_id and task_id must not be empty")


def _unique(values: tuple[str, ...], label: str) -> None:
    if any(not value.strip() for value in values) or len(set(values)) != len(values):
        raise ValueError(f"{label} must contain unique non-empty strings")


def _identifiers(values: tuple[str, ...]) -> None:
    if any(
        not value.isascii() or not value.isidentifier() or keyword.iskeyword(value)
        for value in values
    ):
        raise ValueError("node and interface names must be ASCII Python identifiers")


@dataclass(frozen=True, slots=True)
class NodeCodeRequest:
    """Immutable source provenance, callable interface and import permissions."""

    schema_version: str
    request_id: str
    task_id: str
    node_name: str
    raw_source: str
    source_cell_ids: tuple[str, ...]
    statement_ids: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    parameter_names: tuple[str, ...] = ()
    parameter_arguments: tuple[str, ...] = ()
    allowed_imports: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identity(self.schema_version, self.request_id, self.task_id)
        if not self.raw_source.strip() or not self.source_cell_ids or not self.statement_ids:
            raise ValueError("raw_source, source_cell_ids and statement_ids are required")
        for field in _REQUEST_ARRAYS:
            _unique(getattr(self, field), field)
        _identifiers((self.node_name, *self.inputs, *self.outputs, *self.parameter_arguments))
        if self.node_name.startswith("_"):
            raise ValueError("node_name must be public")
        _unique(self.arguments, "function arguments")
        if len(self.parameter_names) != len(self.parameter_arguments):
            raise ValueError("parameter names and arguments must have matching lengths")

    @property
    def arguments(self) -> tuple[str, ...]:
        """Return the exact ordered positional-or-keyword function signature."""
        return (*self.inputs, *self.parameter_arguments)

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize request evidence with stable JSON key ordering."""
        return encode_object(asdict(self), indent=indent)

    @classmethod
    def from_json(cls, payload: str) -> Self:
        """Parse a strict versioned request."""
        data = decode_object(payload, _REQUEST_STRINGS, _REQUEST_ARRAYS)
        return cls(**data)


@dataclass(frozen=True, slots=True)
class NodeCodeResponse:
    """Untrusted function source and imports awaiting request-specific validation."""

    schema_version: str
    request_id: str
    task_id: str
    function_code: str
    imports: tuple[str, ...] = ()
    review_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identity(self.schema_version, self.request_id, self.task_id)
        if not self.function_code.strip():
            raise ValueError("function_code must not be empty")
        _unique(self.imports, "imports")
        _unique(self.review_notes, "review_notes")

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize the untrusted response deterministically."""
        return encode_object(asdict(self), indent=indent)

    @classmethod
    def from_json(cls, payload: str) -> Self:
        """Parse strict JSON without executing the proposed code."""
        data = decode_object(payload, _RESPONSE_STRINGS, _RESPONSE_ARRAYS)
        return cls(**data)


def build_node_code_request(
    plan: ConversionPlan, task_id: str, *, request_id: str
) -> NodeCodeRequest:
    """Project a validated plan task and its parameter mapping into a code request."""
    validate_conversion_plan(plan)
    task = next((task for task in plan.task_candidates if task.id == task_id), None)
    if task is None:
        raise ValueError(f"unknown task ID: {task_id}")
    parameters = {parameter.name: parameter.function_argument for parameter in plan.parameters}
    return NodeCodeRequest(
        schema_version=NODE_CODE_SCHEMA_VERSION,
        request_id=request_id,
        task_id=task.id,
        node_name=task.name,
        raw_source=task.source,
        source_cell_ids=task.source_cell_ids,
        statement_ids=task.statement_ids,
        inputs=task.inputs,
        outputs=task.outputs,
        parameter_names=task.parameters,
        parameter_arguments=tuple(parameters[name] for name in task.parameters),
        allowed_imports=plan.imports,
    )
