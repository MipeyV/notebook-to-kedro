"""Integration coverage for the reviewed semantic planning corpus."""

from pathlib import Path

import pytest

from notebook_to_kedro import analyze_notebook_path, plan_notebook_path
from notebook_to_kedro.evaluation import evaluate_planning_case, load_planning_corpus
from notebook_to_kedro.semantic import (
    SEMANTIC_GROUPING_SCHEMA_VERSION,
    FakeSemanticPlanningProvider,
    HybridSemanticPlanner,
    SemanticGroupingResponse,
    SemanticTaskGroup,
)

CORPUS = Path(__file__).parents[1] / "fixtures" / "evaluation" / "planning" / "semantic-v1"


def test_deterministic_planner_exposes_the_semantic_grouping_gap() -> None:
    cases = load_planning_corpus(CORPUS)
    evaluations = {
        case.case_id: evaluate_planning_case(
            case,
            analyze_notebook_path(case.notebook_path),
            plan_notebook_path(case.notebook_path),
        )
        for case in cases
    }

    assert tuple(evaluations) == (
        "file-backed-training",
        "pandas-preprocessing-training",
        "scaled-training",
        "simple-training",
        "statement-split-model-comparison",
        "statement-split-scaling",
        "statement-split-training",
    )
    for case_id in (
        "file-backed-training",
        "pandas-preprocessing-training",
        "scaled-training",
        "simple-training",
    ):
        assert evaluations[case_id].exact_match is True

    expected_challenges = {
        "statement-split-model-comparison": (8, 15, 3, 1 / 5, 3 / 8),
        "statement-split-scaling": (7, 15, 2, 2 / 15, 2 / 7),
        "statement-split-training": (6, 12, 2, 1 / 6, 1 / 3),
    }
    for case_id, expected in expected_challenges.items():
        challenge = evaluations[case_id]
        expected_tasks, predicted_tasks, matched_tasks, precision, recall = expected
        assert challenge.exact_match is False
        assert challenge.expected_task_count == expected_tasks
        assert challenge.predicted_task_count == predicted_tasks
        assert challenge.matched_task_count == matched_tasks
        assert challenge.boundary_precision == pytest.approx(precision)
        assert challenge.boundary_recall == pytest.approx(recall)


def test_reviewed_semantic_boundaries_are_accepted_by_hybrid_assembly() -> None:
    for case in load_planning_corpus(CORPUS):
        facts = analyze_notebook_path(case.notebook_path)
        baseline = plan_notebook_path(case.notebook_path)
        response = SemanticGroupingResponse(
            schema_version=SEMANTIC_GROUPING_SCHEMA_VERSION,
            request_id=f"planning-{facts.notebook.content_sha256[:16]}",
            groups=tuple(
                SemanticTaskGroup(
                    tuple(
                        task.id
                        for task in baseline.task_candidates
                        if set(task.statement_ids) <= set(expected.statement_ids)
                    )
                )
                for expected in case.tasks
            ),
        )
        provider = FakeSemanticPlanningProvider(response_json=response.to_json())

        plan = HybridSemanticPlanner(provider).create_plan(facts)
        evaluation = evaluate_planning_case(case, facts, plan)

        assert evaluation.exact_match is True, case.case_id
        assert plan.planner_version == "0.2.0-hybrid"
