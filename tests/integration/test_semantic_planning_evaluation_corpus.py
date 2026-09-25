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
        "pandas-preprocessing-training",
        "simple-training",
        "statement-split-training",
    )
    assert evaluations["pandas-preprocessing-training"].exact_match is True
    assert evaluations["simple-training"].exact_match is True

    challenge = evaluations["statement-split-training"]
    assert challenge.exact_match is False
    assert challenge.expected_task_count == 6
    assert challenge.predicted_task_count == 12
    assert challenge.matched_task_count == 2
    assert challenge.boundary_precision == pytest.approx(1 / 6)
    assert challenge.boundary_recall == pytest.approx(1 / 3)


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
