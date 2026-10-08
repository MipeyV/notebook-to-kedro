"""Explicit full-code corpus snapshots for fresh runs, not historical migration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from notebook_to_kedro.evaluation.behavioral import (
    behavioral_case_from_dict,
    behavioral_case_to_dict,
    validate_behavioral_corpus,
)
from notebook_to_kedro.evaluation.behavioral_artifacts import (
    BehavioralBenchmarkArtifact,
    _exact_keys,
    _is_sha256,
    _json_sha256,
    _number,
    _object,
    _optional_string,
    _proposals_by_id,
    _string,
    _to_json,
    behavioral_benchmark_artifact_from_dict,
    behavioral_benchmark_artifact_to_dict,
    create_behavioral_benchmark_artifact,
    replay_behavioral_benchmark,
    write_json_exclusive,
)
from notebook_to_kedro.evaluation.behavioral_benchmark import (
    BehavioralCodeBenchmarkReport,
    run_behavioral_code_benchmark,
)
from notebook_to_kedro.evaluation.behavioral_comparison import (
    behavioral_case_comparison_to_dict,
    compare_behavioral_result,
)
from notebook_to_kedro.evaluation.behavioral_execution import _result_from_worker
from notebook_to_kedro.evaluation.behavioral_proposal import (
    BEHAVIORAL_PROPOSAL_EVALUATION_SCHEMA_VERSION,
    _response_sha256,
)
from notebook_to_kedro.evaluation.node_code_corpus import (
    node_code_case_from_dict,
    node_code_case_to_dict,
)
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError
from notebook_to_kedro.generation.code import (
    NODE_CODE_VALIDATOR_VERSION,
    NodeCodeRequest,
    NodeCodeResponse,
    validate_node_code,
)
from notebook_to_kedro.generation.code.serialization import _unique_object

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Literal

    from notebook_to_kedro.evaluation.behavioral import BehavioralCase
    from notebook_to_kedro.evaluation.behavioral_artifacts import (
        BehavioralBenchmarkConfiguration,
        BehavioralBenchmarkProvenance,
    )
    from notebook_to_kedro.evaluation.behavioral_execution import BehavioralExecutionConfig
    from notebook_to_kedro.evaluation.node_code_corpus import NodeCodeCase
    from notebook_to_kedro.generation.code import NodeCodeProvider

CORPUS_BOUND_CODE_ARTIFACT_SCHEMA_VERSION = "1.0"
_KEYS = frozenset({"schema_version", "artifact_kind", "corpus_sha256", "corpus", "benchmark"})
_PROPOSAL_KEYS = frozenset(
    {
        "node_code_case_id",
        "notebook_path",
        "source_sha256",
        "request",
        "proposal_duration_seconds",
        "status",
        "raw_response",
        "response",
        "diagnostic_code",
        "diagnostic_message",
        "evaluations",
    }
)
_EVALUATION_KEYS = frozenset(
    {
        "schema_version",
        "case_id",
        "node_code_case_id",
        "request_id",
        "task_id",
        "response_sha256",
        "execution",
        "comparison",
    }
)


@dataclass(frozen=True, slots=True)
class CorpusBoundCodeBenchmarkReport:
    """A snapshot captured before generation and its unchanged full-code report."""

    benchmark: BehavioralCodeBenchmarkReport
    corpus: dict[str, object]
    corpus_sha256: str


@dataclass(frozen=True, slots=True)
class CorpusBoundCodeBenchmarkArtifact:
    """Separate full-code envelope with explicit reviewed corpus evidence."""

    schema_version: str
    corpus_sha256: str
    corpus: dict[str, object]
    benchmark: BehavioralBenchmarkArtifact

    def __post_init__(self) -> None:
        if self.schema_version != CORPUS_BOUND_CODE_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("unsupported corpus-bound code artifact version")
        if not _is_sha256(self.corpus_sha256) or _json_sha256(self.corpus) != self.corpus_sha256:
            raise ValueError("corpus_sha256 must match the complete corpus snapshot")
        behaviors, nodes = _decode_corpus(self.corpus)
        validate_behavioral_corpus(behaviors, nodes)
        validate_recorded_corpus(self.benchmark, behaviors, nodes)
        if self.benchmark.report["validator_version"] != NODE_CODE_VALIDATOR_VERSION:
            raise ValueError("corpus-bound code requires the supported validator version")
        for proposal in _proposals_by_id(self.benchmark.report).values():
            _validate_code_record(proposal)


def _snapshot(
    behaviors: Sequence[BehavioralCase], nodes: Sequence[NodeCodeCase]
) -> dict[str, object]:
    return {
        "behaviors": [
            behavioral_case_to_dict(case) for case in sorted(behaviors, key=lambda c: c.case_id)
        ],
        "nodes": [node_code_case_to_dict(case) for case in sorted(nodes, key=lambda c: c.case_id)],
    }


def _decode_corpus(
    corpus: dict[str, object],
) -> tuple[tuple[BehavioralCase, ...], tuple[NodeCodeCase, ...]]:
    _exact_keys(corpus, frozenset({"behaviors", "nodes"}), "corpus snapshot")
    behaviors, nodes = corpus["behaviors"], corpus["nodes"]
    if not isinstance(behaviors, list) or not isinstance(nodes, list):
        raise ValueError("corpus snapshot must contain case arrays")
    return (
        tuple(behavioral_case_from_dict(case) for case in behaviors),
        tuple(node_code_case_from_dict(case) for case in nodes),
    )


def validate_recorded_corpus(
    artifact: BehavioralBenchmarkArtifact,
    behaviors: Sequence[BehavioralCase],
    nodes: Sequence[NodeCodeCase],
) -> None:
    """Check exact source and scenario bindings without execution or filesystem access."""
    if not behaviors or not nodes:
        raise ValueError("recorded corpus must contain nodes and scenarios")
    proposals = _proposals_by_id(artifact.report)
    if proposals.keys() != {node.case_id for node in nodes} or artifact.report[
        "scenario_count"
    ] != len(behaviors):
        raise ValueError("recorded benchmark must cover the exact corpus")
    for node in nodes:
        proposal = proposals[node.case_id]
        _exact_keys(proposal, _PROPOSAL_KEYS, "recorded proposal")
        duration = _number(proposal["proposal_duration_seconds"], "proposal_duration_seconds")
        if not isfinite(duration) or duration < 0:
            raise ValueError("proposal duration must be finite and nonnegative")
        _optional_string(proposal["diagnostic_code"], "diagnostic_code")
        _optional_string(proposal["diagnostic_message"], "diagnostic_message")
        if (
            proposal["request"] != json.loads(node.request.to_json())
            or proposal["source_sha256"] != node.source_sha256
            or proposal["notebook_path"] != node.notebook_path
        ):
            raise ValueError("recorded source identity must match the corpus")
        evaluations = proposal["evaluations"]
        if not isinstance(evaluations, list):
            raise ValueError("evaluations must be an array")
        expected = (
            {case.case_id for case in behaviors if case.node_code_case_id == node.case_id}
            if proposal["status"] == "accepted"
            else set()
        )
        actual = [
            _string(_object(row, "evaluation").get("case_id"), "case_id") for row in evaluations
        ]
        if set(actual) != expected or len(actual) != len(expected):
            raise ValueError("evaluations must cover exactly the accepted node's scenarios")
        by_id = {case.case_id: case for case in behaviors}
        for value in evaluations:
            row = _object(value, "evaluation")
            _exact_keys(row, _EVALUATION_KEYS, "recorded evaluation")
            response = NodeCodeResponse.from_json(
                _to_json(_object(proposal["response"], "response"))
            )
            if (
                row["schema_version"] != BEHAVIORAL_PROPOSAL_EVALUATION_SCHEMA_VERSION
                or row["node_code_case_id"] != node.case_id
                or row["request_id"] != node.request.request_id
                or row["task_id"] != node.request.task_id
                or row["response_sha256"] != _response_sha256(response)
            ):
                raise ValueError("recorded evaluation identity must match the proposed response")
            execution = dict(_object(row["execution"], "execution"))
            result = _result_from_worker(
                execution,
                duration=_number(execution.pop("duration_seconds", None), "duration_seconds"),
            )
            comparison = behavioral_case_comparison_to_dict(
                compare_behavioral_result(by_id[_string(row["case_id"], "case_id")], result)
            )
            if row["comparison"] != comparison:
                raise ValueError(
                    "recorded comparison must match execution evidence and corpus expectations"
                )


def _validate_code_record(proposal: dict[str, object]) -> None:
    raw, stored = proposal.get("raw_response"), proposal.get("response")
    if proposal["status"] == "provider_error":
        if raw is not None or stored is not None:
            raise ValueError("provider errors must not contain responses")
        return
    raw = _string(raw, "raw_response")
    try:
        parsed = NodeCodeResponse.from_json(raw)
    except ValueError:
        parsed = None
    expected = "invalid_response"
    if parsed is not None:
        request = NodeCodeRequest.from_json(_to_json(_object(proposal["request"], "request")))
        try:
            validate_node_code(request, parsed)
        except ValueError:
            expected = "invalid_code"
        else:
            expected = "accepted"
    response = None if parsed is None else json.loads(parsed.to_json())
    if proposal["status"] != expected or stored != response:
        raise ValueError("recorded status and response must match raw full-code validation")


def run_corpus_bound_code_benchmark(  # noqa: PLR0913
    behavioral_cases: Sequence[BehavioralCase],
    node_code_cases: Sequence[NodeCodeCase],
    provider: NodeCodeProvider,
    *,
    allow_untrusted_code_execution: bool = False,
    project_root: str | Path = ".",
    prompt_version: str | None = None,
    execution_config: BehavioralExecutionConfig | None = None,
    clock: Callable[[], float] = perf_counter,
) -> CorpusBoundCodeBenchmarkReport:
    """Capture complete corpus content before the unchanged consent-gated benchmark."""
    behaviors, nodes = tuple(behavioral_cases), tuple(node_code_cases)
    corpus = _snapshot(behaviors, nodes)
    digest = _json_sha256(corpus)
    report = run_behavioral_code_benchmark(
        behaviors,
        nodes,
        provider,
        allow_untrusted_code_execution=allow_untrusted_code_execution,
        project_root=project_root,
        prompt_version=prompt_version,
        execution_config=execution_config,
        clock=clock,
    )
    return CorpusBoundCodeBenchmarkReport(report, corpus, digest)


def create_corpus_bound_code_artifact(
    report: CorpusBoundCodeBenchmarkReport,
    provenance: BehavioralBenchmarkProvenance,
    configuration: BehavioralBenchmarkConfiguration,
    *,
    mode: Literal["live", "replay"] = "live",
    source_artifact_sha256: str | None = None,
) -> CorpusBoundCodeBenchmarkArtifact:
    """Wrap newly captured evidence; never infer corpus identity from legacy files."""
    return CorpusBoundCodeBenchmarkArtifact(
        CORPUS_BOUND_CODE_ARTIFACT_SCHEMA_VERSION,
        report.corpus_sha256,
        report.corpus,
        create_behavioral_benchmark_artifact(
            report.benchmark,
            provenance,
            configuration,
            mode=mode,
            source_artifact_sha256=source_artifact_sha256,
        ),
    )


def corpus_bound_code_artifact_to_dict(
    artifact: CorpusBoundCodeBenchmarkArtifact,
) -> dict[str, object]:
    """Serialize the distinct complete-corpus envelope."""
    return {
        "schema_version": artifact.schema_version,
        "artifact_kind": "corpus-bound-full-code",
        "corpus_sha256": artifact.corpus_sha256,
        "corpus": artifact.corpus,
        "benchmark": behavioral_benchmark_artifact_to_dict(artifact.benchmark),
    }


def corpus_bound_code_artifact_from_dict(payload: object) -> CorpusBoundCodeBenchmarkArtifact:
    """Strictly decode and revalidate the complete evidence envelope."""
    data = _object(payload, "corpus-bound code artifact")
    _exact_keys(data, _KEYS, "corpus-bound code artifact")
    if data["artifact_kind"] != "corpus-bound-full-code":
        raise ValueError("artifact_kind must be corpus-bound-full-code")
    return CorpusBoundCodeBenchmarkArtifact(
        _string(data["schema_version"], "schema_version"),
        _string(data["corpus_sha256"], "corpus_sha256"),
        _object(data["corpus"], "corpus"),
        behavioral_benchmark_artifact_from_dict(data["benchmark"]),
    )


def corpus_bound_code_artifact_sha256(artifact: CorpusBoundCodeBenchmarkArtifact) -> str:
    """Hash the whole envelope, including corpus and full-code evidence."""
    return _json_sha256(corpus_bound_code_artifact_to_dict(artifact))


def load_corpus_bound_code_artifact(path: str | Path) -> CorpusBoundCodeBenchmarkArtifact:
    """Load strict JSON, rejecting duplicates and incompatible legacy files."""
    try:
        return corpus_bound_code_artifact_from_dict(
            json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        )
    except (OSError, ValueError) as error:
        raise BehavioralBenchmarkArtifactError(
            f"cannot load corpus-bound code artifact: {error}"
        ) from error


def write_corpus_bound_code_artifact(
    path: str | Path, artifact: CorpusBoundCodeBenchmarkArtifact
) -> None:
    """Revalidate mutable containers and atomically publish without overwrite."""
    payload = corpus_bound_code_artifact_to_dict(artifact)
    corpus_bound_code_artifact_from_dict(payload)
    write_json_exclusive(path, payload)


def replay_corpus_bound_code_benchmark(  # noqa: PLR0913
    artifact: CorpusBoundCodeBenchmarkArtifact,
    behavioral_cases: Sequence[BehavioralCase],
    node_code_cases: Sequence[NodeCodeCase],
    *,
    allow_untrusted_code_execution: bool = False,
    project_root: str | Path = ".",
    execution_config: BehavioralExecutionConfig | None = None,
) -> CorpusBoundCodeBenchmarkReport:
    """Require the original corpus before serving recorded raw full-code responses."""
    artifact = corpus_bound_code_artifact_from_dict(corpus_bound_code_artifact_to_dict(artifact))
    if _json_sha256(_snapshot(behavioral_cases, node_code_cases)) != artifact.corpus_sha256:
        raise ValueError("corpus-bound replay requires the exact recorded corpus")
    report = replay_behavioral_benchmark(
        artifact.benchmark,
        behavioral_cases,
        node_code_cases,
        allow_untrusted_code_execution=allow_untrusted_code_execution,
        project_root=project_root,
        execution_config=execution_config,
    )
    return CorpusBoundCodeBenchmarkReport(report, artifact.corpus, artifact.corpus_sha256)
