"""Non-executing code-provider benchmarks against the deterministic V1 reference."""

from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass, replace
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Literal

from notebook_to_kedro.api import analyze_notebook_path
from notebook_to_kedro.evaluation.planning import evaluate_planning_case
from notebook_to_kedro.exceptions import NodeCodeProviderError
from notebook_to_kedro.generation.code import (
    NodeCodeRequest,
    NodeCodeResponse,
    build_node_code_request,
    validate_node_code,
)
from notebook_to_kedro.generation.kedro import render_node_function
from notebook_to_kedro.semantic import plan_tasks, validate_conversion_plan

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from notebook_to_kedro.evaluation.models import PlanningCase
    from notebook_to_kedro.generation.code import NodeCodeProvider

NODE_CODE_BENCHMARK_SCHEMA_VERSION = "1.0"
NodeCodeStatus = Literal["accepted", "provider_error", "invalid_response", "invalid_code"]


@dataclass(frozen=True, slots=True)
class NodeCodeBenchmarkTask:
    """Evidence and static outcome for one request; no behavioral accuracy claim."""

    case_id: str
    notebook_path: str
    source_sha256: str
    request: NodeCodeRequest
    reference_function: str
    duration_seconds: float = 0.0
    status: NodeCodeStatus = "accepted"
    raw_response: str | None = None
    response: NodeCodeResponse | None = None
    diagnostic_code: str | None = None
    diagnostic_message: str | None = None
    reference_ast_match: bool | None = None
    missing_parameter_reads: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class NodeCodeBenchmarkReport:
    """Versioned provider provenance and ordered task outcomes."""

    schema_version: str
    provider_name: str
    model_name: str
    prompt_version: str | None
    tasks: tuple[NodeCodeBenchmarkTask, ...]


def run_node_code_benchmark(
    cases: Sequence[PlanningCase],
    provider: NodeCodeProvider,
    *,
    project_root: str | Path = ".",
    prompt_version: str | None = None,
    clock: Callable[[], float] = perf_counter,
) -> NodeCodeBenchmarkReport:
    """Check every case before model I/O, then request each node once in corpus order."""
    if not cases:
        raise ValueError("node code benchmark requires at least one case")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("node code benchmark case IDs must be unique")
    provider_name, model_name = provider.provider_name, provider.model_name
    root = Path(project_root).resolve()
    prepared = tuple(task for case in cases for task in _prepare_case(case, root))
    results = tuple(_run_task(task, provider, clock) for task in prepared)
    return NodeCodeBenchmarkReport(
        schema_version=NODE_CODE_BENCHMARK_SCHEMA_VERSION,
        provider_name=provider_name,
        model_name=model_name,
        prompt_version=prompt_version,
        tasks=results,
    )


def _prepare_case(case: PlanningCase, root: Path) -> tuple[NodeCodeBenchmarkTask, ...]:
    facts = analyze_notebook_path(root / case.notebook_path, project_root=root)
    plan = plan_tasks(facts)
    validate_conversion_plan(plan)
    if not evaluate_planning_case(case, facts, plan).exact_match:
        raise ValueError(f"case does not match the reviewed V1 plan and source: {case.case_id}")
    prepared = []
    for task in plan.task_candidates:
        request = build_node_code_request(plan, task.id, request_id=f"{case.case_id}:{task.id}")
        reference = render_node_function(task)
        validate_node_code(
            request,
            NodeCodeResponse(
                schema_version=request.schema_version,
                request_id=request.request_id,
                task_id=request.task_id,
                function_code=reference,
                imports=plan.imports,
            ),
        )
        prepared.append(
            NodeCodeBenchmarkTask(
                case_id=case.case_id,
                notebook_path=case.notebook_path,
                source_sha256=case.source_sha256,
                request=request,
                reference_function=reference,
            )
        )
    return tuple(prepared)


def _run_task(
    task: NodeCodeBenchmarkTask, provider: NodeCodeProvider, clock: Callable[[], float]
) -> NodeCodeBenchmarkTask:
    started_at = clock()
    result = _propose(task, provider)
    duration = clock() - started_at
    if not isfinite(duration) or duration < 0:
        raise ValueError("benchmark clock must produce a non-negative finite duration")
    return replace(result, duration_seconds=duration)


def _propose(task: NodeCodeBenchmarkTask, provider: NodeCodeProvider) -> NodeCodeBenchmarkTask:
    try:
        raw = provider.complete(task.request)
    except NodeCodeProviderError as error:
        return replace(
            task,
            status="provider_error",
            diagnostic_code=error.code,
            diagnostic_message=error.message,
        )
    task = replace(task, raw_response=raw)
    try:
        response = NodeCodeResponse.from_json(raw)
    except ValueError as error:
        return replace(
            task,
            status="invalid_response",
            diagnostic_code="invalid_response",
            diagnostic_message=str(error),
        )
    task = replace(task, response=response)
    try:
        validate_node_code(task.request, response)
    except ValueError as error:
        return replace(
            task,
            status="invalid_code",
            diagnostic_code="invalid_code",
            diagnostic_message=str(error),
        )
    tree = ast.parse(response.function_code)
    reads = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    return replace(
        task,
        reference_ast_match=ast.dump(tree) == ast.dump(ast.parse(task.reference_function)),
        missing_parameter_reads=tuple(
            name for name in task.request.parameter_arguments if name not in reads
        ),
    )


def node_code_benchmark_to_dict(report: NodeCodeBenchmarkReport) -> dict[str, object]:
    """Serialize outcomes with explicit denominators and no equivalence score."""
    total = len(report.tasks)
    accepted = sum(task.status == "accepted" for task in report.tasks)
    exact = sum(task.reference_ast_match is True for task in report.tasks)
    parameter_tasks = tuple(
        task
        for task in report.tasks
        if task.status == "accepted" and task.request.parameter_arguments
    )
    duration = sum(task.duration_seconds for task in report.tasks)
    return {
        **asdict(report),
        "reference": "deterministic-v1-function-ast",
        "behavioral_equivalence": "not_evaluated",
        "summary": {
            "task_count": total,
            "accepted_count": accepted,
            "accepted_rate": accepted / total if total else 0.0,
            "reference_ast_match_count": exact,
            "reference_ast_match_rate": exact / total if total else 0.0,
            "provider_error_count": sum(t.status == "provider_error" for t in report.tasks),
            "invalid_response_count": sum(t.status == "invalid_response" for t in report.tasks),
            "invalid_code_count": sum(t.status == "invalid_code" for t in report.tasks),
            "accepted_parameter_task_count": len(parameter_tasks),
            "tasks_missing_parameter_reads": sum(
                bool(t.missing_parameter_reads) for t in parameter_tasks
            ),
            "total_duration_seconds": duration,
            "mean_duration_seconds": duration / total if total else 0.0,
        },
    }


def node_code_benchmark_to_json(report: NodeCodeBenchmarkReport, *, indent: int | None = 2) -> str:
    """Encode a stable JSON report, including source and proposals, without writing files."""
    return (
        json.dumps(
            node_code_benchmark_to_dict(report),
            indent=indent,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )
