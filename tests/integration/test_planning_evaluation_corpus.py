"""Integration coverage for the reviewed V1 planning corpus."""

from pathlib import Path

from notebook_to_kedro import analyze_notebook_path, plan_notebook_path
from notebook_to_kedro.evaluation import evaluate_planning_case, load_planning_corpus

CORPUS = Path(__file__).parents[1] / "fixtures" / "evaluation" / "planning" / "v1"


def test_deterministic_planner_matches_reviewed_v1_corpus() -> None:
    cases = load_planning_corpus(CORPUS)

    evaluations = tuple(
        evaluate_planning_case(
            case,
            analyze_notebook_path(case.notebook_path),
            plan_notebook_path(case.notebook_path),
        )
        for case in cases
    )

    assert len(evaluations) == 4
    assert all(evaluation.exact_match for evaluation in evaluations)
