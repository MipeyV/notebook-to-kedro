"""Unit tests for planning benchmark JSON serialization."""

import json
from pathlib import Path

from notebook_to_kedro.evaluation import (
    load_planning_corpus,
    planning_benchmark_to_dict,
    planning_benchmark_to_json,
    run_planning_benchmark,
)
from notebook_to_kedro.semantic import DeterministicSemanticPlanner

ROOT = Path(__file__).parents[3]
CORPUS = ROOT / "tests" / "fixtures" / "evaluation" / "planning" / "v1"


def test_planning_benchmark_serialization_includes_details_and_summary() -> None:
    case = load_planning_corpus(CORPUS)[-1]
    report = run_planning_benchmark(
        (case,),
        {"deterministic": DeterministicSemanticPlanner()},
        project_root=ROOT,
        clock=iter((4.0, 4.25)).__next__,
    )

    payload = planning_benchmark_to_dict(report)
    planners = payload["planners"]
    assert isinstance(planners, list)
    planner = planners[0]
    assert isinstance(planner, dict)
    summary = planner["summary"]
    assert isinstance(summary, dict)
    cases = planner["cases"]
    assert isinstance(cases, list)
    result = cases[0]
    assert isinstance(result, dict)
    evaluation = result["evaluation"]
    assert isinstance(evaluation, dict)

    assert payload["schema_version"] == "1.0"
    assert payload["corpus_cases"] == [
        {
            "case_id": "simple-training",
            "notebook_path": case.notebook_path,
            "source_sha256": case.source_sha256,
        }
    ]
    assert summary == {
        "case_count": 1,
        "exact_match_count": 1,
        "exact_match_rate": 1.0,
        "valid_plan_count": 1,
        "valid_plan_rate": 1.0,
        "fallback_count": 0,
        "fallback_rate": 0.0,
        "total_duration_seconds": 0.25,
        "mean_duration_seconds": 0.25,
    }
    assert result["planner_version"] == "0.1.0"
    assert evaluation["exact_match"] is True
    assert json.loads(planning_benchmark_to_json(report)) == payload
    assert planning_benchmark_to_json(report, indent=None).endswith("\n")
