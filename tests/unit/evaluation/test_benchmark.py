"""Unit tests for comparative planning benchmarks."""

from dataclasses import replace
from math import nan
from pathlib import Path

import pytest

from notebook_to_kedro.evaluation import (
    PLANNING_BENCHMARK_SCHEMA_VERSION,
    PlannerBenchmark,
    PlanningBenchmarkCorpusCase,
    PlanningBenchmarkReport,
    load_planning_corpus,
    run_planning_benchmark,
)
from notebook_to_kedro.ir import PlanDiagnostic
from notebook_to_kedro.semantic import DeterministicSemanticPlanner, plan_tasks

ROOT = Path(__file__).parents[3]
CORPUS = ROOT / "tests" / "fixtures" / "evaluation" / "planning" / "v1"


class _FallbackPlanner:
    def __init__(self) -> None:
        self.received_facts: list[object] = []

    def create_plan(self, facts):  # type: ignore[no-untyped-def]
        self.received_facts.append(facts)
        baseline = plan_tasks(facts)
        return replace(
            baseline,
            planner_version="test-fallback",
            diagnostics=(
                *baseline.diagnostics,
                PlanDiagnostic(
                    code="SP005",
                    severity="warning",
                    message="Test fallback.",
                ),
            ),
            blocking_diagnostic_codes=("TEST001",),
        )


class _RecordingDeterministicPlanner:
    def __init__(self) -> None:
        self.received_facts: list[object] = []

    def create_plan(self, facts):  # type: ignore[no-untyped-def]
        self.received_facts.append(facts)
        return plan_tasks(facts)


def test_run_planning_benchmark_compares_sorted_planners_over_shared_facts() -> None:
    case = load_planning_corpus(CORPUS)[-1]
    deterministic = _RecordingDeterministicPlanner()
    fallback = _FallbackPlanner()
    ticks = iter((10.0, 10.5, 20.0, 22.0))

    report = run_planning_benchmark(
        (case,),
        {"static": deterministic, "fallback": fallback},
        project_root=ROOT,
        clock=lambda: next(ticks),
    )

    assert report.schema_version == PLANNING_BENCHMARK_SCHEMA_VERSION
    assert report.case_ids == ("simple-training",)
    assert report.corpus_cases[0].notebook_path == case.notebook_path
    assert report.corpus_cases[0].source_sha256 == case.source_sha256
    assert tuple(result.planner_name for result in report.planners) == ("fallback", "static")
    fallback_result, static_result = report.planners
    assert fallback_result.case_count == 1
    assert fallback_result.exact_match_count == 0
    assert fallback_result.exact_match_rate == 0.0
    assert fallback_result.valid_plan_count == 0
    assert fallback_result.valid_plan_rate == 0.0
    assert fallback_result.fallback_count == 1
    assert fallback_result.fallback_rate == 1.0
    assert fallback_result.total_duration_seconds == 0.5
    assert fallback_result.mean_duration_seconds == 0.5
    assert fallback_result.cases[0].plan_valid is False
    assert fallback_result.cases[0].used_fallback is True
    assert static_result.exact_match_count == 1
    assert static_result.exact_match_rate == 1.0
    assert static_result.valid_plan_count == 1
    assert static_result.valid_plan_rate == 1.0
    assert static_result.fallback_count == 0
    assert static_result.fallback_rate == 0.0
    assert static_result.total_duration_seconds == 2.0
    assert static_result.mean_duration_seconds == 2.0
    assert fallback.received_facts[0] is deterministic.received_facts[0]


def test_run_planning_benchmark_requires_cases_and_planners() -> None:
    with pytest.raises(ValueError, match="at least one case"):
        run_planning_benchmark((), {"static": DeterministicSemanticPlanner()})

    case = load_planning_corpus(CORPUS)[0]
    with pytest.raises(ValueError, match="at least one planner"):
        run_planning_benchmark((case,), {}, project_root=ROOT)


def test_run_planning_benchmark_rejects_empty_planner_name() -> None:
    case = load_planning_corpus(CORPUS)[0]

    with pytest.raises(ValueError, match="planner name must not be empty"):
        run_planning_benchmark(
            (case,),
            {"": DeterministicSemanticPlanner()},
            project_root=ROOT,
        )


@pytest.mark.parametrize("ticks", [(2.0, 1.0), (0.0, nan)])
def test_run_planning_benchmark_rejects_invalid_clock(ticks: tuple[float, float]) -> None:
    case = load_planning_corpus(CORPUS)[0]
    values = iter(ticks)

    with pytest.raises(ValueError, match="non-negative finite duration"):
        run_planning_benchmark(
            (case,),
            {"static": DeterministicSemanticPlanner()},
            project_root=ROOT,
            clock=lambda: next(values),
        )


def test_planning_benchmark_contracts_reject_inconsistent_reports() -> None:
    case = load_planning_corpus(CORPUS)[0]
    report = run_planning_benchmark(
        (case,),
        {"static": DeterministicSemanticPlanner()},
        project_root=ROOT,
        clock=iter((0.0, 1.0)).__next__,
    )
    planner = report.planners[0]

    with pytest.raises(ValueError, match="planner name must not be empty"):
        replace(planner, planner_name="")
    with pytest.raises(ValueError, match="at least one case"):
        replace(planner, cases=())
    with pytest.raises(ValueError, match="unsupported planning benchmark schema"):
        replace(report, schema_version="2.0")
    with pytest.raises(ValueError, match="at least one corpus case"):
        replace(report, corpus_cases=())
    with pytest.raises(ValueError, match="benchmark case IDs must be unique"):
        replace(report, corpus_cases=(report.corpus_cases[0], report.corpus_cases[0]))
    with pytest.raises(ValueError, match="at least one planner"):
        replace(report, planners=())
    with pytest.raises(ValueError, match="benchmark planner names must be unique"):
        replace(report, planners=(planner, planner))
    with pytest.raises(ValueError, match="same ordered case IDs"):
        PlanningBenchmarkReport(
            schema_version=PLANNING_BENCHMARK_SCHEMA_VERSION,
            corpus_cases=(
                PlanningBenchmarkCorpusCase(
                    case_id="different-case",
                    notebook_path=case.notebook_path,
                    source_sha256=case.source_sha256,
                ),
            ),
            planners=(PlannerBenchmark(planner_name="static", cases=planner.cases),),
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"case_id": ""}, "benchmark case ID must not be empty"),
        ({"notebook_path": ""}, "benchmark notebook path must not be empty"),
        ({"source_sha256": "invalid"}, "64-character hexadecimal digest"),
    ],
)
def test_benchmark_corpus_case_requires_source_identity(
    changes: dict[str, str], message: str
) -> None:
    values = {
        "case_id": "case-1",
        "notebook_path": "notebooks/example.ipynb",
        "source_sha256": "a" * 64,
        **changes,
    }

    with pytest.raises(ValueError, match=message):
        PlanningBenchmarkCorpusCase(
            case_id=values["case_id"],
            notebook_path=values["notebook_path"],
            source_sha256=values["source_sha256"],
        )
