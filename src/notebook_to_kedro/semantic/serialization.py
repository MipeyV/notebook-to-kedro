"""Deterministic serialization for semantic planning provider contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from notebook_to_kedro.exceptions import SemanticPlanningResponseError
from notebook_to_kedro.semantic.contracts import (
    SemanticPlanningResponse,
    SemanticTaskSuggestion,
)

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan
    from notebook_to_kedro.semantic.contracts import SemanticPlanningRequest


def _baseline_plan_to_dict(plan: ConversionPlan) -> dict[str, object]:
    return {
        "schema_version": plan.schema_version,
        "planner_version": plan.planner_version,
        "notebook_path": plan.notebook_path,
        "task_candidates": [
            {
                "id": task.id,
                "name": task.name,
                "source_cell_ids": list(task.source_cell_ids),
                "statement_ids": list(task.statement_ids),
                "inputs": list(task.inputs),
                "outputs": list(task.outputs),
                "parameters": list(task.parameters),
                "diagnostic_codes": list(task.diagnostic_codes),
            }
            for task in plan.task_candidates
        ],
        "catalog_dataset_names": [dataset.name for dataset in plan.catalog_datasets],
        "parameter_names": [parameter.name for parameter in plan.parameters],
        "blocking_diagnostic_codes": list(plan.blocking_diagnostic_codes),
        "diagnostics": [
            {
                "code": diagnostic.code,
                "severity": diagnostic.severity,
                "message": diagnostic.message,
                "task_id": diagnostic.task_id,
            }
            for diagnostic in plan.diagnostics
        ],
    }


def semantic_planning_request_to_dict(request: SemanticPlanningRequest) -> dict[str, object]:
    """Convert a request into its deterministic provider payload."""
    return {
        "schema_version": request.schema_version,
        "request_id": request.request_id,
        "prompt_version": request.prompt_version,
        "notebook_facts": request.facts.to_dict(),
        "baseline_plan": _baseline_plan_to_dict(request.baseline_plan),
    }


def semantic_planning_request_to_json(
    request: SemanticPlanningRequest, *, indent: int | None = 2
) -> str:
    """Serialize a semantic planning request with stable ordering."""
    return _to_json(semantic_planning_request_to_dict(request), indent=indent)


def _task_to_dict(task: SemanticTaskSuggestion) -> dict[str, object]:
    return {
        "source_cell_ids": list(task.source_cell_ids),
        "statement_ids": list(task.statement_ids),
        "node_name": task.node_name,
        "inputs": list(task.inputs),
        "outputs": list(task.outputs),
        "parameter_names": list(task.parameter_names),
        "pipeline_id": task.pipeline_id,
        "review_notes": list(task.review_notes),
    }


def semantic_planning_response_to_dict(response: SemanticPlanningResponse) -> dict[str, object]:
    """Convert a semantic response into its canonical JSON-compatible payload."""
    return {
        "schema_version": response.schema_version,
        "request_id": response.request_id,
        "tasks": [_task_to_dict(task) for task in response.tasks],
        "review_notes": list(response.review_notes),
    }


def semantic_planning_response_to_json(
    response: SemanticPlanningResponse, *, indent: int | None = 2
) -> str:
    """Serialize a semantic response with stable ordering."""
    return _to_json(semantic_planning_response_to_dict(response), indent=indent)


def _to_json(payload: dict[str, object], *, indent: int | None) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=indent,
        separators=(",", ":") if indent is None else None,
        sort_keys=True,
    )


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        message = f"{field_name} must be an object with string keys"
        raise TypeError(message)
    return cast("Mapping[str, object]", value)


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        message = f"{field_name} must be an array"
        raise TypeError(message)
    return cast("Sequence[object]", value)


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        message = f"{field_name} must be a string"
        raise TypeError(message)
    return value


def _exact_keys(payload: Mapping[str, object], expected: frozenset[str], field_name: str) -> None:
    actual = frozenset(payload)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    details: list[str] = []
    if missing:
        details.append(f"missing keys: {', '.join(missing)}")
    if unexpected:
        details.append(f"unexpected keys: {', '.join(unexpected)}")
    message = f"{field_name} has invalid fields ({'; '.join(details)})"
    raise ValueError(message)


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    return tuple(_string(item, f"{field_name} item") for item in _sequence(value, field_name))


def _task_from_value(value: object, index: int) -> SemanticTaskSuggestion:
    field_name = f"tasks[{index}]"
    payload = _mapping(value, field_name)
    _exact_keys(
        payload,
        frozenset(
            {
                "source_cell_ids",
                "statement_ids",
                "node_name",
                "inputs",
                "outputs",
                "parameter_names",
                "pipeline_id",
                "review_notes",
            }
        ),
        field_name,
    )
    return SemanticTaskSuggestion(
        source_cell_ids=_string_tuple(payload["source_cell_ids"], f"{field_name}.source_cell_ids"),
        statement_ids=_string_tuple(payload["statement_ids"], f"{field_name}.statement_ids"),
        node_name=_string(payload["node_name"], f"{field_name}.node_name"),
        inputs=_string_tuple(payload["inputs"], f"{field_name}.inputs"),
        outputs=_string_tuple(payload["outputs"], f"{field_name}.outputs"),
        parameter_names=_string_tuple(payload["parameter_names"], f"{field_name}.parameter_names"),
        pipeline_id=_string(payload["pipeline_id"], f"{field_name}.pipeline_id"),
        review_notes=_string_tuple(payload["review_notes"], f"{field_name}.review_notes"),
    )


def _response_from_mapping(payload: Mapping[str, object]) -> SemanticPlanningResponse:
    _exact_keys(
        payload,
        frozenset({"schema_version", "request_id", "tasks", "review_notes"}),
        "root",
    )
    return SemanticPlanningResponse(
        schema_version=_string(payload["schema_version"], "schema_version"),
        request_id=_string(payload["request_id"], "request_id"),
        tasks=tuple(
            _task_from_value(item, index)
            for index, item in enumerate(_sequence(payload["tasks"], "tasks"))
        ),
        review_notes=_string_tuple(payload["review_notes"], "review_notes"),
    )


def semantic_planning_response_from_dict(
    payload: Mapping[str, object],
) -> SemanticPlanningResponse:
    """Parse a strict decoded provider response."""
    try:
        return _response_from_mapping(_mapping(payload, "root"))
    except (TypeError, ValueError) as error:
        message = f"Invalid semantic planning response: {error}"
        raise SemanticPlanningResponseError(message) from error


def semantic_planning_response_from_json(payload: str) -> SemanticPlanningResponse:
    """Decode JSON and parse a strict provider response."""
    try:
        decoded: object = json.loads(payload)
        return _response_from_mapping(_mapping(decoded, "root"))
    except (TypeError, ValueError) as error:
        message = f"Invalid semantic planning response: {error}"
        raise SemanticPlanningResponseError(message) from error
