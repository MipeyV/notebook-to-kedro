"""Deterministic JSON serialization for planning benchmark reports."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from notebook_to_kedro.evaluation.models import (
        PlannerBenchmark,
        PlanningBenchmarkCaseResult,
        PlanningBenchmarkReport,
    )


def planning_benchmark_to_dict(report: PlanningBenchmarkReport) -> dict[str, object]:
    """Return a JSON-compatible benchmark report dictionary."""
    return {
        "schema_version": report.schema_version,
        "corpus_cases": [asdict(case) for case in report.corpus_cases],
        "planners": [_planner_to_dict(planner) for planner in report.planners],
    }


def planning_benchmark_to_json(report: PlanningBenchmarkReport, *, indent: int | None = 2) -> str:
    """Serialize a benchmark report to deterministic JSON."""
    return (
        json.dumps(
            planning_benchmark_to_dict(report),
            indent=indent,
            ensure_ascii=True,
            sort_keys=True,
        )
        + "\n"
    )


def _planner_to_dict(planner: PlannerBenchmark) -> dict[str, object]:
    return {
        "planner_name": planner.planner_name,
        "summary": {
            "case_count": planner.case_count,
            "exact_match_count": planner.exact_match_count,
            "exact_match_rate": planner.exact_match_rate,
            "valid_plan_count": planner.valid_plan_count,
            "valid_plan_rate": planner.valid_plan_rate,
            "fallback_count": planner.fallback_count,
            "fallback_rate": planner.fallback_rate,
            "total_duration_seconds": planner.total_duration_seconds,
            "mean_duration_seconds": planner.mean_duration_seconds,
        },
        "cases": [_case_to_dict(result) for result in planner.cases],
    }


def _case_to_dict(result: PlanningBenchmarkCaseResult) -> dict[str, object]:
    return {
        "case_id": result.case_id,
        "planner_version": result.planner_version,
        "duration_seconds": result.duration_seconds,
        "plan_valid": result.plan_valid,
        "used_fallback": result.used_fallback,
        "evaluation": asdict(result.evaluation),
    }


__all__ = ["planning_benchmark_to_dict", "planning_benchmark_to_json"]
