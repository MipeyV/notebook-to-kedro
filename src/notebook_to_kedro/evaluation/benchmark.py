"""Comparable execution of semantic planners over a reviewed corpus."""

from __future__ import annotations

from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from notebook_to_kedro.api import analyze_notebook_path
from notebook_to_kedro.evaluation.models import (
    PLANNING_BENCHMARK_SCHEMA_VERSION,
    PlannerBenchmark,
    PlanningBenchmarkCaseResult,
    PlanningBenchmarkCorpusCase,
    PlanningBenchmarkReport,
)
from notebook_to_kedro.evaluation.planning import evaluate_planning_case
from notebook_to_kedro.exceptions import ConversionPlanValidationError
from notebook_to_kedro.semantic.validation import validate_conversion_plan

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from notebook_to_kedro.evaluation.models import PlanningCase
    from notebook_to_kedro.ir import ConversionPlan, NotebookFacts
    from notebook_to_kedro.semantic import SemanticPlanner

FALLBACK_DIAGNOSTIC_CODE = "SP005"


def run_planning_benchmark(
    cases: Sequence[PlanningCase],
    planners: Mapping[str, SemanticPlanner],
    *,
    project_root: str | Path = ".",
    clock: Callable[[], float] = perf_counter,
) -> PlanningBenchmarkReport:
    """Evaluate named planners over the same facts and return comparable results."""
    if not cases:
        raise ValueError("planning benchmark requires at least one case")
    if not planners:
        raise ValueError("planning benchmark requires at least one planner")
    root = Path(project_root).resolve()
    analyzed_cases = tuple(
        (
            case,
            analyze_notebook_path(root / case.notebook_path, project_root=root),
        )
        for case in cases
    )
    planner_results = tuple(
        _run_planner(planner_name, planner, analyzed_cases, clock)
        for planner_name, planner in sorted(planners.items())
    )
    return PlanningBenchmarkReport(
        schema_version=PLANNING_BENCHMARK_SCHEMA_VERSION,
        corpus_cases=tuple(
            PlanningBenchmarkCorpusCase(
                case_id=case.case_id,
                notebook_path=case.notebook_path,
                source_sha256=case.source_sha256,
            )
            for case in cases
        ),
        planners=planner_results,
    )


def _run_planner(
    planner_name: str,
    planner: SemanticPlanner,
    analyzed_cases: tuple[tuple[PlanningCase, NotebookFacts], ...],
    clock: Callable[[], float],
) -> PlannerBenchmark:
    if not planner_name:
        raise ValueError("planner name must not be empty")
    results = tuple(_run_case(case, facts, planner, clock) for case, facts in analyzed_cases)
    return PlannerBenchmark(planner_name=planner_name, cases=results)


def _run_case(
    case: PlanningCase,
    facts: NotebookFacts,
    planner: SemanticPlanner,
    clock: Callable[[], float],
) -> PlanningBenchmarkCaseResult:
    started_at = clock()
    plan = planner.create_plan(facts)
    duration_seconds = clock() - started_at
    if not isfinite(duration_seconds) or duration_seconds < 0:
        raise ValueError("benchmark clock must produce a non-negative finite duration")
    return PlanningBenchmarkCaseResult(
        case_id=case.case_id,
        planner_version=plan.planner_version,
        duration_seconds=duration_seconds,
        plan_valid=_is_valid(plan),
        used_fallback=any(
            diagnostic.code == FALLBACK_DIAGNOSTIC_CODE for diagnostic in plan.diagnostics
        ),
        evaluation=evaluate_planning_case(case, facts, plan),
    )


def _is_valid(plan: ConversionPlan) -> bool:
    try:
        validate_conversion_plan(plan)
    except ConversionPlanValidationError:
        return False
    return True


__all__ = ["FALLBACK_DIAGNOSTIC_CODE", "run_planning_benchmark"]
