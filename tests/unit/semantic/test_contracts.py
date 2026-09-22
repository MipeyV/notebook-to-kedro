"""Tests for versioned semantic planning contracts."""

from dataclasses import replace

import pytest

from notebook_to_kedro.semantic import (
    SemanticPlanningRequest,
    SemanticPlanningResponse,
    SemanticPlanningResult,
    SemanticPlanningTrace,
    SemanticTaskSuggestion,
)


def _task(**overrides: object) -> SemanticTaskSuggestion:
    values: dict[str, object] = {
        "source_cell_ids": ("cell-0001",),
        "statement_ids": ("cell-0001-stmt-0000",),
        "node_name": "prepare_data",
        "inputs": ("raw_data",),
        "outputs": ("clean_data",),
        "parameter_names": ("prepare_data.columns",),
        "pipeline_id": "data_processing",
        "review_notes": ("Grouped from one source cell.",),
    }
    values.update(overrides)
    return SemanticTaskSuggestion(**values)  # type: ignore[arg-type]


def test_request_and_response_contracts_accept_valid_values(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    trace = SemanticPlanningTrace(
        request_id=semantic_request.request_id,
        prompt_version=semantic_request.prompt_version,
        provider_name="fake",
        model_name="fixed-response",
    )

    result = SemanticPlanningResult(semantic_request, semantic_response, trace)

    assert result.response.tasks


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": "2.0"}, "schema_version must be '1.0'"),
        ({"request_id": ""}, "request_id must not be empty"),
        ({"prompt_version": ""}, "prompt_version must not be empty"),
    ],
)
def test_request_rejects_invalid_identity_fields(
    semantic_request: SemanticPlanningRequest,
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(semantic_request, **changes)  # type: ignore[arg-type]


def test_request_rejects_a_baseline_for_another_notebook(
    semantic_request: SemanticPlanningRequest,
) -> None:
    plan = replace(semantic_request.baseline_plan, notebook_path="other.ipynb")

    with pytest.raises(ValueError, match="baseline_plan notebook path must match"):
        replace(semantic_request, baseline_plan=plan)


@pytest.mark.parametrize("field_name", ["source_cell_ids", "statement_ids"])
def test_task_rejects_empty_source_boundaries(field_name: str) -> None:
    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        _task(**{field_name: ()})


@pytest.mark.parametrize(
    "field_name",
    [
        "source_cell_ids",
        "statement_ids",
        "inputs",
        "outputs",
        "parameter_names",
        "review_notes",
    ],
)
def test_task_rejects_empty_collection_items(field_name: str) -> None:
    with pytest.raises(ValueError, match=f"{field_name} must not contain empty values"):
        _task(**{field_name: ("",)})


@pytest.mark.parametrize(
    "field_name",
    [
        "source_cell_ids",
        "statement_ids",
        "inputs",
        "outputs",
        "parameter_names",
        "review_notes",
    ],
)
def test_task_rejects_duplicate_collection_items(field_name: str) -> None:
    with pytest.raises(ValueError, match=f"{field_name} must contain unique values"):
        _task(**{field_name: ("duplicate", "duplicate")})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("node_name", "bad-name"), ("node_name", "class"), ("pipeline_id", "bad pipeline")],
)
def test_task_rejects_invalid_identifiers(field_name: str, value: str) -> None:
    with pytest.raises(ValueError, match="public ASCII Python identifier"):
        _task(**{field_name: value})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": "2.0"}, "schema_version must be '1.0'"),
        ({"request_id": ""}, "request_id must not be empty"),
        ({"review_notes": ("",)}, "review_notes must not contain empty values"),
        (
            {"tasks": (_task(), _task(source_cell_ids=("cell-0002",)))},
            "task node names must be unique",
        ),
    ],
)
def test_response_rejects_invalid_values(
    semantic_response: SemanticPlanningResponse,
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(semantic_response, **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field_name", ["request_id", "prompt_version", "provider_name", "model_name"]
)
def test_trace_rejects_empty_identity_fields(field_name: str) -> None:
    values = {
        "request_id": "request-0001",
        "prompt_version": "planning-v1",
        "provider_name": "fake",
        "model_name": "fixed-response",
    }
    values[field_name] = ""

    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        SemanticPlanningTrace(**values)


def test_result_rejects_mismatched_request_ids(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    trace = SemanticPlanningTrace(
        request_id="other-request",
        prompt_version=semantic_request.prompt_version,
        provider_name="fake",
        model_name="fixed-response",
    )

    with pytest.raises(ValueError, match="request IDs must match"):
        SemanticPlanningResult(semantic_request, semantic_response, trace)


def test_result_rejects_mismatched_prompt_versions(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    trace = SemanticPlanningTrace(
        request_id=semantic_request.request_id,
        prompt_version="other-prompt",
        provider_name="fake",
        model_name="fixed-response",
    )

    with pytest.raises(ValueError, match="prompt_version must match"):
        SemanticPlanningResult(semantic_request, semantic_response, trace)
