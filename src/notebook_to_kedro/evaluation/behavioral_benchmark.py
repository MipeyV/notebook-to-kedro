"""Provider benchmark with static validation and behavioral proposal evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Literal, TypeAlias

from notebook_to_kedro.evaluation.behavioral import validate_behavioral_corpus
from notebook_to_kedro.evaluation.behavioral_proposal import (
    BehavioralProposalEvaluation,
    behavioral_proposal_evaluation_to_dict,
    evaluate_behavioral_proposal,
)
from notebook_to_kedro.evaluation.node_code_corpus import verify_node_code_case_source
from notebook_to_kedro.exceptions import NodeCodeProviderError
from notebook_to_kedro.generation.code import (
    NODE_CODE_VALIDATOR_VERSION,
    NodeCodeRequest,
    NodeCodeResponse,
    validate_node_code,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from notebook_to_kedro.evaluation.behavioral import BehavioralCase
    from notebook_to_kedro.evaluation.behavioral_execution import BehavioralExecutionConfig
    from notebook_to_kedro.evaluation.node_code_corpus import NodeCodeCase
    from notebook_to_kedro.generation.code import NodeCodeProvider

BEHAVIORAL_CODE_BENCHMARK_SCHEMA_VERSION = "1.0"
BEHAVIORAL_PROPOSAL_EXECUTION_POLICY = "validated-local-subprocess-v1"
BehavioralCodeProposalStatus: TypeAlias = Literal[
    "accepted", "provider_error", "invalid_response", "invalid_code"
]


@dataclass(frozen=True, slots=True)
class BehavioralCodeBenchmarkProposal:
    """Provider and behavioral outcomes for one independent node-code case."""

    node_code_case_id: str
    notebook_path: str
    source_sha256: str
    request: NodeCodeRequest
    proposal_duration_seconds: float = 0.0
    status: BehavioralCodeProposalStatus = "accepted"
    raw_response: str | None = None
    response: NodeCodeResponse | None = None
    diagnostic_code: str | None = None
    diagnostic_message: str | None = None
    evaluations: tuple[BehavioralProposalEvaluation, ...] = ()


@dataclass(frozen=True, slots=True)
class BehavioralCodeBenchmarkReport:
    """Versioned provider provenance and behavioral outcomes for one corpus run."""

    schema_version: str
    provider_name: str
    model_name: str
    prompt_version: str | None
    validator_version: str
    execution_policy: str
    scenario_count: int
    proposals: tuple[BehavioralCodeBenchmarkProposal, ...]


def run_behavioral_code_benchmark(  # noqa: PLR0913
    behavioral_cases: Sequence[BehavioralCase],
    node_code_cases: Sequence[NodeCodeCase],
    provider: NodeCodeProvider,
    *,
    allow_untrusted_code_execution: bool = False,
    project_root: str | Path = ".",
    prompt_version: str | None = None,
    execution_config: BehavioralExecutionConfig | None = None,
    clock: Callable[[], float] = perf_counter,
) -> BehavioralCodeBenchmarkReport:
    """Request each node once, then execute accepted proposals over linked scenarios."""
    if allow_untrusted_code_execution is not True:
        raise ValueError(
            "behavioral benchmark requires allow_untrusted_code_execution=True because "
            "process isolation is not an OS sandbox"
        )
    behaviors = tuple(behavioral_cases)
    nodes = tuple(node_code_cases)
    _preflight(behaviors, nodes, Path(project_root).resolve())
    provider_name, model_name = provider.provider_name, provider.model_name
    proposals = tuple(
        _run_proposal(
            node,
            tuple(case for case in behaviors if case.node_code_case_id == node.case_id),
            provider,
            execution_config,
            clock,
        )
        for node in nodes
    )
    return BehavioralCodeBenchmarkReport(
        schema_version=BEHAVIORAL_CODE_BENCHMARK_SCHEMA_VERSION,
        provider_name=provider_name,
        model_name=model_name,
        prompt_version=prompt_version,
        validator_version=NODE_CODE_VALIDATOR_VERSION,
        execution_policy=BEHAVIORAL_PROPOSAL_EXECUTION_POLICY,
        scenario_count=len(behaviors),
        proposals=proposals,
    )


def behavioral_code_benchmark_to_dict(
    report: BehavioralCodeBenchmarkReport,
) -> dict[str, object]:
    """Serialize benchmark evidence with explicit static and behavioral denominators."""
    evaluations = tuple(
        evaluation for proposal in report.proposals for evaluation in proposal.evaluations
    )
    proposal_count = len(report.proposals)
    accepted_count = sum(proposal.status == "accepted" for proposal in report.proposals)
    evaluated_count = len(evaluations)
    matched_count = sum(evaluation.comparison.status == "matched" for evaluation in evaluations)
    mismatch_count = sum(evaluation.comparison.status == "mismatch" for evaluation in evaluations)
    execution_error_count = sum(
        evaluation.comparison.status == "execution_error" for evaluation in evaluations
    )
    provider_duration = sum(proposal.proposal_duration_seconds for proposal in report.proposals)
    execution_duration = sum(evaluation.execution.duration_seconds for evaluation in evaluations)
    return {
        "schema_version": report.schema_version,
        "provider_name": report.provider_name,
        "model_name": report.model_name,
        "prompt_version": report.prompt_version,
        "validator_version": report.validator_version,
        "execution_policy": report.execution_policy,
        "scenario_count": report.scenario_count,
        "proposals": [_proposal_to_dict(proposal) for proposal in report.proposals],
        "summary": {
            "proposal_count": proposal_count,
            "accepted_count": accepted_count,
            "accepted_rate": accepted_count / proposal_count if proposal_count else 0.0,
            "provider_error_count": sum(
                proposal.status == "provider_error" for proposal in report.proposals
            ),
            "invalid_response_count": sum(
                proposal.status == "invalid_response" for proposal in report.proposals
            ),
            "invalid_code_count": sum(
                proposal.status == "invalid_code" for proposal in report.proposals
            ),
            "scenario_count": report.scenario_count,
            "evaluated_scenario_count": evaluated_count,
            "not_evaluated_scenario_count": report.scenario_count - evaluated_count,
            "matched_scenario_count": matched_count,
            "mismatch_scenario_count": mismatch_count,
            "execution_error_scenario_count": execution_error_count,
            "evaluated_match_rate": matched_count / evaluated_count if evaluated_count else 0.0,
            "end_to_end_match_rate": (
                matched_count / report.scenario_count if report.scenario_count else 0.0
            ),
            "provider_duration_seconds": provider_duration,
            "mean_provider_duration_seconds": (
                provider_duration / proposal_count if proposal_count else 0.0
            ),
            "execution_duration_seconds": execution_duration,
        },
    }


def behavioral_code_benchmark_to_json(
    report: BehavioralCodeBenchmarkReport, *, indent: int | None = 2
) -> str:
    """Encode a deterministic benchmark report without writing it to disk."""
    return (
        json.dumps(
            behavioral_code_benchmark_to_dict(report),
            indent=indent,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )


def _preflight(
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
    root: Path,
) -> None:
    validate_behavioral_corpus(behaviors, nodes)
    linked_node_ids = {case.node_code_case_id for case in behaviors}
    node_ids = {case.case_id for case in nodes}
    if linked_node_ids != node_ids:
        raise ValueError("behavioral benchmark requires scenarios for every node code case")
    for node in nodes:
        verify_node_code_case_source(node, project_root=root)
        validate_node_code(node.request, node.reference_response)


def _run_proposal(
    node: NodeCodeCase,
    behaviors: tuple[BehavioralCase, ...],
    provider: NodeCodeProvider,
    execution_config: BehavioralExecutionConfig | None,
    clock: Callable[[], float],
) -> BehavioralCodeBenchmarkProposal:
    proposal = BehavioralCodeBenchmarkProposal(
        node_code_case_id=node.case_id,
        notebook_path=node.notebook_path,
        source_sha256=node.source_sha256,
        request=node.request,
    )
    started_at = clock()
    proposal = _request_proposal(proposal, provider)
    duration = clock() - started_at
    if not isfinite(duration) or duration < 0:
        raise ValueError("benchmark clock must produce a non-negative finite duration")
    proposal = replace(proposal, proposal_duration_seconds=duration)
    return _evaluate_proposal(proposal, node, behaviors, execution_config)


def _evaluate_proposal(
    proposal: BehavioralCodeBenchmarkProposal,
    node: NodeCodeCase,
    behaviors: tuple[BehavioralCase, ...],
    execution_config: BehavioralExecutionConfig | None,
) -> BehavioralCodeBenchmarkProposal:
    if proposal.status != "accepted":
        return proposal
    response = proposal.response
    if response is None:
        raise ValueError("accepted proposal must contain a parsed response")
    return replace(
        proposal,
        evaluations=tuple(
            evaluate_behavioral_proposal(
                case,
                node,
                response,
                allow_untrusted_code_execution=True,
                config=execution_config,
            )
            for case in behaviors
        ),
    )


def _request_proposal(
    proposal: BehavioralCodeBenchmarkProposal, provider: NodeCodeProvider
) -> BehavioralCodeBenchmarkProposal:
    try:
        raw = provider.complete(proposal.request)
    except NodeCodeProviderError as error:
        return replace(
            proposal,
            status="provider_error",
            diagnostic_code=error.code,
            diagnostic_message=error.message,
        )
    proposal = replace(proposal, raw_response=raw)
    try:
        response = NodeCodeResponse.from_json(raw)
    except ValueError as error:
        return replace(
            proposal,
            status="invalid_response",
            diagnostic_code="invalid_response",
            diagnostic_message=str(error),
        )
    proposal = replace(proposal, response=response)
    try:
        validate_node_code(proposal.request, response)
    except ValueError as error:
        return replace(
            proposal,
            status="invalid_code",
            diagnostic_code="invalid_code",
            diagnostic_message=str(error),
        )
    return proposal


def _proposal_to_dict(proposal: BehavioralCodeBenchmarkProposal) -> dict[str, object]:
    return {
        "node_code_case_id": proposal.node_code_case_id,
        "notebook_path": proposal.notebook_path,
        "source_sha256": proposal.source_sha256,
        "request": json.loads(proposal.request.to_json(indent=None)),
        "proposal_duration_seconds": proposal.proposal_duration_seconds,
        "status": proposal.status,
        "raw_response": proposal.raw_response,
        "response": (
            None
            if proposal.response is None
            else json.loads(proposal.response.to_json(indent=None))
        ),
        "diagnostic_code": proposal.diagnostic_code,
        "diagnostic_message": proposal.diagnostic_message,
        "evaluations": [
            behavioral_proposal_evaluation_to_dict(evaluation)
            for evaluation in proposal.evaluations
        ],
    }
