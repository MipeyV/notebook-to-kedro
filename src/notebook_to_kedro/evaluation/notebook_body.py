"""Offline static batches of recorded node bodies, without provider or execution I/O."""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
from dataclasses import asdict, dataclass
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING, Literal

from notebook_to_kedro.generation.code import (
    NodeBodyResponse,
    NodeCodeRequest,
    NodeCodeResponse,
    assemble_node_body,
    build_node_code_request,
    build_parameter_evidence,
)
from notebook_to_kedro.semantic.validation import validate_conversion_plan

if TYPE_CHECKING:
    from collections.abc import Sequence

    from notebook_to_kedro.ir import ConversionPlan

NotebookBodyStatus = Literal[
    "accepted", "not_requested", "provider_error", "invalid_response", "invalid_code"
]
DEFAULT_NOTEBOOK_BODY_RESPONSE_BYTES = 1_048_576
_PROVIDER_ERROR_LENGTH = 2


@dataclass(frozen=True, slots=True)
class NotebookBodyRecord:
    """One exact recorded response or transport error; absent records mean not requested."""

    request_id: str
    raw_response: str | None = None
    provider_error: tuple[str, str] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("record request_id must be a non-empty string")
        if (self.raw_response is None) == (self.provider_error is None):
            raise ValueError("record must contain exactly one response or provider error")
        if self.raw_response is not None and not isinstance(self.raw_response, str):
            raise ValueError("record raw_response must be a string")
        if self.provider_error is not None and (
            not isinstance(self.provider_error, tuple)
            or len(self.provider_error) != _PROVIDER_ERROR_LENGTH
            or any(not isinstance(value, str) or not value.strip() for value in self.provider_error)
        ):
            raise ValueError("provider_error must contain a non-empty code and message")


@dataclass(frozen=True, slots=True)
class NotebookBodyProposal:
    """One planned slot, preserving raw data and the stage at which validation stopped."""

    request: NodeCodeRequest
    status: NotebookBodyStatus
    record: NotebookBodyRecord | None = None
    body: NodeBodyResponse | None = None
    response: NodeCodeResponse | None = None
    diagnostic_code: str | None = None
    diagnostic_message: str | None = None


@dataclass(frozen=True, slots=True)
class NotebookBodyBatchReport:
    """Transient static evidence, not an approved or executed notebook benchmark artifact."""

    plan_sha256: str
    proposals: tuple[NotebookBodyProposal, ...]
    module_source: str | None

    @property
    def planned_count(self) -> int:
        """Count every planned request, including missing and rejected records."""
        return len(self.proposals)

    @property
    def accepted_count(self) -> int:
        """Count statically accepted bodies, without claiming runtime equivalence."""
        return sum(proposal.status == "accepted" for proposal in self.proposals)

    @property
    def static_ready(self) -> bool:
        """Indicate whether a complete validated module was assembled without execution."""
        return self.module_source is not None


def _validate_graph(plan: ConversionPlan) -> None:
    producers: dict[str, str | None] = {dataset.name: None for dataset in plan.catalog_datasets}
    statements: set[str] = set()
    for task in plan.task_candidates:
        for statement in task.statement_ids:
            if statement in statements:
                raise ValueError(f"statement belongs to multiple tasks: {statement}")
            statements.add(statement)
        for output in task.outputs:
            if output in producers:
                raise ValueError(f"dataset has multiple producers: {output}")
            producers[output] = task.id
    dependencies: dict[str, set[str]] = {}
    for task in plan.task_candidates:
        dependencies[task.id] = set()
        for name in task.inputs:
            if name not in producers:
                raise ValueError(f"unresolved dataset input: {name}")
            producer = producers[name]
            if producer is not None:
                dependencies[task.id].add(producer)
    try:
        tuple(TopologicalSorter(dependencies).static_order())
    except CycleError as error:
        raise ValueError("notebook body batch requires an acyclic dataset graph") from error


def _validate_module_names(plan: ConversionPlan) -> None:
    bindings = set(dir(builtins))
    for source in plan.imports:
        try:
            statements = ast.parse(source).body
        except SyntaxError as error:
            raise ValueError("batch import must be one valid import statement") from error
        if len(statements) != 1 or not isinstance(statements[0], (ast.Import, ast.ImportFrom)):
            raise ValueError("batch import must be one valid import statement")
        statement = statements[0]
        if isinstance(statement, ast.ImportFrom) and (
            statement.level or any(alias.name == "*" for alias in statement.names)
        ):
            raise ValueError("relative and wildcard batch imports are unsupported")
        bindings.update(
            alias.asname
            or (alias.name.split(".")[0] if isinstance(statement, ast.Import) else alias.name)
            for alias in statement.names
        )
    if any(task.name in bindings for task in plan.task_candidates):
        raise ValueError("batch node names must not shadow imports or builtins")
    try:
        compile("\n".join(plan.imports), "<batch-imports>", "exec")
    except SyntaxError as error:
        raise ValueError("batch imports must compile together in their original order") from error


def prepare_notebook_body_requests(
    plan: ConversionPlan, *, request_prefix: str = "notebook-body"
) -> tuple[NodeCodeRequest, ...]:
    """Preflight the complete plan, graph and parameter evidence before any caller I/O.

    This checks the supplied plan only, not its fidelity to notebook bytes or human approval.
    No notebook, dataset, provider or destination is opened by this function.
    """
    if not isinstance(request_prefix, str) or not request_prefix.strip():
        raise ValueError("request_prefix must be a non-empty string")
    validate_conversion_plan(plan)
    if not plan.task_candidates:
        raise ValueError("notebook body batch requires at least one task")
    _validate_graph(plan)
    _validate_module_names(plan)
    requests = tuple(
        build_node_code_request(plan, task.id, request_id=f"{request_prefix}:{task.id}")
        for task in plan.task_candidates
    )
    for request in requests:
        build_parameter_evidence(request)
    return requests


def _validate_record(  # noqa: PLR0911
    request: NodeCodeRequest, record: NotebookBodyRecord | None, max_response_bytes: int
) -> NotebookBodyProposal:
    if record is None:
        return NotebookBodyProposal(request, "not_requested")
    if record.provider_error is not None:
        code, message = record.provider_error
        return NotebookBodyProposal(
            request, "provider_error", record, diagnostic_code=code, diagnostic_message=message
        )
    raw = record.raw_response
    assert raw is not None
    try:
        oversized = len(raw.encode("utf-8")) > max_response_bytes
    except UnicodeEncodeError:
        return NotebookBodyProposal(
            request,
            "invalid_response",
            record,
            diagnostic_code="invalid_utf8",
            diagnostic_message="response contains invalid UTF-8 text",
        )
    if oversized:
        return NotebookBodyProposal(
            request,
            "invalid_response",
            record,
            diagnostic_code="response_too_large",
            diagnostic_message="response exceeds max_response_bytes",
        )
    try:
        body = NodeBodyResponse.from_json(raw)
    except ValueError as error:
        return NotebookBodyProposal(
            request,
            "invalid_response",
            record,
            diagnostic_code="invalid_response",
            diagnostic_message=str(error),
        )
    try:
        response = assemble_node_body(request, body)
    except ValueError as error:
        return NotebookBodyProposal(
            request,
            "invalid_code",
            record,
            body,
            diagnostic_code="invalid_code",
            diagnostic_message=str(error),
        )
    return NotebookBodyProposal(request, "accepted", record, body, response)


def validate_notebook_body_batch(
    plan: ConversionPlan,
    records: Sequence[NotebookBodyRecord],
    *,
    request_prefix: str = "notebook-body",
    max_response_bytes: int = DEFAULT_NOTEBOOK_BODY_RESPONSE_BYTES,
) -> NotebookBodyBatchReport:
    """Validate recorded bodies as one complete static batch, retaining every planned slot.

    Missing bodies are never repaired or replaced with deterministic code. Returned module
    text remains untrusted and is not written, imported or executed. This transient report
    lacks source/review binding, durable capture and runtime evidence required for live use.
    """
    if type(max_response_bytes) is not int or max_response_bytes <= 0:
        raise ValueError("max_response_bytes must be a positive integer")
    requests = prepare_notebook_body_requests(plan, request_prefix=request_prefix)
    plan_sha256 = hashlib.sha256(
        json.dumps(asdict(plan), sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    expected = {request.request_id for request in requests}
    by_id: dict[str, NotebookBodyRecord] = {}
    for record in records:
        if record.request_id not in expected:
            raise ValueError(f"unknown record request_id: {record.request_id}")
        if record.request_id in by_id:
            raise ValueError(f"duplicate record request_id: {record.request_id}")
        by_id[record.request_id] = record
    proposals = tuple(
        _validate_record(request, by_id.get(request.request_id), max_response_bytes)
        for request in requests
    )
    responses = tuple(proposal.response for proposal in proposals if proposal.response is not None)
    module_source = None
    if len(responses) == len(requests):
        module_source = (
            "\n\n".join(
                (*plan.imports, *(response.function_code.rstrip() for response in responses))
            )
            + "\n"
        )
    return NotebookBodyBatchReport(plan_sha256, proposals, module_source)
