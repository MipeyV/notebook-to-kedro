"""Body-only benchmarks with strict assembly and the existing behavioral metrics."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from notebook_to_kedro.evaluation.behavioral import behavioral_case_to_dict
from notebook_to_kedro.evaluation.behavioral_artifacts import _json_sha256
from notebook_to_kedro.evaluation.behavioral_benchmark import (
    BEHAVIORAL_CODE_BENCHMARK_SCHEMA_VERSION,
    BEHAVIORAL_PROPOSAL_EXECUTION_POLICY,
    BehavioralCodeBenchmarkProposal,
    BehavioralCodeBenchmarkReport,
    _evaluate_proposal,
    _preflight,
)
from notebook_to_kedro.evaluation.node_code_corpus import node_code_case_to_dict
from notebook_to_kedro.exceptions import NodeCodeProviderError
from notebook_to_kedro.generation.code import (
    NODE_CODE_VALIDATOR_VERSION,
    NodeBodyResponse,
    assemble_node_body,
    build_parameter_evidence,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from notebook_to_kedro.evaluation.behavioral import BehavioralCase
    from notebook_to_kedro.evaluation.behavioral_execution import BehavioralExecutionConfig
    from notebook_to_kedro.evaluation.node_code_corpus import NodeCodeCase
    from notebook_to_kedro.generation.code import NodeBodyProvider


@dataclass(frozen=True, slots=True)
class NodeBodyBenchmarkReport:
    """Behavioral outcomes plus ordered parsed bodies and an exact corpus identity."""

    benchmark: BehavioralCodeBenchmarkReport
    body_responses: tuple[NodeBodyResponse | None, ...]
    corpus_sha256: str


def _corpus_sha256(behaviors: Sequence[BehavioralCase], nodes: Sequence[NodeCodeCase]) -> str:
    return _json_sha256(
        {
            "behaviors": [
                behavioral_case_to_dict(case) for case in sorted(behaviors, key=lambda c: c.case_id)
            ],
            "nodes": [
                node_code_case_to_dict(case) for case in sorted(nodes, key=lambda c: c.case_id)
            ],
        }
    )


def run_node_body_benchmark(  # noqa: PLR0913
    behavioral_cases: Sequence[BehavioralCase],
    node_code_cases: Sequence[NodeCodeCase],
    provider: NodeBodyProvider,
    *,
    allow_untrusted_code_execution: bool = False,
    project_root: str | Path = ".",
    execution_config: BehavioralExecutionConfig | None = None,
    clock: Callable[[], float] = perf_counter,
) -> NodeBodyBenchmarkReport:
    """Record every raw body and rejection, then execute only validated assemblies."""
    if allow_untrusted_code_execution is not True:
        raise ValueError(
            "body benchmark requires allow_untrusted_code_execution=True; "
            "subprocesses are not an OS sandbox"
        )
    behaviors, nodes = tuple(behavioral_cases), tuple(node_code_cases)
    _preflight(behaviors, nodes, Path(project_root).resolve())
    for node in nodes:
        build_parameter_evidence(node.request)
    provider_name, model_name, prompt_version = (
        provider.provider_name,
        provider.model_name,
        provider.prompt_version,
    )
    proposals = []
    bodies = []
    for node in nodes:
        proposal = BehavioralCodeBenchmarkProposal(
            node_code_case_id=node.case_id,
            notebook_path=node.notebook_path,
            source_sha256=node.source_sha256,
            request=node.request,
        )
        started_at = clock()
        proposal, body = _request_body(proposal, provider)
        duration = clock() - started_at
        if not isfinite(duration) or duration < 0:
            raise ValueError("benchmark clock must produce a non-negative finite duration")
        proposal = replace(proposal, proposal_duration_seconds=duration)
        proposals.append(
            _evaluate_proposal(
                proposal,
                node,
                tuple(case for case in behaviors if case.node_code_case_id == node.case_id),
                execution_config,
            )
        )
        bodies.append(body)
    benchmark = BehavioralCodeBenchmarkReport(
        schema_version=BEHAVIORAL_CODE_BENCHMARK_SCHEMA_VERSION,
        provider_name=provider_name,
        model_name=model_name,
        prompt_version=prompt_version,
        validator_version=NODE_CODE_VALIDATOR_VERSION,
        execution_policy=BEHAVIORAL_PROPOSAL_EXECUTION_POLICY,
        scenario_count=len(behaviors),
        proposals=tuple(proposals),
    )
    return NodeBodyBenchmarkReport(benchmark, tuple(bodies), _corpus_sha256(behaviors, nodes))


def _request_body(
    proposal: BehavioralCodeBenchmarkProposal, provider: NodeBodyProvider
) -> tuple[BehavioralCodeBenchmarkProposal, NodeBodyResponse | None]:
    try:
        raw = provider.complete(proposal.request)
    except NodeCodeProviderError as error:
        return replace(
            proposal,
            status="provider_error",
            diagnostic_code=error.code,
            diagnostic_message=error.message,
        ), None
    proposal = replace(proposal, raw_response=raw)
    try:
        body = NodeBodyResponse.from_json(raw)
    except ValueError as error:
        return replace(
            proposal,
            status="invalid_response",
            diagnostic_code="invalid_response",
            diagnostic_message=str(error),
        ), None
    try:
        response = assemble_node_body(proposal.request, body)
    except ValueError as error:
        return replace(
            proposal,
            status="invalid_code",
            diagnostic_code="invalid_code",
            diagnostic_message=str(error),
        ), body
    return replace(proposal, response=response), body
