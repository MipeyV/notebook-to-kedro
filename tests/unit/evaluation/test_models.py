"""Unit tests for planning evaluation contracts."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from notebook_to_kedro.evaluation import ExpectedTask, PlanningCase

TaskMutation = Callable[[ExpectedTask], ExpectedTask]
CaseMutation = Callable[[PlanningCase], PlanningCase]


def _task() -> ExpectedTask:
    return ExpectedTask(
        id="task-0001",
        expected_pipeline_id="notebook_pipeline",
        source_cell_ids=("cell-0001",),
        statement_ids=("cell-0001-stmt-0000",),
        raw_source="result = source + 1",
        expected_node_name="transform_data",
        expected_inputs=("source",),
        expected_outputs=("result",),
        expected_parameters=("transform_data.increment",),
        expected_diagnostic_codes=("DF001",),
    )


def _case() -> PlanningCase:
    return PlanningCase(
        schema_version="1.0",
        case_id="reviewed-case",
        notebook_path="tests/fixtures/notebooks/reviewed.ipynb",
        source_sha256="a" * 64,
        review_status="approved",
        tasks=(_task(),),
        expected_catalog_datasets=("source",),
        expected_parameter_names=("transform_data.increment",),
        expected_blocking_diagnostic_codes=("PY001",),
    )


def test_expected_task_exposes_stable_boundary() -> None:
    task = _task()

    assert task.boundary == (task.source_cell_ids, task.statement_ids)


TASK_MUTATIONS: list[tuple[TaskMutation, str]] = [
    (lambda task: replace(task, id=""), "task id must not be empty"),
    (
        lambda task: replace(task, expected_pipeline_id=""),
        "expected pipeline id must not be empty",
    ),
    (lambda task: replace(task, raw_source=""), "raw source must not be empty"),
    (lambda task: replace(task, expected_node_name=""), "expected node name must not be empty"),
    (lambda task: replace(task, source_cell_ids=()), "at least one source cell"),
    (lambda task: replace(task, statement_ids=()), "at least one statement"),
    (
        lambda task: replace(task, source_cell_ids=("cell", "cell")),
        "source cell IDs must be unique",
    ),
    (
        lambda task: replace(task, statement_ids=("statement", "statement")),
        "statement IDs must be unique",
    ),
    (
        lambda task: replace(task, expected_inputs=("input", "input")),
        "expected inputs must be unique",
    ),
    (
        lambda task: replace(task, expected_outputs=("output", "output")),
        "expected outputs must be unique",
    ),
    (
        lambda task: replace(task, expected_parameters=("parameter", "parameter")),
        "expected parameters must be unique",
    ),
    (
        lambda task: replace(task, expected_diagnostic_codes=("code", "code")),
        "expected diagnostic codes must be unique",
    ),
]


@pytest.mark.parametrize(("mutate", "message"), TASK_MUTATIONS)
def test_expected_task_rejects_invalid_fields(mutate: TaskMutation, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        mutate(_task())


CASE_MUTATIONS: list[tuple[CaseMutation, str]] = [
    (
        lambda case: replace(case, schema_version="2.0"),
        "unsupported planning case schema version",
    ),
    (lambda case: replace(case, case_id=""), "case id must not be empty"),
    (lambda case: replace(case, notebook_path=""), "notebook path must not be empty"),
    (lambda case: replace(case, source_sha256="short"), "64-character hexadecimal"),
    (lambda case: replace(case, source_sha256="g" * 64), "64-character hexadecimal"),
    (
        lambda case: replace(case, review_status="pending"),
        "must be explicitly approved",
    ),
    (lambda case: replace(case, tasks=()), "at least one expected task"),
    (
        lambda case: replace(
            case,
            tasks=(
                _task(),
                replace(
                    _task(),
                    source_cell_ids=("cell-0002",),
                    statement_ids=("cell-0002-stmt-0000",),
                ),
            ),
        ),
        "task IDs must be unique",
    ),
    (
        lambda case: replace(case, tasks=(_task(), replace(_task(), id="task-0002"))),
        "task boundaries must be unique",
    ),
    (
        lambda case: replace(case, expected_catalog_datasets=("dataset", "dataset")),
        "expected catalog datasets must be unique",
    ),
    (
        lambda case: replace(case, expected_parameter_names=("parameter", "parameter")),
        "expected parameter names must be unique",
    ),
    (
        lambda case: replace(
            case,
            expected_blocking_diagnostic_codes=("code", "code"),
        ),
        "expected blocking diagnostic codes must be unique",
    ),
]


@pytest.mark.parametrize(("mutate", "message"), CASE_MUTATIONS)
def test_planning_case_rejects_invalid_fields(mutate: CaseMutation, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        mutate(_case())
