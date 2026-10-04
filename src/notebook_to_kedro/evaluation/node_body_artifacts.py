"""Distinct body-only artifact envelopes and consent-gated offline replay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.evaluation.behavioral_artifacts import (
    BehavioralBenchmarkArtifact,
    _exact_keys,
    _is_sha256,
    _json_sha256,
    _object,
    _proposals_by_id,
    _RecordedNodeCodeProvider,
    _string,
    _to_json,
    behavioral_benchmark_artifact_from_dict,
    behavioral_benchmark_artifact_to_dict,
    create_behavioral_benchmark_artifact,
    write_json_exclusive,
)
from notebook_to_kedro.evaluation.node_body_benchmark import (
    NodeBodyBenchmarkReport,
    _corpus_sha256,
    run_node_body_benchmark,
)
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError
from notebook_to_kedro.generation.code import (
    NODE_BODY_ASSEMBLY_VERSION,
    NODE_BODY_SCHEMA_VERSION,
    NODE_CODE_PARAMETER_EVIDENCE_VERSION,
    NODE_CODE_VALIDATOR_VERSION,
    NodeBodyResponse,
    NodeCodeRequest,
    NodeCodeResponse,
    assemble_node_body,
)
from notebook_to_kedro.generation.code.serialization import _unique_object

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Literal

    from notebook_to_kedro.evaluation.behavioral import BehavioralCase
    from notebook_to_kedro.evaluation.behavioral_artifacts import (
        BehavioralBenchmarkConfiguration,
        BehavioralBenchmarkProvenance,
    )
    from notebook_to_kedro.evaluation.behavioral_execution import BehavioralExecutionConfig
    from notebook_to_kedro.evaluation.node_code_corpus import NodeCodeCase

NODE_BODY_BENCHMARK_ARTIFACT_SCHEMA_VERSION = "1.0"
_KEYS = frozenset(
    {
        "schema_version",
        "artifact_kind",
        "body_schema_version",
        "assembly_version",
        "parameter_evidence_version",
        "corpus_sha256",
        "body_responses",
        "benchmark",
    }
)


@dataclass(frozen=True, slots=True)
class NodeBodyBenchmarkArtifact:
    """Versioned body evidence wrapping unchanged behavioral metrics and provenance."""

    schema_version: str
    body_schema_version: str
    assembly_version: str
    parameter_evidence_version: str
    corpus_sha256: str
    body_responses: dict[str, NodeBodyResponse | None]
    benchmark: BehavioralBenchmarkArtifact

    def __post_init__(self) -> None:
        versions = (
            (self.schema_version, NODE_BODY_BENCHMARK_ARTIFACT_SCHEMA_VERSION),
            (self.body_schema_version, NODE_BODY_SCHEMA_VERSION),
            (self.assembly_version, NODE_BODY_ASSEMBLY_VERSION),
            (self.parameter_evidence_version, NODE_CODE_PARAMETER_EVIDENCE_VERSION),
        )
        if any(actual != expected for actual, expected in versions):
            raise ValueError("unsupported body benchmark version")
        if not _is_sha256(self.corpus_sha256):
            raise ValueError("corpus_sha256 must be a lowercase SHA-256 digest")
        if self.benchmark.configuration.include_parameter_evidence is not True:
            raise ValueError("body benchmarks require exact parameter evidence")
        if not _string(self.benchmark.report["prompt_version"], "prompt_version").strip():
            raise ValueError("body prompt_version must not be empty")
        proposals = _proposals_by_id(self.benchmark.report)
        if proposals.keys() != self.body_responses.keys():
            raise ValueError("body response case IDs must match benchmark proposals exactly")
        for case_id, proposal in proposals.items():
            _validate_body_record(proposal, self.body_responses[case_id])


def _validate_body_record(proposal: dict[str, object], body: NodeBodyResponse | None) -> None:
    raw = proposal.get("raw_response")
    status = proposal["status"]
    if status == "provider_error":
        if raw is not None or body is not None or proposal.get("response") is not None:
            raise ValueError("provider errors must not contain model responses")
    else:
        raw = _string(raw, "raw_response")
        try:
            parsed = NodeBodyResponse.from_json(raw)
        except ValueError:
            parsed = None
        if parsed != body or (parsed is None) != (status == "invalid_response"):
            raise ValueError("parsed body and status must match the raw response")
        if status == "accepted":
            request = NodeCodeRequest.from_json(_to_json(_object(proposal["request"], "request")))
            response = NodeCodeResponse.from_json(
                _to_json(_object(proposal["response"], "response"))
            )
            assert body is not None
            if assemble_node_body(request, body) != response:
                raise ValueError("assembled response must match the recorded body")
        elif proposal.get("response") is not None:
            raise ValueError("rejected body proposals must not contain an assembled response")
    if status != "accepted" and proposal.get("evaluations") != []:
        raise ValueError("rejected body proposals must not have evaluations")


def create_node_body_benchmark_artifact(
    report: NodeBodyBenchmarkReport,
    provenance: BehavioralBenchmarkProvenance,
    configuration: BehavioralBenchmarkConfiguration,
    *,
    mode: Literal["live", "replay"] = "live",
    source_artifact_sha256: str | None = None,
) -> NodeBodyBenchmarkArtifact:
    """Capture bodies and benchmark outcomes without writing or invoking a model."""
    if len(report.body_responses) != len(report.benchmark.proposals):
        raise ValueError("one body response entry is required per benchmark proposal")
    return NodeBodyBenchmarkArtifact(
        NODE_BODY_BENCHMARK_ARTIFACT_SCHEMA_VERSION,
        NODE_BODY_SCHEMA_VERSION,
        NODE_BODY_ASSEMBLY_VERSION,
        NODE_CODE_PARAMETER_EVIDENCE_VERSION,
        report.corpus_sha256,
        dict(
            zip(
                (proposal.node_code_case_id for proposal in report.benchmark.proposals),
                report.body_responses,
                strict=True,
            )
        ),
        create_behavioral_benchmark_artifact(
            report.benchmark,
            provenance,
            configuration,
            mode=mode,
            source_artifact_sha256=source_artifact_sha256,
        ),
    )


def node_body_benchmark_artifact_to_dict(artifact: NodeBodyBenchmarkArtifact) -> dict[str, object]:
    """Serialize the explicitly tagged body-only envelope."""
    return {
        "schema_version": artifact.schema_version,
        "artifact_kind": "node-body",
        "body_schema_version": artifact.body_schema_version,
        "assembly_version": artifact.assembly_version,
        "parameter_evidence_version": artifact.parameter_evidence_version,
        "corpus_sha256": artifact.corpus_sha256,
        "body_responses": {
            case_id: None if body is None else json.loads(body.to_json())
            for case_id, body in artifact.body_responses.items()
        },
        "benchmark": behavioral_benchmark_artifact_to_dict(artifact.benchmark),
    }


def node_body_benchmark_artifact_to_json(
    artifact: NodeBodyBenchmarkArtifact, *, indent: int | None = 2
) -> str:
    """Encode stable JSON without persisting it."""
    return _to_json(node_body_benchmark_artifact_to_dict(artifact), indent=indent)


def node_body_benchmark_artifact_sha256(artifact: NodeBodyBenchmarkArtifact) -> str:
    """Hash the whole envelope, including body and assembly provenance."""
    return _json_sha256(node_body_benchmark_artifact_to_dict(artifact))


def node_body_benchmark_artifact_from_dict(payload: object) -> NodeBodyBenchmarkArtifact:
    """Decode the exact body-only envelope and recheck raw/parsed/assembled evidence."""
    data = _object(payload, "body benchmark artifact")
    _exact_keys(data, _KEYS, "body benchmark artifact")
    if data["artifact_kind"] != "node-body":
        raise ValueError("artifact_kind must be node-body")
    bodies = _object(data["body_responses"], "body_responses")
    return NodeBodyBenchmarkArtifact(
        schema_version=_string(data["schema_version"], "schema_version"),
        body_schema_version=_string(data["body_schema_version"], "body_schema_version"),
        assembly_version=_string(data["assembly_version"], "assembly_version"),
        parameter_evidence_version=_string(
            data["parameter_evidence_version"], "parameter_evidence_version"
        ),
        corpus_sha256=_string(data["corpus_sha256"], "corpus_sha256"),
        body_responses={
            case_id: None
            if body is None
            else NodeBodyResponse.from_json(_to_json(_object(body, "body response")))
            for case_id, body in bodies.items()
        },
        benchmark=behavioral_benchmark_artifact_from_dict(data["benchmark"]),
    )


def node_body_benchmark_artifact_from_json(payload: str) -> NodeBodyBenchmarkArtifact:
    """Decode strict JSON, rejecting duplicate keys throughout the envelope."""
    return node_body_benchmark_artifact_from_dict(
        json.loads(payload, object_pairs_hook=_unique_object)
    )


def load_node_body_benchmark_artifact(path: str | Path) -> NodeBodyBenchmarkArtifact:
    """Read one body-only artifact with normalized I/O and validation failures."""
    try:
        return node_body_benchmark_artifact_from_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BehavioralBenchmarkArtifactError(
            f"cannot load body benchmark artifact: {error}"
        ) from error


def write_node_body_benchmark_artifact(
    path: str | Path, artifact: NodeBodyBenchmarkArtifact
) -> None:
    """Revalidate and publish exclusively using the existing atomic writer."""
    payload = node_body_benchmark_artifact_to_dict(artifact)
    node_body_benchmark_artifact_from_dict(payload)
    write_json_exclusive(path, payload)


def replay_node_body_benchmark(  # noqa: PLR0913
    artifact: NodeBodyBenchmarkArtifact,
    behavioral_cases: Sequence[BehavioralCase],
    node_code_cases: Sequence[NodeCodeCase],
    *,
    allow_untrusted_code_execution: bool = False,
    project_root: str | Path = ".",
    execution_config: BehavioralExecutionConfig | None = None,
) -> NodeBodyBenchmarkReport:
    """Reassemble recorded bodies on the exact corpus, without contacting Ollama."""
    artifact = node_body_benchmark_artifact_from_dict(
        node_body_benchmark_artifact_to_dict(artifact)
    )
    if artifact.benchmark.report["validator_version"] != NODE_CODE_VALIDATOR_VERSION:
        raise ValueError("body replay requires the recorded validator version")
    if artifact.corpus_sha256 != _corpus_sha256(behavioral_cases, node_code_cases):
        raise ValueError("body replay requires the exact recorded corpus")
    nodes = {node.case_id: node for node in node_code_cases}
    proposals = _proposals_by_id(artifact.benchmark.report)
    if proposals.keys() != nodes.keys() or artifact.benchmark.report["scenario_count"] != len(
        behavioral_cases
    ):
        raise ValueError("recorded benchmark must cover the exact corpus")
    for case_id, proposal in proposals.items():
        node = nodes[case_id]
        if (
            proposal["request"] != json.loads(node.request.to_json())
            or proposal["source_sha256"] != node.source_sha256
            or proposal["notebook_path"] != node.notebook_path
        ):
            raise ValueError("recorded source identity must match the corpus")
    provider = _RecordedBodyProvider(artifact.benchmark.report)
    return run_node_body_benchmark(
        behavioral_cases,
        node_code_cases,
        provider,
        allow_untrusted_code_execution=allow_untrusted_code_execution,
        project_root=project_root,
        execution_config=execution_config or artifact.benchmark.configuration.execution,
        clock=lambda: 0.0,
    )


class _RecordedBodyProvider(_RecordedNodeCodeProvider):
    """Serve raw bodies and recorded transport failures; never serve cached full code."""

    def __init__(self, report: dict[str, object]) -> None:
        super().__init__(report)
        self.prompt_version = _string(report["prompt_version"], "prompt_version")
