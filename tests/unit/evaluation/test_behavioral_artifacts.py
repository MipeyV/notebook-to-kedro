from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Self, cast
from urllib.error import URLError

import pytest

from notebook_to_kedro.evaluation import (
    BEHAVIORAL_BENCHMARK_ARTIFACT_SCHEMA_VERSION,
    BEHAVIORAL_BENCHMARK_COMPARISON_SCHEMA_VERSION,
    BEHAVIORAL_CODE_BENCHMARK_SCHEMA_VERSION,
    BEHAVIORAL_PROPOSAL_EXECUTION_POLICY,
    BehavioralBenchmarkArtifact,
    BehavioralBenchmarkConfiguration,
    BehavioralBenchmarkProvenance,
    BehavioralCodeBenchmarkProposal,
    BehavioralCodeBenchmarkReport,
    BehavioralExecutionConfig,
    behavioral_benchmark_artifact_from_dict,
    behavioral_benchmark_artifact_from_json,
    behavioral_benchmark_artifact_sha256,
    behavioral_benchmark_artifact_to_dict,
    behavioral_benchmark_artifact_to_json,
    collect_environment_provenance,
    compare_behavioral_benchmark_artifacts,
    create_behavioral_benchmark_artifact,
    load_behavioral_benchmark_artifact,
    load_behavioral_corpus,
    load_node_code_corpus,
    replay_behavioral_benchmark,
    write_behavioral_benchmark_artifact,
    write_json_exclusive,
)
from notebook_to_kedro.evaluation import behavioral_artifacts as artifacts
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError
from notebook_to_kedro.generation.code import NODE_CODE_VALIDATOR_VERSION

ROOT = Path(__file__).parents[3]
BEHAVIOR_DIRECTORY = ROOT / "tests/fixtures/evaluation/behavioral/v1"
NODE_DIRECTORY = ROOT / "tests/fixtures/evaluation/node_code/v1"
MODEL_DIGEST = "a" * 64


class _Response(BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _provenance() -> BehavioralBenchmarkProvenance:
    return BehavioralBenchmarkProvenance(
        created_at_utc="2026-10-01T10:00:00Z",
        repository_revision="abc123",
        python_version="3.12.14",
        platform="win32",
        ollama_version="0.34.4",
        model_digest=MODEL_DIGEST,
    )


def _configuration() -> BehavioralBenchmarkConfiguration:
    return BehavioralBenchmarkConfiguration(
        ollama_base_url="http://127.0.0.1:11434/",
        provider_timeout_seconds=120,
        include_parameter_evidence=True,
        execution=BehavioralExecutionConfig(timeout_seconds=7),
    )


def _report() -> BehavioralCodeBenchmarkReport:
    nodes = load_node_code_corpus(NODE_DIRECTORY)
    proposals = []
    for index, node in enumerate(nodes):
        if index == 0:
            proposals.append(
                BehavioralCodeBenchmarkProposal(
                    node_code_case_id=node.case_id,
                    notebook_path=node.notebook_path,
                    source_sha256=node.source_sha256,
                    request=node.request,
                    status="invalid_response",
                    raw_response="not-json",
                    diagnostic_code="invalid_response",
                    diagnostic_message="recorded invalid JSON",
                )
            )
        else:
            proposals.append(
                BehavioralCodeBenchmarkProposal(
                    node_code_case_id=node.case_id,
                    notebook_path=node.notebook_path,
                    source_sha256=node.source_sha256,
                    request=node.request,
                    status="provider_error",
                    diagnostic_code="ollama_timeout",
                    diagnostic_message="timed out",
                )
            )
    return BehavioralCodeBenchmarkReport(
        schema_version=BEHAVIORAL_CODE_BENCHMARK_SCHEMA_VERSION,
        provider_name="ollama",
        model_name="qwen3:8b",
        prompt_version="node-code-v4",
        validator_version=NODE_CODE_VALIDATOR_VERSION,
        execution_policy=BEHAVIORAL_PROPOSAL_EXECUTION_POLICY,
        scenario_count=5,
        proposals=tuple(proposals),
    )


@pytest.fixture
def artifact() -> BehavioralBenchmarkArtifact:
    return create_behavioral_benchmark_artifact(_report(), _provenance(), _configuration())


def _artifact_with_payload(
    source: BehavioralBenchmarkArtifact,
    mutate: Any,
    *,
    mode: str = "live",
) -> BehavioralBenchmarkArtifact:
    payload = json.loads(behavioral_benchmark_artifact_to_json(source))
    mutate(payload)
    payload["mode"] = mode
    payload["source_artifact_sha256"] = "b" * 64 if mode == "replay" else None
    report_json = json.dumps(payload["report"], sort_keys=True, separators=(",", ":"))
    payload["report_sha256"] = hashlib.sha256(report_json.encode()).hexdigest()
    return behavioral_benchmark_artifact_from_dict(payload)


def test_artifact_round_trip_and_stable_identity(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    payload = behavioral_benchmark_artifact_to_dict(artifact)
    encoded = behavioral_benchmark_artifact_to_json(artifact)

    assert artifact.schema_version == BEHAVIORAL_BENCHMARK_ARTIFACT_SCHEMA_VERSION
    assert behavioral_benchmark_artifact_from_dict(payload) == artifact
    assert behavioral_benchmark_artifact_from_json(encoded) == artifact
    assert json.loads(behavioral_benchmark_artifact_to_json(artifact, indent=None)) == payload
    assert len(behavioral_benchmark_artifact_sha256(artifact)) == 64
    assert artifact.configuration.ollama_base_url == "http://127.0.0.1:11434"


def test_artifact_write_load_and_existing_output_refusal(
    tmp_path: Path, artifact: BehavioralBenchmarkArtifact
) -> None:
    output = tmp_path / "nested" / "artifact.json"

    write_behavioral_benchmark_artifact(output, artifact)

    assert load_behavioral_benchmark_artifact(output) == artifact
    assert not tuple(output.parent.glob("*.tmp"))
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        write_behavioral_benchmark_artifact(output, artifact)
    assert load_behavioral_benchmark_artifact(output) == artifact


def test_generic_exclusive_writer_reports_io_failures(tmp_path: Path) -> None:
    parent_file = tmp_path / "parent"
    parent_file.write_text("occupied", encoding="utf-8")

    with pytest.raises(BehavioralBenchmarkArtifactError, match="cannot write"):
        write_json_exclusive(parent_file / "result.json", {"ok": True})


def test_generic_exclusive_writer_wraps_publish_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny_link(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr("notebook_to_kedro.evaluation.behavioral_artifacts.os.link", deny_link)
    with pytest.raises(BehavioralBenchmarkArtifactError, match="cannot write"):
        write_json_exclusive(tmp_path / "result.json", {"ok": True})
    assert not tuple(tmp_path.glob("*.tmp"))


def test_generic_exclusive_writer_wraps_temporary_file_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny_temporary_file(*_args: object, **_kwargs: object) -> tuple[int, str]:
        raise PermissionError("denied")

    monkeypatch.setattr(
        "notebook_to_kedro.evaluation.behavioral_artifacts.tempfile.mkstemp",
        deny_temporary_file,
    )
    with pytest.raises(BehavioralBenchmarkArtifactError, match="cannot write"):
        write_json_exclusive(tmp_path / "result.json", {"ok": True})


def test_artifact_loader_wraps_read_and_validation_errors(tmp_path: Path) -> None:
    with pytest.raises(BehavioralBenchmarkArtifactError, match="cannot read"):
        load_behavioral_benchmark_artifact(tmp_path / "missing.json")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    with pytest.raises(BehavioralBenchmarkArtifactError, match=r"invalid.*JSON"):
        load_behavioral_benchmark_artifact(invalid)


def test_replay_uses_only_recorded_provider_outcomes(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    report = replay_behavioral_benchmark(
        artifact,
        load_behavioral_corpus(BEHAVIOR_DIRECTORY),
        load_node_code_corpus(NODE_DIRECTORY),
        allow_untrusted_code_execution=True,
        project_root=ROOT,
        execution_config=BehavioralExecutionConfig(timeout_seconds=3),
    )

    assert tuple(proposal.status for proposal in report.proposals) == (
        "invalid_response",
        "provider_error",
        "provider_error",
        "provider_error",
    )
    assert all(proposal.proposal_duration_seconds == 0 for proposal in report.proposals)
    assert report.provider_name == "ollama"
    assert report.model_name == "qwen3:8b"


def test_replay_reports_missing_recorded_requests(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    def mutate(payload: dict[str, object]) -> None:
        report = cast("dict[str, Any]", payload["report"])
        report["proposals"][0]["request"]["request_id"] = "different-request"

    changed = _artifact_with_payload(artifact, mutate)
    report = replay_behavioral_benchmark(
        changed,
        load_behavioral_corpus(BEHAVIOR_DIRECTORY),
        load_node_code_corpus(NODE_DIRECTORY),
        allow_untrusted_code_execution=True,
        project_root=ROOT,
    )

    assert report.proposals[0].status == "provider_error"
    assert report.proposals[0].diagnostic_code == "replay_missing_response"


def test_replay_reports_missing_raw_response(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    def mutate(payload: dict[str, object]) -> None:
        report = cast("dict[str, Any]", payload["report"])
        report["proposals"][0]["raw_response"] = None

    changed = _artifact_with_payload(artifact, mutate)
    report = replay_behavioral_benchmark(
        changed,
        load_behavioral_corpus(BEHAVIOR_DIRECTORY),
        load_node_code_corpus(NODE_DIRECTORY),
        allow_untrusted_code_execution=True,
        project_root=ROOT,
    )

    assert report.proposals[0].status == "provider_error"
    assert report.proposals[0].diagnostic_code == "replay_missing_response"


def test_comparison_reports_regressions_improvements_and_changed_failures(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    def baseline_mutation(payload: dict[str, object]) -> None:
        report = cast("dict[str, Any]", payload["report"])
        proposals = report["proposals"]
        proposals[0]["status"] = "accepted"
        proposals[0]["evaluations"] = [
            {"case_id": "scenario-a", "comparison": {"status": "matched"}},
            {"case_id": "scenario-b", "comparison": {"status": "mismatch"}},
        ]
        report["summary"]["accepted_rate"] = 0.5
        report["summary"]["end_to_end_match_rate"] = 0.4
        report["summary"]["provider_duration_seconds"] = 10.0
        report["summary"]["execution_duration_seconds"] = 2.0

    def candidate_mutation(payload: dict[str, object]) -> None:
        report = cast("dict[str, Any]", payload["report"])
        proposals = report["proposals"]
        proposals[0]["status"] = "invalid_code"
        proposals[1]["status"] = "accepted"
        proposals[0]["evaluations"] = [
            {"case_id": "scenario-a", "comparison": {"status": "mismatch"}},
            {"case_id": "scenario-b", "comparison": {"status": "matched"}},
            {"case_id": "scenario-c", "comparison": {"status": "execution_error"}},
        ]
        report["summary"]["accepted_rate"] = 0.75
        report["summary"]["end_to_end_match_rate"] = 0.6
        report["summary"]["provider_duration_seconds"] = 8.0
        report["summary"]["execution_duration_seconds"] = 3.0

    baseline = _artifact_with_payload(artifact, baseline_mutation)
    candidate = _artifact_with_payload(artifact, candidate_mutation, mode="replay")

    comparison = cast("dict[str, Any]", compare_behavioral_benchmark_artifacts(baseline, candidate))

    assert comparison["schema_version"] == BEHAVIORAL_BENCHMARK_COMPARISON_SCHEMA_VERSION
    assert comparison["regressed_proposal_count"] == 1
    assert comparison["regressed_scenario_count"] == 1
    assert [item["change"] for item in comparison["proposal_changes"][:2]] == [
        "regressed",
        "improved",
    ]
    assert [item["change"] for item in comparison["scenario_changes"]] == [
        "regressed",
        "improved",
        "changed",
    ]
    metrics = comparison["metrics"]
    assert metrics["accepted_rate"]["delta"] == pytest.approx(0.25)
    assert metrics["provider_duration_seconds"]["comparable"] is False
    assert metrics["provider_duration_seconds"]["delta"] is None


def test_comparison_reports_comparable_live_latency(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    def mutate(payload: dict[str, object]) -> None:
        report = cast("dict[str, Any]", payload["report"])
        report["summary"]["provider_duration_seconds"] = 5.0

    candidate = _artifact_with_payload(artifact, mutate)
    comparison = cast("dict[str, Any]", compare_behavioral_benchmark_artifacts(artifact, candidate))

    latency = comparison["metrics"]["provider_duration_seconds"]
    assert latency == {"baseline": 0.0, "candidate": 5.0, "delta": 5.0, "comparable": True}


def test_comparison_requires_identical_node_case_sets(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    def mutate(payload: dict[str, object]) -> None:
        report = cast("dict[str, Any]", payload["report"])
        report["proposals"].pop()

    candidate = _artifact_with_payload(artifact, mutate)
    with pytest.raises(BehavioralBenchmarkArtifactError, match="same node code case IDs"):
        compare_behavioral_benchmark_artifacts(artifact, candidate)


def test_collect_environment_provenance_with_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        (
            {"version": "0.34.4"},
            {"models": [{"name": "qwen3:8b", "digest": MODEL_DIGEST}]},
        )
    )
    monkeypatch.setattr(artifacts, "_http_json", lambda *_args: next(responses))
    monkeypatch.setattr(artifacts, "_repository_revision", lambda _root: "revision")

    provenance = collect_environment_provenance(
        project_root=ROOT,
        ollama_base_url="http://localhost:11434",
        model_name="qwen3:8b",
        now=datetime(2026, 10, 1, 12, 30, tzinfo=UTC),
    )

    assert provenance.created_at_utc == "2026-10-01T12:30:00Z"
    assert provenance.repository_revision == "revision"
    assert provenance.ollama_version == "0.34.4"
    assert provenance.model_digest == MODEL_DIGEST


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"ollama_base_url": "http://localhost:11434"}, "model_name"),
        ({"now": datetime(2026, 1, 1)}, "timezone-aware"),
    ],
)
def test_collect_environment_provenance_rejects_invalid_settings(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        collect_environment_provenance(**cast("Any", kwargs))


def test_http_json_is_bounded_and_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        artifacts,
        "urlopen",
        lambda *_args, **_kwargs: _Response(b'{"version":"0.34.4"}'),
    )
    assert artifacts._http_json("http://localhost/api/version", 1) == {"version": "0.34.4"}

    monkeypatch.setattr(
        artifacts,
        "urlopen",
        lambda *_args, **_kwargs: _Response(b"x" * (_MAX_METADATA_RESPONSE_BYTES + 1)),
    )
    with pytest.raises(BehavioralBenchmarkArtifactError, match="too large"):
        artifacts._http_json("http://localhost/api/version", 1)


_MAX_METADATA_RESPONSE_BYTES = 1_000_000


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"\xff"])
def test_http_json_rejects_invalid_responses(monkeypatch: pytest.MonkeyPatch, body: bytes) -> None:
    monkeypatch.setattr(artifacts, "urlopen", lambda *_args, **_kwargs: _Response(body))
    with pytest.raises((BehavioralBenchmarkArtifactError, ValueError)):
        artifacts._http_json("http://localhost/api/version", 1)


def test_http_json_wraps_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> _Response:
        raise URLError("offline")

    monkeypatch.setattr(artifacts, "urlopen", unavailable)
    with pytest.raises(BehavioralBenchmarkArtifactError, match="collect local Ollama"):
        artifacts._http_json("http://localhost/api/version", 1)


@pytest.mark.parametrize(
    ("tags", "message"),
    [
        ({}, "models array"),
        ({"models": [{"name": "qwen3:8b", "digest": "bad"}]}, "SHA-256"),
        ({"models": [{"name": "other", "digest": MODEL_DIGEST}]}, "not found"),
    ],
)
def test_ollama_metadata_rejects_incomplete_evidence(
    monkeypatch: pytest.MonkeyPatch, tags: dict[str, object], message: str
) -> None:
    responses = iter(({"version": "0.34.4"}, tags))
    monkeypatch.setattr(artifacts, "_http_json", lambda *_args: next(responses))
    with pytest.raises(BehavioralBenchmarkArtifactError, match=message):
        artifacts._ollama_metadata("http://localhost:11434", "qwen3:8b", 1)


def test_ollama_metadata_accepts_model_alias_field(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        ({"version": "0.34.4"}, {"models": [{"model": "qwen3:8b", "digest": MODEL_DIGEST}]})
    )
    monkeypatch.setattr(artifacts, "_http_json", lambda *_args: next(responses))
    assert artifacts._ollama_metadata("http://localhost:11434", "qwen3:8b", 1) == (
        "0.34.4",
        MODEL_DIGEST,
    )


def test_repository_revision_handles_success_failure_and_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess((), 0, stdout="abc\n"),
    )
    assert artifacts._repository_revision(ROOT) == "abc"
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess((), 0, stdout=""),
    )
    assert artifacts._repository_revision(ROOT) is None

    def fail(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("git", 5)

    monkeypatch.setattr(subprocess, "run", fail)
    assert artifacts._repository_revision(ROOT) is None


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"schema_version": "2.0"}, "unsupported artifact"),
        ({"mode": "other"}, "unsupported artifact mode"),
        ({"report_sha256": "0" * 64}, "does not match"),
        ({"source_artifact_sha256": "bad"}, "source_artifact_sha256"),
    ],
)
def test_artifact_rejects_invalid_envelope(
    artifact: BehavioralBenchmarkArtifact,
    replacement: dict[str, object],
    message: str,
) -> None:
    payload = behavioral_benchmark_artifact_to_dict(artifact)
    payload.update(replacement)
    with pytest.raises(ValueError, match=message):
        behavioral_benchmark_artifact_from_dict(payload)


def test_artifact_requires_mode_specific_source_digest(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    payload = behavioral_benchmark_artifact_to_dict(artifact)
    payload["source_artifact_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="live artifacts"):
        behavioral_benchmark_artifact_from_dict(payload)
    payload["mode"] = "replay"
    payload["source_artifact_sha256"] = None
    with pytest.raises(ValueError, match="replay artifacts"):
        behavioral_benchmark_artifact_from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("created_at_utc", "not-a-date", "ISO-8601"),
        ("created_at_utc", "2026-10-01T10:00:00", "UTC"),
        ("python_version", "", "python_version"),
        ("platform", "", "platform"),
        ("repository_revision", "", "repository_revision"),
        ("ollama_version", "", "ollama_version"),
        ("model_digest", "BAD", "model_digest"),
    ],
)
def test_provenance_rejects_invalid_fields(field: str, value: object, message: str) -> None:
    kwargs: dict[str, object] = {
        "created_at_utc": "2026-10-01T10:00:00Z",
        "repository_revision": None,
        "python_version": "3.12",
        "platform": "win32",
        "ollama_version": None,
        "model_digest": None,
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match=message):
        BehavioralBenchmarkProvenance(**cast("Any", kwargs))


@pytest.mark.parametrize("timeout", [0, float("nan"), float("inf")])
def test_configuration_rejects_invalid_provider_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        BehavioralBenchmarkConfiguration(
            ollama_base_url="http://localhost:11434",
            provider_timeout_seconds=timeout,
            include_parameter_evidence=False,
        )


def test_strict_artifact_parser_rejects_wrong_shapes(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    payload = behavioral_benchmark_artifact_to_dict(artifact)
    payload["extra"] = True
    with pytest.raises(ValueError, match="invalid behavioral benchmark artifact fields"):
        behavioral_benchmark_artifact_from_dict(payload)
    with pytest.raises(ValueError, match="must be an object"):
        behavioral_benchmark_artifact_from_dict([])
    with pytest.raises(ValueError, match=r"invalid.*JSON"):
        behavioral_benchmark_artifact_from_json("{")


def test_report_validation_rejects_duplicate_and_invalid_identities(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    payload = behavioral_benchmark_artifact_to_dict(artifact)
    report = cast("dict[str, Any]", payload["report"])
    report["proposals"][1]["node_code_case_id"] = report["proposals"][0]["node_code_case_id"]
    report_json = json.dumps(report, sort_keys=True, separators=(",", ":"))
    payload["report_sha256"] = hashlib.sha256(report_json.encode()).hexdigest()
    with pytest.raises(ValueError, match="case IDs must be unique"):
        behavioral_benchmark_artifact_from_dict(payload)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda report: report.update(schema_version="2.0"), "unsupported benchmark report"),
        (lambda report: report.update(provider_name=""), "provider_name must not be empty"),
        (lambda report: report.update(proposals={}), "proposals must be an array"),
        (
            lambda report: report["proposals"][1]["request"].update(
                request_id=report["proposals"][0]["request"]["request_id"]
            ),
            "request IDs must be unique",
        ),
        (
            lambda report: report["proposals"][0].update(status="unknown"),
            "unsupported proposal status",
        ),
    ],
)
def test_report_validation_rejects_invalid_contracts(
    artifact: BehavioralBenchmarkArtifact, mutation: Any, message: str
) -> None:
    payload = behavioral_benchmark_artifact_to_dict(artifact)
    report = cast("dict[str, Any]", payload["report"])
    mutation(report)
    report_json = json.dumps(report, sort_keys=True, separators=(",", ":"))
    payload["report_sha256"] = hashlib.sha256(report_json.encode()).hexdigest()
    with pytest.raises(ValueError, match=message):
        behavioral_benchmark_artifact_from_dict(payload)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("provenance", "python_version"), 312, "must be a string"),
        (("configuration", "provider_timeout_seconds"), True, "must be a number"),
        (("configuration", "execution", "max_request_bytes"), 1.5, "must be an integer"),
        (("configuration", "include_parameter_evidence"), 1, "must be a boolean"),
    ],
)
def test_artifact_parser_rejects_scalar_types(
    artifact: BehavioralBenchmarkArtifact,
    path: tuple[str, ...],
    value: object,
    message: str,
) -> None:
    payload = behavioral_benchmark_artifact_to_dict(artifact)
    target = payload
    for component in path[:-1]:
        target = cast("dict[str, object]", target[component])
    target[path[-1]] = value
    with pytest.raises(ValueError, match=message):
        behavioral_benchmark_artifact_from_dict(payload)


def test_comparison_rejects_duplicate_scenario_ids(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    def mutate(payload: dict[str, object]) -> None:
        report = cast("dict[str, Any]", payload["report"])
        report["proposals"][0]["evaluations"] = [
            {"case_id": "same", "comparison": {"status": "matched"}},
            {"case_id": "same", "comparison": {"status": "matched"}},
        ]

    candidate = _artifact_with_payload(artifact, mutate)
    with pytest.raises(ValueError, match="evaluation case IDs must be unique"):
        compare_behavioral_benchmark_artifacts(artifact, candidate)


def test_comparison_rejects_non_array_evaluations(
    artifact: BehavioralBenchmarkArtifact,
) -> None:
    def mutate(payload: dict[str, object]) -> None:
        report = cast("dict[str, Any]", payload["report"])
        report["proposals"][0]["evaluations"] = {}

    candidate = _artifact_with_payload(artifact, mutate)
    with pytest.raises(ValueError, match="evaluations must be an array"):
        compare_behavioral_benchmark_artifacts(artifact, candidate)
