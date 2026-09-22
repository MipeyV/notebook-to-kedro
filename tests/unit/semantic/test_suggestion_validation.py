"""Tests for semantic suggestion validation against deterministic facts."""

from dataclasses import replace

import pytest

from notebook_to_kedro.exceptions import SemanticPlanningResponseError
from notebook_to_kedro.semantic import (
    SemanticPlanningRequest,
    SemanticPlanningResponse,
    SemanticTaskSuggestion,
    validate_semantic_planning_response,
)


def test_validation_accepts_a_fact_preserving_response(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    validate_semantic_planning_response(semantic_request, semantic_response)


def test_validation_rejects_invented_dropped_and_misattributed_facts(
    semantic_request: SemanticPlanningRequest,
) -> None:
    baseline_tasks = semantic_request.baseline_plan.task_candidates
    first = baseline_tasks[0]
    second = baseline_tasks[1]
    response = SemanticPlanningResponse(
        schema_version="1.0",
        request_id="wrong-request",
        tasks=(
            SemanticTaskSuggestion(
                source_cell_ids=(first.source_cell_ids[0], "cell-9999"),
                statement_ids=(second.statement_ids[0], "statement-9999"),
                node_name="invalid_boundaries",
                inputs=("invented_input",),
                outputs=("invented_output",),
                parameter_names=(
                    semantic_request.baseline_plan.parameters[0].name,
                    "invented.parameter",
                ),
                pipeline_id="notebook_pipeline",
            ),
            SemanticTaskSuggestion(
                source_cell_ids=second.source_cell_ids,
                statement_ids=(second.statement_ids[0],),
                node_name="duplicate_statement",
                inputs=second.inputs,
                outputs=second.outputs,
                parameter_names=(),
                pipeline_id="notebook_pipeline",
            ),
        ),
    )

    with pytest.raises(SemanticPlanningResponseError) as error_info:
        validate_semantic_planning_response(semantic_request, response)

    message = str(error_info.value)
    assert "response request_id does not match" in message
    assert "unknown cell: cell-9999" in message
    assert "unknown statement: statement-9999" in message
    assert "is not in its source cells" in message
    assert "source cell has no selected statement" in message
    assert "unsupported input: invented_input" in message
    assert "unsupported output: invented_output" in message
    assert "references unknown parameter: invented.parameter" in message
    assert "does not belong to its source cells" in message
    assert "statement is assigned to multiple tasks" in message
    assert "baseline statement is missing" in message
    assert "suggestion contains a non-baseline statement" in message


def test_validation_reports_an_empty_response_when_baseline_has_tasks(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    response = replace(semantic_response, tasks=())

    with pytest.raises(SemanticPlanningResponseError, match="baseline statement is missing"):
        validate_semantic_planning_response(semantic_request, response)
