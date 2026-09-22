"""Planning evaluation against reviewed notebook cases."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notebook_to_kedro.evaluation.models import ExpectedTask, PlanningCase, PlanningEvaluation

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from notebook_to_kedro.ir import ConversionPlan, NotebookFacts, TaskCandidate

DEFAULT_PIPELINE_ID = "notebook_pipeline"


def evaluate_planning_case(
    case: PlanningCase,
    facts: NotebookFacts,
    plan: ConversionPlan,
    *,
    pipeline_ids: Mapping[str, str] | None = None,
) -> PlanningEvaluation:
    """Compare a proposed conversion plan with one reviewed planning case."""
    predicted_by_boundary = {_task_boundary(task): task for task in plan.task_candidates}
    matched = tuple(
        (expected, predicted_by_boundary[expected.boundary])
        for expected in case.tasks
        if expected.boundary in predicted_by_boundary
    )
    matched_count = len(matched)
    expected_count = len(case.tasks)
    predicted_count = len(plan.task_candidates)
    boundary_precision = _ratio(matched_count, predicted_count)
    boundary_recall = _ratio(matched_count, expected_count)
    resolved_pipeline_ids = pipeline_ids or {}
    task_id_accuracy = _accuracy(matched, lambda expected, task: expected.id == task.id)
    node_name_accuracy = _accuracy(
        matched, lambda expected, task: expected.expected_node_name == task.name
    )
    raw_source_accuracy = _accuracy(
        matched, lambda expected, task: expected.raw_source == task.source
    )
    input_accuracy = _accuracy(
        matched, lambda expected, task: expected.expected_inputs == task.inputs
    )
    output_accuracy = _accuracy(
        matched, lambda expected, task: expected.expected_outputs == task.outputs
    )
    parameter_accuracy = _accuracy(
        matched,
        lambda expected, task: expected.expected_parameters == task.parameters,
    )
    diagnostic_accuracy = _accuracy(
        matched,
        lambda expected, task: expected.expected_diagnostic_codes == task.diagnostic_codes,
    )
    pipeline_accuracy = _accuracy(
        matched,
        lambda expected, task: (
            expected.expected_pipeline_id == resolved_pipeline_ids.get(task.id, DEFAULT_PIPELINE_ID)
        ),
    )
    source_identity_match = (
        facts.notebook.path == case.notebook_path
        and facts.notebook.content_sha256 == case.source_sha256
        and plan.notebook_path == case.notebook_path
    )
    catalog_exact_match = (
        tuple(dataset.name for dataset in plan.catalog_datasets) == case.expected_catalog_datasets
    )
    parameter_names_exact_match = (
        tuple(parameter.name for parameter in plan.parameters) == case.expected_parameter_names
    )
    blocking_diagnostics_exact_match = (
        plan.blocking_diagnostic_codes == case.expected_blocking_diagnostic_codes
    )
    exact_match = (
        source_identity_match
        and expected_count == predicted_count == matched_count
        and all(
            accuracy == 1.0
            for accuracy in (
                task_id_accuracy,
                node_name_accuracy,
                raw_source_accuracy,
                input_accuracy,
                output_accuracy,
                parameter_accuracy,
                diagnostic_accuracy,
                pipeline_accuracy,
            )
        )
        and catalog_exact_match
        and parameter_names_exact_match
        and blocking_diagnostics_exact_match
    )
    return PlanningEvaluation(
        case_id=case.case_id,
        source_identity_match=source_identity_match,
        expected_task_count=expected_count,
        predicted_task_count=predicted_count,
        matched_task_count=matched_count,
        boundary_precision=boundary_precision,
        boundary_recall=boundary_recall,
        task_id_accuracy=task_id_accuracy,
        node_name_accuracy=node_name_accuracy,
        raw_source_accuracy=raw_source_accuracy,
        input_accuracy=input_accuracy,
        output_accuracy=output_accuracy,
        parameter_accuracy=parameter_accuracy,
        diagnostic_accuracy=diagnostic_accuracy,
        pipeline_accuracy=pipeline_accuracy,
        catalog_exact_match=catalog_exact_match,
        parameter_names_exact_match=parameter_names_exact_match,
        blocking_diagnostics_exact_match=blocking_diagnostics_exact_match,
        exact_match=exact_match,
    )


def _task_boundary(task: TaskCandidate) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return task.source_cell_ids, task.statement_ids


def _accuracy(
    matched: tuple[tuple[ExpectedTask, TaskCandidate], ...],
    predicate: Callable[[ExpectedTask, TaskCandidate], bool],
) -> float:
    if not matched:
        return 0.0
    return sum(predicate(expected, task) for expected, task in matched) / len(matched)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
