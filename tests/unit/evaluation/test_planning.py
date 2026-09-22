"""Unit tests for planning evaluation metrics."""

from dataclasses import replace
from pathlib import Path

from notebook_to_kedro import analyze_notebook_path, plan_notebook_path
from notebook_to_kedro.evaluation import evaluate_planning_case, load_planning_case

CORPUS = Path(__file__).parents[2] / "fixtures" / "evaluation" / "planning" / "v1"


def test_evaluate_planning_case_scores_exact_plan() -> None:
    case = load_planning_case(CORPUS / "simple_training.json")
    facts = analyze_notebook_path(case.notebook_path)
    plan = plan_notebook_path(case.notebook_path)

    evaluation = evaluate_planning_case(case, facts, plan)

    assert evaluation.exact_match is True
    assert evaluation.matched_task_count == evaluation.expected_task_count
    assert evaluation.boundary_precision == 1.0
    assert evaluation.boundary_recall == 1.0
    assert evaluation.task_id_accuracy == 1.0
    assert evaluation.node_name_accuracy == 1.0
    assert evaluation.raw_source_accuracy == 1.0
    assert evaluation.input_accuracy == 1.0
    assert evaluation.output_accuracy == 1.0
    assert evaluation.parameter_accuracy == 1.0
    assert evaluation.diagnostic_accuracy == 1.0
    assert evaluation.pipeline_accuracy == 1.0


def test_evaluate_planning_case_exposes_dimension_level_mismatches() -> None:
    case = load_planning_case(CORPUS / "file_backed_training.json")
    facts = analyze_notebook_path(case.notebook_path)
    plan = plan_notebook_path(case.notebook_path)
    first_task = plan.task_candidates[0]
    changed_task = replace(
        first_task,
        id="wrong-task",
        name="wrong_name",
        inputs=("wrong_input",),
        outputs=("wrong_output",),
        source="wrong_source",
        parameters=("wrong.parameter",),
        diagnostic_codes=("WRONG",),
    )
    changed_plan = replace(
        plan,
        notebook_path="wrong.ipynb",
        task_candidates=(changed_task,),
        catalog_datasets=(),
        parameters=(),
        blocking_diagnostic_codes=("WRONG",),
    )
    changed_facts = replace(
        facts,
        notebook=replace(facts.notebook, content_sha256="0" * 64),
    )

    evaluation = evaluate_planning_case(
        case,
        changed_facts,
        changed_plan,
        pipeline_ids={changed_task.id: "wrong_pipeline"},
    )

    assert evaluation.exact_match is False
    assert evaluation.source_identity_match is False
    assert evaluation.matched_task_count == 1
    assert evaluation.boundary_precision == 1.0
    assert evaluation.boundary_recall == 0.2
    assert evaluation.task_id_accuracy == 0.0
    assert evaluation.node_name_accuracy == 0.0
    assert evaluation.raw_source_accuracy == 0.0
    assert evaluation.input_accuracy == 0.0
    assert evaluation.output_accuracy == 0.0
    assert evaluation.parameter_accuracy == 0.0
    assert evaluation.diagnostic_accuracy == 0.0
    assert evaluation.pipeline_accuracy == 0.0
    assert evaluation.catalog_exact_match is False
    assert evaluation.parameter_names_exact_match is False
    assert evaluation.blocking_diagnostics_exact_match is False


def test_evaluate_planning_case_scores_missing_tasks() -> None:
    case = load_planning_case(CORPUS / "simple_training.json")
    facts = analyze_notebook_path(case.notebook_path)
    plan = replace(plan_notebook_path(case.notebook_path), task_candidates=())

    evaluation = evaluate_planning_case(case, facts, plan)

    assert evaluation.exact_match is False
    assert evaluation.predicted_task_count == 0
    assert evaluation.matched_task_count == 0
    assert evaluation.boundary_precision == 0.0
    assert evaluation.boundary_recall == 0.0
    assert evaluation.node_name_accuracy == 0.0
