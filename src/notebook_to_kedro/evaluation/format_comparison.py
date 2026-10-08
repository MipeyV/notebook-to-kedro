"""Corpus-bound comparisons of full-code and deterministically assembled bodies."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from notebook_to_kedro.evaluation.behavioral_artifacts import (
    _classify_change,
    _exact_keys,
    _integer,
    _json_sha256,
    _number,
    _object,
    _proposals_by_id,
    _scenario_statuses,
    behavioral_benchmark_artifact_to_dict,
    compare_behavioral_benchmark_artifacts,
)
from notebook_to_kedro.evaluation.corpus_bound_code import (
    _decode_corpus,
    corpus_bound_code_artifact_from_dict,
    corpus_bound_code_artifact_to_dict,
    validate_recorded_corpus,
)
from notebook_to_kedro.evaluation.node_body_artifacts import (
    node_body_benchmark_artifact_from_dict,
    node_body_benchmark_artifact_to_dict,
)
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError

if TYPE_CHECKING:
    from notebook_to_kedro.evaluation.behavioral_artifacts import BehavioralBenchmarkArtifact
    from notebook_to_kedro.evaluation.corpus_bound_code import CorpusBoundCodeBenchmarkArtifact
    from notebook_to_kedro.evaluation.node_body_artifacts import NodeBodyBenchmarkArtifact

FORMAT_COMPARISON_SCHEMA_VERSION = "1.0"


def compare_generation_formats(
    full_code: CorpusBoundCodeBenchmarkArtifact,
    node_body: NodeBodyBenchmarkArtifact,
) -> dict[str, object]:
    """Compare complete corpus evidence, without model calls or code execution."""
    full_payload = corpus_bound_code_artifact_to_dict(full_code)
    body_payload = node_body_benchmark_artifact_to_dict(node_body)
    full_code = corpus_bound_code_artifact_from_dict(full_payload)
    node_body = node_body_benchmark_artifact_from_dict(body_payload)
    if full_code.corpus_sha256 != node_body.corpus_sha256:
        raise BehavioralBenchmarkArtifactError("format comparison requires the exact same corpus")
    behaviors, nodes = _decode_corpus(full_code.corpus)
    left, right = full_code.benchmark, node_body.benchmark
    validate_recorded_corpus(right, behaviors, nodes)
    _validate_summary(left)
    _validate_summary(right)
    if left.configuration != right.configuration or any(
        left.report[key] != right.report[key]
        for key in ("validator_version", "execution_policy", "provider_name", "model_name")
    ):
        raise BehavioralBenchmarkArtifactError(
            "format comparison requires matching model and execution settings"
        )
    if (left.provenance.python_version, left.provenance.platform) != (
        right.provenance.python_version,
        right.provenance.platform,
    ):
        raise BehavioralBenchmarkArtifactError(
            "format comparison requires matching Python/platform"
        )
    live = left.mode == right.mode == "live"
    if live:
        _validate_live_identity(left, right)
    comparison = compare_behavioral_benchmark_artifacts(left, right)
    baseline_statuses, candidate_statuses = (
        _scenario_statuses(left.report),
        _scenario_statuses(right.report),
    )
    comparison.update(
        schema_version=FORMAT_COMPARISON_SCHEMA_VERSION,
        artifact_kind="generation-format-comparison",
        corpus_sha256=full_code.corpus_sha256,
        baseline_artifact_sha256=_json_sha256(full_payload),
        candidate_artifact_sha256=_json_sha256(body_payload),
        comparison_scope="recorded-live-controls" if live else "outcomes-only",
        baseline_metadata=_metadata(left, "corpus-bound-full-code"),
        candidate_metadata={
            **_metadata(right, "node-body"),
            "assembly_version": node_body.assembly_version,
            "body_schema_version": node_body.body_schema_version,
            "parameter_evidence_version": node_body.parameter_evidence_version,
        },
        baseline_summary=left.report["summary"],
        candidate_summary=right.report["summary"],
        scenario_changes=[
            {
                "case_id": case.case_id,
                "baseline_status": baseline_statuses.get(case.case_id, "not_evaluated"),
                "candidate_status": candidate_statuses.get(case.case_id, "not_evaluated"),
                "change": _classify_change(
                    baseline_status=baseline_statuses.get(case.case_id, "not_evaluated"),
                    candidate_status=candidate_statuses.get(case.case_id, "not_evaluated"),
                    success_status="matched",
                ),
            }
            for case in sorted(behaviors, key=lambda c: c.case_id)
        ],
        proposal_diagnostics=_diagnostics(left, right),
    )
    return comparison


def _validate_live_identity(
    left: BehavioralBenchmarkArtifact, right: BehavioralBenchmarkArtifact
) -> None:
    for name in ("repository_revision", "ollama_version", "model_digest"):
        actual, expected = getattr(left.provenance, name), getattr(right.provenance, name)
        if actual != expected or actual is None:
            raise BehavioralBenchmarkArtifactError(
                f"live format comparison requires matching known {name}"
            )


def _metadata(artifact: BehavioralBenchmarkArtifact, kind: str) -> dict[str, object]:
    payload = behavioral_benchmark_artifact_to_dict(artifact)
    return {
        "artifact_kind": kind,
        "mode": artifact.mode,
        "provider_name": artifact.report["provider_name"],
        "model_name": artifact.report["model_name"],
        "prompt_version": artifact.report["prompt_version"],
        "configuration": payload["configuration"],
        "provenance": payload["provenance"],
    }


def _diagnostics(
    left: BehavioralBenchmarkArtifact, right: BehavioralBenchmarkArtifact
) -> list[dict[str, object]]:
    baseline, candidate = _proposals_by_id(left.report), _proposals_by_id(right.report)
    return [
        {
            "node_code_case_id": case_id,
            "baseline_code": baseline[case_id]["diagnostic_code"],
            "baseline_message": baseline[case_id]["diagnostic_message"],
            "candidate_code": candidate[case_id]["diagnostic_code"],
            "candidate_message": candidate[case_id]["diagnostic_message"],
        }
        for case_id in sorted(baseline)
    ]


def _validate_summary(artifact: BehavioralBenchmarkArtifact) -> None:
    proposals = _proposals_by_id(artifact.report)
    statuses = _scenario_statuses(artifact.report)
    if not proposals or set(statuses.values()) - {"matched", "mismatch", "execution_error"}:
        raise ValueError(
            "format comparison requires nonempty proposals and known scenario statuses"
        )
    count = cast("int", artifact.report["scenario_count"])
    accepted = sum(p["status"] == "accepted" for p in proposals.values())
    matched = sum(status == "matched" for status in statuses.values())
    provider_duration = sum(
        _number(p["proposal_duration_seconds"], "proposal_duration_seconds")
        for p in proposals.values()
    )
    execution_duration = sum(
        _number(
            _object(_object(e, "evaluation")["execution"], "execution")["duration_seconds"],
            "duration_seconds",
        )
        for p in proposals.values()
        for e in cast("list[object]", p["evaluations"])
    )
    expected = {
        "proposal_count": len(proposals),
        "scenario_count": count,
        "accepted_count": accepted,
        "accepted_rate": accepted / len(proposals),
        "evaluated_scenario_count": len(statuses),
        "not_evaluated_scenario_count": count - len(statuses),
        "matched_scenario_count": matched,
        "evaluated_match_rate": matched / len(statuses) if statuses else 0.0,
        "end_to_end_match_rate": matched / count,
        "mismatch_scenario_count": sum(status == "mismatch" for status in statuses.values()),
        "execution_error_scenario_count": sum(
            status == "execution_error" for status in statuses.values()
        ),
        "provider_duration_seconds": provider_duration,
        "mean_provider_duration_seconds": provider_duration / len(proposals),
        "execution_duration_seconds": execution_duration,
        **{
            name + "_count": sum(p["status"] == name for p in proposals.values())
            for name in ("provider_error", "invalid_response", "invalid_code")
        },
    }
    summary = _object(artifact.report["summary"], "summary")
    _exact_keys(summary, frozenset(expected), "benchmark summary")
    if any(
        (_integer(summary[key], key) if key.endswith("_count") else _number(summary[key], key))
        != value
        for key, value in expected.items()
    ):
        raise ValueError("summary counts and rates must match recorded outcomes")
