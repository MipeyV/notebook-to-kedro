"""Offline regression checks for code benchmarks and honest metric denominators."""

from __future__ import annotations

import json
from dataclasses import replace
from math import inf, nan
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from notebook_to_kedro import plan_notebook_path
from notebook_to_kedro.evaluation import (
    NODE_CODE_BENCHMARK_SCHEMA_VERSION,
    load_planning_corpus,
    node_code_benchmark_to_dict,
    node_code_benchmark_to_json,
    run_node_code_benchmark,
)
from notebook_to_kedro.exceptions import NodeCodeProviderError
from notebook_to_kedro.generation.code import NodeCodeRequest, NodeCodeResponse
from notebook_to_kedro.generation.kedro import render_node_function

if TYPE_CHECKING:
    from collections.abc import Callable

    from notebook_to_kedro.evaluation import PlanningCase

ROOT = Path(__file__).parents[3]
CORPUS = ROOT / "tests/fixtures/evaluation/planning/v1"


class _ReferenceProvider:
    provider_name = "fake-reference"
    model_name = "v1"

    def __init__(
        self,
        cases: tuple[PlanningCase, ...],
        mutate: Callable[[NodeCodeRequest, NodeCodeResponse], str] | None = None,
    ) -> None:
        self.requests: list[NodeCodeRequest] = []
        self.mutate = mutate
        self.functions = {
            f"{case.case_id}:{task.id}": render_node_function(task)
            for case in cases
            for task in plan_notebook_path(
                ROOT / case.notebook_path, project_root=ROOT
            ).task_candidates
        }

    def complete(self, request: NodeCodeRequest) -> str:
        self.requests.append(request)
        response = NodeCodeResponse(
            schema_version=request.schema_version,
            request_id=request.request_id,
            task_id=request.task_id,
            function_code=self.functions[request.request_id],
            imports=request.allowed_imports,
        )
        if self.mutate is not None:
            return self.mutate(request, response)
        return response.to_json()


@pytest.fixture
def cases() -> tuple[PlanningCase, ...]:
    return load_planning_corpus(CORPUS)


def test_benchmark_checks_all_v1_nodes_and_serializes_provenance(
    cases: tuple[PlanningCase, ...],
) -> None:
    provider = _ReferenceProvider(cases)
    ticks = iter(float(tick) / 2 for tick in range(52))
    report = run_node_code_benchmark(
        cases, provider, project_root=ROOT, prompt_version="test-v1", clock=lambda: next(ticks)
    )

    assert report.schema_version == NODE_CODE_BENCHMARK_SCHEMA_VERSION
    assert (report.provider_name, report.model_name, report.prompt_version) == (
        "fake-reference",
        "v1",
        "test-v1",
    )
    assert len(report.tasks) == len(provider.requests) == 26
    assert all(task.duration_seconds == 0.5 for task in report.tasks)
    assert all(task.status == "accepted" and task.reference_ast_match for task in report.tasks)
    assert all(task.missing_parameter_reads == () for task in report.tasks)
    assert tuple(task.request for task in report.tasks) == tuple(provider.requests)
    assert report.tasks[0].notebook_path == cases[0].notebook_path
    assert report.tasks[0].source_sha256 == cases[0].source_sha256
    assert all(
        task.raw_response and task.response and task.reference_function for task in report.tasks
    )
    payload = json.loads(node_code_benchmark_to_json(report))
    assert payload["behavioral_equivalence"] == "not_evaluated"
    assert payload["reference"] == "deterministic-v1-function-ast"
    assert payload["tasks"][0]["request"]["source_cell_ids"]
    summary = payload["summary"]
    assert (
        summary["task_count"]
        == summary["accepted_count"]
        == summary["reference_ast_match_count"]
        == 26
    )
    assert summary["accepted_rate"] == summary["reference_ast_match_rate"] == 1.0
    assert summary["accepted_parameter_task_count"] > 0
    assert summary["tasks_missing_parameter_reads"] == 0
    assert summary["total_duration_seconds"] == 13.0
    assert summary["mean_duration_seconds"] == 0.5
    assert node_code_benchmark_to_json(report) == node_code_benchmark_to_json(report)
    assert json.loads(node_code_benchmark_to_json(report, indent=None)) == payload


def test_expected_failures_are_recorded_without_retry_or_dropping_tasks(
    cases: tuple[PlanningCase, ...],
) -> None:
    case = cases[-1]
    count = 0

    def mutate(_request: NodeCodeRequest, response: NodeCodeResponse) -> str:
        nonlocal count
        count += 1
        if count == 1:
            raise NodeCodeProviderError("ollama_timeout", "test timeout")
        if count == 2:
            return "not-json"
        if count == 3:
            return replace(response, request_id="wrong-id").to_json()
        return response.to_json()

    provider = _ReferenceProvider((case,), mutate)
    report = run_node_code_benchmark((case,), provider, project_root=ROOT)

    assert len(report.tasks) == len(provider.requests) == len(case.tasks)
    assert tuple(task.status for task in report.tasks[:3]) == (
        "provider_error",
        "invalid_response",
        "invalid_code",
    )
    assert report.tasks[0].diagnostic_code == "ollama_timeout"
    assert report.tasks[0].diagnostic_message == "test timeout"
    assert report.tasks[0].raw_response is None
    assert report.tasks[1].raw_response == "not-json"
    assert report.tasks[1].response is None
    assert report.tasks[2].response is not None
    assert all(task.reference_ast_match is None for task in report.tasks[:3])
    assert all(task.missing_parameter_reads is None for task in report.tasks[:3])
    summary = node_code_benchmark_to_dict(report)["summary"]
    assert isinstance(summary, dict)
    assert (
        summary["provider_error_count"]
        == summary["invalid_response_count"]
        == summary["invalid_code_count"]
        == 1
    )
    assert summary["accepted_count"] == len(case.tasks) - 3
    assert summary["reference_ast_match_rate"] == (len(case.tasks) - 3) / len(case.tasks)


def test_accepted_code_can_diverge_and_ignore_parameters(cases: tuple[PlanningCase, ...]) -> None:
    case = cases[-1]

    def mutate(request: NodeCodeRequest, response: NodeCodeResponse) -> str:
        if request.node_name == "split_data":
            code = response.function_code.replace("test_size=split_data_test_size", "test_size=0.2")
            assert code != response.function_code
            return replace(response, function_code=code).to_json()
        return response.to_json()

    report = run_node_code_benchmark(
        (case,), _ReferenceProvider((case,), mutate), project_root=ROOT
    )
    task = next(task for task in report.tasks if task.request.node_name == "split_data")

    assert task.status == "accepted"
    assert task.reference_ast_match is False
    assert task.missing_parameter_reads == ("split_data_test_size",)
    summary = node_code_benchmark_to_dict(report)["summary"]
    assert isinstance(summary, dict)
    assert summary["accepted_rate"] == 1.0
    assert summary["reference_ast_match_count"] == len(case.tasks) - 1
    assert summary["tasks_missing_parameter_reads"] == 1


def test_ast_comparison_ignores_formatting_and_comments(cases: tuple[PlanningCase, ...]) -> None:
    case = cases[-1]

    def mutate(_request: NodeCodeRequest, response: NodeCodeResponse) -> str:
        return replace(
            response, function_code="# added comment\n" + response.function_code
        ).to_json()

    report = run_node_code_benchmark(
        (case,), _ReferenceProvider((case,), mutate), project_root=ROOT
    )

    assert all(task.reference_ast_match is True for task in report.tasks)


def test_dropped_assertion_is_not_counted_as_a_reference_match(
    cases: tuple[PlanningCase, ...],
) -> None:
    case = cases[-1]

    def mutate(request: NodeCodeRequest, response: NodeCodeResponse) -> str:
        if request.node_name == "evaluate_model":
            code = response.function_code.replace("    assert accuracy >= 0.90\n", "")
            assert code != response.function_code
            return replace(response, function_code=code).to_json()
        return response.to_json()

    report = run_node_code_benchmark(
        (case,), _ReferenceProvider((case,), mutate), project_root=ROOT
    )
    task = next(task for task in report.tasks if task.request.node_name == "evaluate_model")

    assert task.status == "accepted"
    assert task.reference_ast_match is False
    assert task.missing_parameter_reads == ()


def test_benchmark_does_not_execute_valid_proposals(
    cases: tuple[PlanningCase, ...], tmp_path: Path
) -> None:
    case = cases[-1]
    marker = tmp_path / "never-created"

    def mutate(_request: NodeCodeRequest, response: NodeCodeResponse) -> str:
        return replace(
            response,
            function_code=response.function_code.replace(
                "    return ", f"    open({str(marker)!r}, 'w').close()\n    return "
            ),
        ).to_json()

    report = run_node_code_benchmark(
        (case,), _ReferenceProvider((case,), mutate), project_root=ROOT
    )

    assert all(task.status == "accepted" and not task.reference_ast_match for task in report.tasks)
    assert not marker.exists()


def test_benchmark_rejects_empty_or_duplicate_cases(cases: tuple[PlanningCase, ...]) -> None:
    provider = _ReferenceProvider(cases)
    with pytest.raises(ValueError, match="at least one case"):
        run_node_code_benchmark((), provider)
    with pytest.raises(ValueError, match="IDs must be unique"):
        run_node_code_benchmark((cases[0], cases[0]), provider)
    assert not provider.requests


@pytest.mark.parametrize("change", ["hash", "source", "interface"])
def test_all_cases_are_preflighted_before_any_provider_call(
    cases: tuple[PlanningCase, ...], change: str
) -> None:
    bad_case = cases[-1]
    if change == "hash":
        bad_case = replace(bad_case, source_sha256="0" * 64)
    else:
        first = bad_case.tasks[0]
        first = (
            replace(first, raw_source="x = 1")
            if change == "source"
            else replace(first, expected_inputs=("invented",))
        )
        bad_case = replace(bad_case, tasks=(first, *bad_case.tasks[1:]))
    provider = _ReferenceProvider(cases)

    with pytest.raises(ValueError, match="does not match the reviewed V1 plan and source"):
        run_node_code_benchmark((*cases[:-1], bad_case), provider, project_root=ROOT)

    assert not provider.requests


@pytest.mark.parametrize("ticks", [(1.0, 0.0), (0.0, nan), (0.0, inf)])
def test_invalid_clock_is_rejected(
    cases: tuple[PlanningCase, ...], ticks: tuple[float, float]
) -> None:
    values = iter(ticks)
    with pytest.raises(ValueError, match="non-negative finite duration"):
        run_node_code_benchmark(
            (cases[-1],), _ReferenceProvider(cases), project_root=ROOT, clock=lambda: next(values)
        )


def test_unexpected_provider_bugs_propagate(cases: tuple[PlanningCase, ...]) -> None:
    def mutate(_request: NodeCodeRequest, _response: NodeCodeResponse) -> str:
        raise RuntimeError("implementation bug")

    with pytest.raises(RuntimeError, match="implementation bug"):
        run_node_code_benchmark(cases, _ReferenceProvider(cases, mutate), project_root=ROOT)


def test_empty_report_summary_is_defined(cases: tuple[PlanningCase, ...]) -> None:
    report = run_node_code_benchmark((cases[-1],), _ReferenceProvider(cases), project_root=ROOT)
    summary = node_code_benchmark_to_dict(replace(report, tasks=()))["summary"]

    assert isinstance(summary, dict)
    assert summary["accepted_rate"] == summary["reference_ast_match_rate"] == 0.0
    assert summary["mean_duration_seconds"] == 0.0
