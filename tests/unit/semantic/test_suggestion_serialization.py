"""Tests for semantic planning JSON serialization."""

import json
from typing import cast

import pytest

from notebook_to_kedro.exceptions import SemanticPlanningResponseError
from notebook_to_kedro.semantic import (
    SEMANTIC_PLANNING_RESPONSE_JSON_SCHEMA,
    SemanticPlanningRequest,
    SemanticPlanningResponse,
    semantic_planning_response_from_dict,
    semantic_planning_response_from_json,
)


def test_request_serialization_projects_facts_and_baseline_plan(
    semantic_request: SemanticPlanningRequest,
) -> None:
    payload = semantic_request.to_dict()
    compact = semantic_request.to_json(indent=None)

    assert payload["notebook_facts"] == semantic_request.facts.to_dict()
    assert payload["baseline_plan"] == {
        "schema_version": "1.0",
        "planner_version": "0.1.0",
        "notebook_path": "tests/fixtures/notebooks/simple_training.ipynb",
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
            for task in semantic_request.baseline_plan.task_candidates
        ],
        "catalog_dataset_names": [],
        "parameter_names": [
            parameter.name for parameter in semantic_request.baseline_plan.parameters
        ],
        "blocking_diagnostic_codes": [],
        "diagnostics": [
            {
                "code": diagnostic.code,
                "severity": diagnostic.severity,
                "message": diagnostic.message,
                "task_id": diagnostic.task_id,
            }
            for diagnostic in semantic_request.baseline_plan.diagnostics
        ],
    }
    assert json.loads(compact) == payload
    assert ": " not in compact


def test_response_round_trips_through_dict_and_json(
    semantic_response: SemanticPlanningResponse,
) -> None:
    payload = semantic_response.to_dict()
    formatted = semantic_response.to_json()

    assert SemanticPlanningResponse.from_dict(payload) == semantic_response
    assert SemanticPlanningResponse.from_json(formatted) == semantic_response
    assert semantic_planning_response_from_dict(payload) == semantic_response
    assert semantic_planning_response_from_json(formatted) == semantic_response
    assert formatted == semantic_response.to_json()


def test_response_schema_is_strict_and_versioned() -> None:
    properties = cast("dict[str, object]", SEMANTIC_PLANNING_RESPONSE_JSON_SCHEMA["properties"])
    tasks = cast("dict[str, object]", properties["tasks"])
    task = cast("dict[str, object]", tasks["items"])

    assert SEMANTIC_PLANNING_RESPONSE_JSON_SCHEMA["additionalProperties"] is False
    assert task["additionalProperties"] is False
    assert properties["schema_version"] == {"type": "string", "const": "1.0"}


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not an object", "root must be an object"),
        (
            {"schema_version": "1.0", "request_id": "id", "tasks": []},
            "missing keys: review_notes",
        ),
        (
            {
                "schema_version": "1.0",
                "request_id": "id",
                "tasks": [],
                "review_notes": [],
                "extra": True,
            },
            "unexpected keys: extra",
        ),
        (
            {
                "schema_version": "1.0",
                "request_id": "id",
                "tasks": "invalid",
                "review_notes": [],
            },
            "tasks must be an array",
        ),
        (
            {
                "schema_version": "1.0",
                "request_id": 1,
                "tasks": [],
                "review_notes": [],
            },
            "request_id must be a string",
        ),
        (
            {
                "schema_version": "1.0",
                "request_id": "id",
                "tasks": ["invalid"],
                "review_notes": [],
            },
            r"tasks\[0\] must be an object",
        ),
    ],
)
def test_response_parser_rejects_invalid_payloads(payload: object, message: str) -> None:
    with pytest.raises(SemanticPlanningResponseError, match=message):
        semantic_planning_response_from_dict(cast("dict[str, object]", payload))


def test_response_parser_reports_missing_and_unexpected_task_fields(
    semantic_response: SemanticPlanningResponse,
) -> None:
    payload = semantic_response.to_dict()
    task = cast("dict[str, object]", cast("list[object]", payload["tasks"])[0])
    task.pop("pipeline_id")
    task["extra"] = True

    with pytest.raises(SemanticPlanningResponseError) as error_info:
        semantic_planning_response_from_dict(payload)

    assert "missing keys: pipeline_id" in str(error_info.value)
    assert "unexpected keys: extra" in str(error_info.value)


def test_response_parser_rejects_non_string_array_items(
    semantic_response: SemanticPlanningResponse,
) -> None:
    payload = semantic_response.to_dict()
    task = cast("dict[str, object]", cast("list[object]", payload["tasks"])[0])
    task["inputs"] = [1]

    with pytest.raises(SemanticPlanningResponseError, match="inputs item must be a string"):
        semantic_planning_response_from_dict(payload)


def test_response_json_parser_rejects_invalid_json() -> None:
    with pytest.raises(SemanticPlanningResponseError, match="Invalid semantic planning response"):
        semantic_planning_response_from_json("{")


def test_response_deserialization_rejects_subclasses(
    semantic_response: SemanticPlanningResponse,
) -> None:
    class SpecializedResponse(SemanticPlanningResponse):
        pass

    with pytest.raises(TypeError, match="does not support subclasses"):
        SpecializedResponse.from_dict(semantic_response.to_dict())
    with pytest.raises(TypeError, match="does not support subclasses"):
        SpecializedResponse.from_json(semantic_response.to_json())
