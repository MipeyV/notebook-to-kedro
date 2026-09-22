"""Deterministic serialization for planning evaluation cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from notebook_to_kedro.evaluation.models import ExpectedTask, PlanningCase

CASE_KEYS = frozenset(
    {
        "schema_version",
        "case_id",
        "notebook_path",
        "source_sha256",
        "review_status",
        "tasks",
        "expected_catalog_datasets",
        "expected_parameter_names",
        "expected_blocking_diagnostic_codes",
    }
)
TASK_KEYS = frozenset(
    {
        "id",
        "expected_pipeline_id",
        "source_cell_ids",
        "statement_ids",
        "raw_source",
        "expected_node_name",
        "expected_inputs",
        "expected_outputs",
        "expected_parameters",
        "expected_diagnostic_codes",
    }
)


def planning_case_to_dict(case: PlanningCase) -> dict[str, object]:
    """Return a canonical JSON-compatible planning case dictionary."""
    return {
        "schema_version": case.schema_version,
        "case_id": case.case_id,
        "notebook_path": case.notebook_path,
        "source_sha256": case.source_sha256,
        "review_status": case.review_status,
        "tasks": [_expected_task_to_dict(task) for task in case.tasks],
        "expected_catalog_datasets": list(case.expected_catalog_datasets),
        "expected_parameter_names": list(case.expected_parameter_names),
        "expected_blocking_diagnostic_codes": list(case.expected_blocking_diagnostic_codes),
    }


def planning_case_to_json(case: PlanningCase, *, indent: int | None = 2) -> str:
    """Serialize a planning case to deterministic JSON."""
    return json.dumps(planning_case_to_dict(case), indent=indent, ensure_ascii=True) + "\n"


def planning_case_from_dict(payload: object) -> PlanningCase:
    """Validate and reconstruct a planning case from decoded JSON."""
    data = _object(payload, "planning case")
    _require_exact_keys(data, CASE_KEYS, "planning case")
    tasks_value = _required(data, "tasks")
    if not isinstance(tasks_value, list):
        msg = "planning case tasks must be an array"
        raise ValueError(msg)
    review_status = _string(_required(data, "review_status"), "review_status")
    if review_status != "approved":
        msg = "review_status must be 'approved'"
        raise ValueError(msg)
    return PlanningCase(
        schema_version=_string(_required(data, "schema_version"), "schema_version"),
        case_id=_string(_required(data, "case_id"), "case_id"),
        notebook_path=_string(_required(data, "notebook_path"), "notebook_path"),
        source_sha256=_string(_required(data, "source_sha256"), "source_sha256"),
        review_status="approved",
        tasks=tuple(_expected_task_from_dict(item) for item in tasks_value),
        expected_catalog_datasets=_string_tuple(
            _required(data, "expected_catalog_datasets"),
            "expected_catalog_datasets",
        ),
        expected_parameter_names=_string_tuple(
            _required(data, "expected_parameter_names"),
            "expected_parameter_names",
        ),
        expected_blocking_diagnostic_codes=_string_tuple(
            _required(data, "expected_blocking_diagnostic_codes"),
            "expected_blocking_diagnostic_codes",
        ),
    )


def planning_case_from_json(payload: str) -> PlanningCase:
    """Validate and reconstruct a planning case from JSON text."""
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as error:
        msg = f"invalid planning case JSON: {error.msg}"
        raise ValueError(msg) from error
    return planning_case_from_dict(decoded)


def load_planning_case(path: str | Path) -> PlanningCase:
    """Load one planning evaluation case from disk."""
    case_path = Path(path)
    try:
        payload = case_path.read_text(encoding="utf-8")
    except OSError as error:
        msg = f"cannot read planning case {case_path}: {error}"
        raise ValueError(msg) from error
    return planning_case_from_json(payload)


def load_planning_corpus(directory: str | Path) -> tuple[PlanningCase, ...]:
    """Load all planning cases in deterministic filename order."""
    corpus_path = Path(directory)
    paths = tuple(sorted(corpus_path.glob("*.json")))
    if not paths:
        msg = f"planning corpus contains no JSON cases: {corpus_path}"
        raise ValueError(msg)
    cases = tuple(load_planning_case(path) for path in paths)
    case_ids = tuple(case.case_id for case in cases)
    if len(case_ids) != len(set(case_ids)):
        msg = "planning corpus case IDs must be unique"
        raise ValueError(msg)
    return cases


def _expected_task_to_dict(task: ExpectedTask) -> dict[str, object]:
    return {
        "id": task.id,
        "expected_pipeline_id": task.expected_pipeline_id,
        "source_cell_ids": list(task.source_cell_ids),
        "statement_ids": list(task.statement_ids),
        "raw_source": task.raw_source,
        "expected_node_name": task.expected_node_name,
        "expected_inputs": list(task.expected_inputs),
        "expected_outputs": list(task.expected_outputs),
        "expected_parameters": list(task.expected_parameters),
        "expected_diagnostic_codes": list(task.expected_diagnostic_codes),
    }


def _expected_task_from_dict(payload: object) -> ExpectedTask:
    data = _object(payload, "expected task")
    _require_exact_keys(data, TASK_KEYS, "expected task")
    return ExpectedTask(
        id=_string(_required(data, "id"), "task id"),
        expected_pipeline_id=_string(
            _required(data, "expected_pipeline_id"),
            "expected_pipeline_id",
        ),
        source_cell_ids=_string_tuple(_required(data, "source_cell_ids"), "source_cell_ids"),
        statement_ids=_string_tuple(_required(data, "statement_ids"), "statement_ids"),
        raw_source=_string(_required(data, "raw_source"), "raw_source"),
        expected_node_name=_string(
            _required(data, "expected_node_name"),
            "expected_node_name",
        ),
        expected_inputs=_string_tuple(_required(data, "expected_inputs"), "expected_inputs"),
        expected_outputs=_string_tuple(_required(data, "expected_outputs"), "expected_outputs"),
        expected_parameters=_string_tuple(
            _required(data, "expected_parameters"),
            "expected_parameters",
        ),
        expected_diagnostic_codes=_string_tuple(
            _required(data, "expected_diagnostic_codes"),
            "expected_diagnostic_codes",
        ),
    )


def _object(payload: object, label: str) -> dict[str, object]:
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        msg = f"{label} must be an object with string keys"
        raise ValueError(msg)
    return cast("dict[str, object]", payload)


def _required(data: dict[str, object], key: str) -> object:
    return data[key]


def _require_exact_keys(data: dict[str, object], expected: frozenset[str], label: str) -> None:
    actual = frozenset(data)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        msg = f"invalid {label} fields; missing={missing}, unexpected={unexpected}"
        raise ValueError(msg)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        msg = f"{label} must be a string"
        raise ValueError(msg)
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = f"{label} must be an array of strings"
        raise ValueError(msg)
    return tuple(value)
