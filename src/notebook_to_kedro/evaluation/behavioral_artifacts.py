"""Reproducible artifacts, offline replay and comparison for behavioral benchmarks."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from notebook_to_kedro.evaluation.behavioral_benchmark import (
    BEHAVIORAL_CODE_BENCHMARK_SCHEMA_VERSION,
    behavioral_code_benchmark_to_dict,
    run_behavioral_code_benchmark,
)
from notebook_to_kedro.evaluation.behavioral_execution import BehavioralExecutionConfig
from notebook_to_kedro.exceptions import (
    BehavioralBenchmarkArtifactError,
    NodeCodeProviderError,
)
from notebook_to_kedro.semantic.ollama import _normalize_local_base_url

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from notebook_to_kedro.evaluation.behavioral import BehavioralCase
    from notebook_to_kedro.evaluation.behavioral_benchmark import BehavioralCodeBenchmarkReport
    from notebook_to_kedro.evaluation.node_code_corpus import NodeCodeCase
    from notebook_to_kedro.generation.code import NodeCodeRequest

BEHAVIORAL_BENCHMARK_ARTIFACT_SCHEMA_VERSION = "1.0"
BEHAVIORAL_BENCHMARK_COMPARISON_SCHEMA_VERSION = "1.0"
_MAX_METADATA_RESPONSE_BYTES = 1_000_000
_SHA256_HEX_LENGTH = 64
_ARTIFACT_KEYS = frozenset(
    {
        "schema_version",
        "mode",
        "provenance",
        "configuration",
        "report_sha256",
        "source_artifact_sha256",
        "report",
    }
)
_PROVENANCE_KEYS = frozenset(
    {
        "created_at_utc",
        "repository_revision",
        "python_version",
        "platform",
        "ollama_version",
        "model_digest",
    }
)
_CONFIGURATION_KEYS = frozenset(
    {
        "ollama_base_url",
        "provider_timeout_seconds",
        "include_parameter_evidence",
        "execution",
    }
)
_EXECUTION_KEYS = frozenset(
    {"timeout_seconds", "max_request_bytes", "max_result_bytes", "max_capture_bytes"}
)
_REPORT_KEYS = frozenset(
    {
        "schema_version",
        "provider_name",
        "model_name",
        "prompt_version",
        "validator_version",
        "execution_policy",
        "scenario_count",
        "proposals",
        "summary",
    }
)
_PROPOSAL_STATUSES = frozenset({"accepted", "provider_error", "invalid_response", "invalid_code"})
_ArtifactMode: TypeAlias = Literal["live", "replay"]


@dataclass(frozen=True, slots=True)
class BehavioralBenchmarkProvenance:
    """Environment identity captured independently from model output."""

    created_at_utc: str
    repository_revision: str | None
    python_version: str
    platform: str
    ollama_version: str | None
    model_digest: str | None

    def __post_init__(self) -> None:
        try:
            parsed = datetime.fromisoformat(self.created_at_utc.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("created_at_utc must be an ISO-8601 timestamp") from error
        if parsed.tzinfo != UTC:
            raise ValueError("created_at_utc must use UTC")
        for label in ("python_version", "platform"):
            if not cast("str", getattr(self, label)).strip():
                raise ValueError(f"{label} must not be empty")
        for label in ("repository_revision", "ollama_version"):
            value = cast("str | None", getattr(self, label))
            if value is not None and not value.strip():
                raise ValueError(f"{label} must be null or non-empty")
        if self.model_digest is not None and not _is_sha256(self.model_digest):
            raise ValueError("model_digest must be null or a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class BehavioralBenchmarkConfiguration:
    """Provider and execution settings needed to interpret a benchmark run."""

    ollama_base_url: str
    provider_timeout_seconds: float
    include_parameter_evidence: bool
    execution: BehavioralExecutionConfig = field(default_factory=BehavioralExecutionConfig)

    def __post_init__(self) -> None:
        normalized = _normalize_local_base_url(self.ollama_base_url)
        object.__setattr__(self, "ollama_base_url", normalized)
        if not math.isfinite(self.provider_timeout_seconds) or self.provider_timeout_seconds <= 0:
            raise ValueError("provider_timeout_seconds must be a positive finite number")


@dataclass(frozen=True, slots=True)
class BehavioralBenchmarkArtifact:
    """One immutable benchmark report with reproducibility evidence."""

    schema_version: str
    mode: _ArtifactMode
    provenance: BehavioralBenchmarkProvenance
    configuration: BehavioralBenchmarkConfiguration
    report_sha256: str
    source_artifact_sha256: str | None
    report: dict[str, object]

    def __post_init__(self) -> None:
        if self.schema_version != BEHAVIORAL_BENCHMARK_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(f"unsupported artifact schema version: {self.schema_version!r}")
        if self.mode not in ("live", "replay"):
            raise ValueError(f"unsupported artifact mode: {self.mode!r}")
        _validate_report(self.report)
        if self.report_sha256 != _json_sha256(self.report):
            raise ValueError("report_sha256 does not match the canonical report")
        if self.source_artifact_sha256 is not None and not _is_sha256(self.source_artifact_sha256):
            raise ValueError("source_artifact_sha256 must be null or a lowercase SHA-256 digest")
        if self.mode == "live" and self.source_artifact_sha256 is not None:
            raise ValueError("live artifacts cannot reference a source artifact")
        if self.mode == "replay" and self.source_artifact_sha256 is None:
            raise ValueError("replay artifacts require a source artifact digest")


def collect_environment_provenance(
    *,
    project_root: str | Path = ".",
    ollama_base_url: str | None = None,
    model_name: str | None = None,
    timeout_seconds: float = 5.0,
    now: datetime | None = None,
) -> BehavioralBenchmarkProvenance:
    """Collect local runtime, repository and optional Ollama identities."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    ollama_version = None
    model_digest = None
    if ollama_base_url is not None:
        if model_name is None or not model_name.strip():
            raise ValueError("model_name is required with ollama_base_url")
        ollama_version, model_digest = _ollama_metadata(
            ollama_base_url, model_name, timeout_seconds
        )
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("provenance clock must be timezone-aware")
    created_at = instant.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return BehavioralBenchmarkProvenance(
        created_at_utc=created_at,
        repository_revision=_repository_revision(Path(project_root)),
        python_version=platform.python_version(),
        platform=sys.platform,
        ollama_version=ollama_version,
        model_digest=model_digest,
    )


def create_behavioral_benchmark_artifact(
    report: BehavioralCodeBenchmarkReport,
    provenance: BehavioralBenchmarkProvenance,
    configuration: BehavioralBenchmarkConfiguration,
    *,
    mode: _ArtifactMode = "live",
    source_artifact_sha256: str | None = None,
) -> BehavioralBenchmarkArtifact:
    """Wrap one in-memory report in a validated artifact."""
    payload = behavioral_code_benchmark_to_dict(report)
    return BehavioralBenchmarkArtifact(
        schema_version=BEHAVIORAL_BENCHMARK_ARTIFACT_SCHEMA_VERSION,
        mode=mode,
        provenance=provenance,
        configuration=configuration,
        report_sha256=_json_sha256(payload),
        source_artifact_sha256=source_artifact_sha256,
        report=payload,
    )


def behavioral_benchmark_artifact_to_dict(
    artifact: BehavioralBenchmarkArtifact,
) -> dict[str, object]:
    """Serialize an artifact as canonical JSON-compatible data."""
    return {
        "schema_version": artifact.schema_version,
        "mode": artifact.mode,
        "provenance": asdict(artifact.provenance),
        "configuration": {
            "ollama_base_url": artifact.configuration.ollama_base_url,
            "provider_timeout_seconds": artifact.configuration.provider_timeout_seconds,
            "include_parameter_evidence": artifact.configuration.include_parameter_evidence,
            "execution": asdict(artifact.configuration.execution),
        },
        "report_sha256": artifact.report_sha256,
        "source_artifact_sha256": artifact.source_artifact_sha256,
        "report": artifact.report,
    }


def behavioral_benchmark_artifact_to_json(
    artifact: BehavioralBenchmarkArtifact, *, indent: int | None = 2
) -> str:
    """Encode an artifact deterministically."""
    return _to_json(behavioral_benchmark_artifact_to_dict(artifact), indent=indent)


def behavioral_benchmark_artifact_from_dict(payload: object) -> BehavioralBenchmarkArtifact:
    """Strictly reconstruct and integrity-check an artifact."""
    data = _object(payload, "behavioral benchmark artifact")
    _exact_keys(data, _ARTIFACT_KEYS, "behavioral benchmark artifact")
    provenance_data = _object(data["provenance"], "artifact provenance")
    _exact_keys(provenance_data, _PROVENANCE_KEYS, "artifact provenance")
    configuration_data = _object(data["configuration"], "artifact configuration")
    _exact_keys(configuration_data, _CONFIGURATION_KEYS, "artifact configuration")
    execution_data = _object(configuration_data["execution"], "execution configuration")
    _exact_keys(execution_data, _EXECUTION_KEYS, "execution configuration")
    report = _object(data["report"], "behavioral benchmark report")
    return BehavioralBenchmarkArtifact(
        schema_version=_string(data["schema_version"], "schema_version"),
        mode=cast("_ArtifactMode", _string(data["mode"], "mode")),
        provenance=BehavioralBenchmarkProvenance(
            created_at_utc=_string(provenance_data["created_at_utc"], "created_at_utc"),
            repository_revision=_optional_string(
                provenance_data["repository_revision"], "repository_revision"
            ),
            python_version=_string(provenance_data["python_version"], "python_version"),
            platform=_string(provenance_data["platform"], "platform"),
            ollama_version=_optional_string(provenance_data["ollama_version"], "ollama_version"),
            model_digest=_optional_string(provenance_data["model_digest"], "model_digest"),
        ),
        configuration=BehavioralBenchmarkConfiguration(
            ollama_base_url=_string(configuration_data["ollama_base_url"], "ollama_base_url"),
            provider_timeout_seconds=_number(
                configuration_data["provider_timeout_seconds"], "provider_timeout_seconds"
            ),
            include_parameter_evidence=_boolean(
                configuration_data["include_parameter_evidence"],
                "include_parameter_evidence",
            ),
            execution=BehavioralExecutionConfig(
                timeout_seconds=_number(execution_data["timeout_seconds"], "timeout_seconds"),
                max_request_bytes=_integer(
                    execution_data["max_request_bytes"], "max_request_bytes"
                ),
                max_result_bytes=_integer(execution_data["max_result_bytes"], "max_result_bytes"),
                max_capture_bytes=_integer(
                    execution_data["max_capture_bytes"], "max_capture_bytes"
                ),
            ),
        ),
        report_sha256=_string(data["report_sha256"], "report_sha256"),
        source_artifact_sha256=_optional_string(
            data["source_artifact_sha256"], "source_artifact_sha256"
        ),
        report=report,
    )


def behavioral_benchmark_artifact_from_json(payload: str) -> BehavioralBenchmarkArtifact:
    """Decode a benchmark artifact from JSON text."""
    try:
        decoded: object = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid behavioral benchmark artifact JSON: {error.msg}") from error
    return behavioral_benchmark_artifact_from_dict(decoded)


def load_behavioral_benchmark_artifact(path: str | Path) -> BehavioralBenchmarkArtifact:
    """Read and validate one benchmark artifact."""
    artifact_path = Path(path)
    try:
        payload = artifact_path.read_text(encoding="utf-8")
    except OSError as error:
        raise BehavioralBenchmarkArtifactError(
            f"cannot read behavioral benchmark artifact {artifact_path}: {error}"
        ) from error
    try:
        return behavioral_benchmark_artifact_from_json(payload)
    except ValueError as error:
        raise BehavioralBenchmarkArtifactError(str(error)) from error


def write_json_exclusive(path: str | Path, payload: Mapping[str, object]) -> None:
    """Publish canonical JSON atomically and refuse to replace an existing path."""
    destination = Path(path)
    temporary_path: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise BehavioralBenchmarkArtifactError(
            f"cannot write behavioral benchmark output {destination}: {error}"
        ) from error
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary_path = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(_to_json(dict(payload)))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, destination)
    except FileExistsError as error:
        raise BehavioralBenchmarkArtifactError(
            f"benchmark output already exists: {destination}"
        ) from error
    except OSError as error:
        raise BehavioralBenchmarkArtifactError(
            f"cannot write behavioral benchmark output {destination}: {error}"
        ) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_behavioral_benchmark_artifact(
    path: str | Path, artifact: BehavioralBenchmarkArtifact
) -> None:
    """Atomically publish one validated artifact without overwriting evidence."""
    write_json_exclusive(path, behavioral_benchmark_artifact_to_dict(artifact))


def replay_behavioral_benchmark(  # noqa: PLR0913
    artifact: BehavioralBenchmarkArtifact,
    behavioral_cases: Sequence[BehavioralCase],
    node_code_cases: Sequence[NodeCodeCase],
    *,
    allow_untrusted_code_execution: bool = False,
    project_root: str | Path = ".",
    execution_config: BehavioralExecutionConfig | None = None,
) -> BehavioralCodeBenchmarkReport:
    """Re-validate and re-execute recorded responses without contacting a provider."""
    provider = _RecordedNodeCodeProvider(artifact.report)
    return run_behavioral_code_benchmark(
        behavioral_cases,
        node_code_cases,
        provider,
        allow_untrusted_code_execution=allow_untrusted_code_execution,
        project_root=project_root,
        prompt_version=_optional_string(artifact.report["prompt_version"], "prompt_version"),
        execution_config=execution_config or artifact.configuration.execution,
        clock=lambda: 0.0,
    )


def compare_behavioral_benchmark_artifacts(
    baseline: BehavioralBenchmarkArtifact,
    candidate: BehavioralBenchmarkArtifact,
) -> dict[str, object]:
    """Compare static acceptance, scenario outcomes and latency across two artifacts."""
    baseline_proposals = _proposals_by_id(baseline.report)
    candidate_proposals = _proposals_by_id(candidate.report)
    if baseline_proposals.keys() != candidate_proposals.keys():
        raise BehavioralBenchmarkArtifactError(
            "benchmark artifacts must contain the same node code case IDs"
        )
    proposal_changes = [
        {
            "node_code_case_id": case_id,
            "baseline_status": _proposal_status(baseline_proposals[case_id]),
            "candidate_status": _proposal_status(candidate_proposals[case_id]),
            "change": _classify_change(
                baseline_status=_proposal_status(baseline_proposals[case_id]),
                candidate_status=_proposal_status(candidate_proposals[case_id]),
                success_status="accepted",
            ),
        }
        for case_id in sorted(baseline_proposals)
    ]
    baseline_scenarios = _scenario_statuses(baseline.report)
    candidate_scenarios = _scenario_statuses(candidate.report)
    all_scenario_ids = sorted(baseline_scenarios.keys() | candidate_scenarios.keys())
    scenario_changes = [
        {
            "case_id": case_id,
            "baseline_status": baseline_scenarios.get(case_id, "not_evaluated"),
            "candidate_status": candidate_scenarios.get(case_id, "not_evaluated"),
            "change": _classify_change(
                baseline_status=baseline_scenarios.get(case_id, "not_evaluated"),
                candidate_status=candidate_scenarios.get(case_id, "not_evaluated"),
                success_status="matched",
            ),
        }
        for case_id in all_scenario_ids
    ]
    baseline_summary = _object(baseline.report["summary"], "benchmark summary")
    candidate_summary = _object(candidate.report["summary"], "benchmark summary")
    metrics: dict[str, dict[str, object]] = {}
    for name in ("accepted_rate", "end_to_end_match_rate", "execution_duration_seconds"):
        baseline_value = _number(baseline_summary.get(name), name)
        candidate_value = _number(candidate_summary.get(name), name)
        metrics[name] = {
            "baseline": baseline_value,
            "candidate": candidate_value,
            "delta": candidate_value - baseline_value,
        }
    comparable_provider_latency = baseline.mode == candidate.mode == "live"
    baseline_duration = _number(
        baseline_summary.get("provider_duration_seconds"), "provider_duration_seconds"
    )
    candidate_duration = _number(
        candidate_summary.get("provider_duration_seconds"), "provider_duration_seconds"
    )
    metrics["provider_duration_seconds"] = {
        "baseline": baseline_duration,
        "candidate": candidate_duration,
        "delta": candidate_duration - baseline_duration if comparable_provider_latency else None,
        "comparable": comparable_provider_latency,
    }
    return {
        "schema_version": BEHAVIORAL_BENCHMARK_COMPARISON_SCHEMA_VERSION,
        "baseline_artifact_sha256": behavioral_benchmark_artifact_sha256(baseline),
        "candidate_artifact_sha256": behavioral_benchmark_artifact_sha256(candidate),
        "metrics": metrics,
        "proposal_changes": proposal_changes,
        "scenario_changes": scenario_changes,
        "regressed_proposal_count": sum(
            change["change"] == "regressed" for change in proposal_changes
        ),
        "regressed_scenario_count": sum(
            change["change"] == "regressed" for change in scenario_changes
        ),
    }


def behavioral_benchmark_artifact_sha256(artifact: BehavioralBenchmarkArtifact) -> str:
    """Return the stable identity of a complete artifact."""
    return _json_sha256(behavioral_benchmark_artifact_to_dict(artifact))


class _RecordedNodeCodeProvider:
    """Provider adapter that only serves outcomes embedded in one artifact."""

    def __init__(self, report: dict[str, object]) -> None:
        self.provider_name = _string(report["provider_name"], "provider_name")
        self.model_name = _string(report["model_name"], "model_name")
        proposals = _proposals_by_request_id(report)
        self._proposals = proposals

    def complete(self, request: NodeCodeRequest) -> str:
        try:
            proposal = self._proposals[request.request_id]
        except KeyError as error:
            raise NodeCodeProviderError(
                "replay_missing_response",
                f"artifact has no response for request {request.request_id!r}",
            ) from error
        status = _proposal_status(proposal)
        if status == "provider_error":
            raise NodeCodeProviderError(
                _optional_string(proposal.get("diagnostic_code"), "diagnostic_code")
                or "recorded_provider_error",
                _optional_string(proposal.get("diagnostic_message"), "diagnostic_message")
                or "recorded provider error",
            )
        raw_response = proposal.get("raw_response")
        if not isinstance(raw_response, str):
            raise NodeCodeProviderError(
                "replay_missing_response",
                f"artifact has no raw response for request {request.request_id!r}",
            )
        return raw_response


def _ollama_metadata(base_url: str, model_name: str, timeout_seconds: float) -> tuple[str, str]:
    base = _normalize_local_base_url(base_url)
    version_payload = _http_json(f"{base}/api/version", timeout_seconds)
    tags_payload = _http_json(f"{base}/api/tags", timeout_seconds)
    version = _string(version_payload.get("version"), "Ollama version")
    models = tags_payload.get("models")
    if not isinstance(models, list):
        raise BehavioralBenchmarkArtifactError("Ollama tags response must contain a models array")
    for item in models:
        model = _object(item, "Ollama model")
        if model.get("name") == model_name or model.get("model") == model_name:
            digest = _string(model.get("digest"), "model digest")
            if not _is_sha256(digest):
                raise BehavioralBenchmarkArtifactError(
                    "Ollama model digest must be a lowercase SHA-256 digest"
                )
            return version, digest
    raise BehavioralBenchmarkArtifactError(
        f"Ollama model metadata was not found for {model_name!r}"
    )


def _http_json(url: str, timeout_seconds: float) -> dict[str, object]:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(_MAX_METADATA_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        raise BehavioralBenchmarkArtifactError(
            f"cannot collect local Ollama provenance: {error}"
        ) from error
    if len(body) > _MAX_METADATA_RESPONSE_BYTES:
        raise BehavioralBenchmarkArtifactError("Ollama metadata response is too large")
    try:
        decoded: object = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BehavioralBenchmarkArtifactError(
            "Ollama metadata response is not valid UTF-8 JSON"
        ) from error
    return _object(decoded, "Ollama metadata response")


def _repository_revision(project_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ("git", "-C", str(project_root.resolve()), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = completed.stdout.strip()
    return revision or None


def _validate_report(report: dict[str, object]) -> None:
    _exact_keys(report, _REPORT_KEYS, "behavioral benchmark report")
    if report.get("schema_version") != BEHAVIORAL_CODE_BENCHMARK_SCHEMA_VERSION:
        raise ValueError(f"unsupported benchmark report schema: {report.get('schema_version')!r}")
    for name in ("provider_name", "model_name", "validator_version", "execution_policy"):
        if not _string(report.get(name), name).strip():
            raise ValueError(f"{name} must not be empty")
    _optional_string(report.get("prompt_version"), "prompt_version")
    _integer(report.get("scenario_count"), "scenario_count")
    proposals = report.get("proposals")
    if not isinstance(proposals, list):
        raise ValueError("proposals must be an array")
    _object(report.get("summary"), "benchmark summary")
    _proposals_by_id(report)
    _proposals_by_request_id(report)


def _proposals_by_id(report: dict[str, object]) -> dict[str, dict[str, object]]:
    proposals = cast("list[object]", report["proposals"])
    by_id: dict[str, dict[str, object]] = {}
    for payload in proposals:
        proposal = _object(payload, "benchmark proposal")
        case_id = _string(proposal.get("node_code_case_id"), "node_code_case_id")
        _proposal_status(proposal)
        if case_id in by_id:
            raise ValueError("benchmark proposal case IDs must be unique")
        by_id[case_id] = proposal
    return by_id


def _proposals_by_request_id(report: dict[str, object]) -> dict[str, dict[str, object]]:
    by_request: dict[str, dict[str, object]] = {}
    for proposal in _proposals_by_id(report).values():
        request = _object(proposal.get("request"), "node code request")
        request_id = _string(request.get("request_id"), "request_id")
        if request_id in by_request:
            raise ValueError("benchmark proposal request IDs must be unique")
        by_request[request_id] = proposal
    return by_request


def _scenario_statuses(report: dict[str, object]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for proposal in _proposals_by_id(report).values():
        evaluations = proposal.get("evaluations")
        if not isinstance(evaluations, list):
            raise ValueError("proposal evaluations must be an array")
        for payload in evaluations:
            evaluation = _object(payload, "proposal evaluation")
            case_id = _string(evaluation.get("case_id"), "case_id")
            comparison = _object(evaluation.get("comparison"), "behavioral comparison")
            status = _string(comparison.get("status"), "comparison status")
            if case_id in statuses:
                raise ValueError("benchmark evaluation case IDs must be unique")
            statuses[case_id] = status
    return statuses


def _proposal_status(proposal: dict[str, object]) -> str:
    status = _string(proposal.get("status"), "proposal status")
    if status not in _PROPOSAL_STATUSES:
        raise ValueError(f"unsupported proposal status: {status!r}")
    return status


def _classify_change(*, baseline_status: str, candidate_status: str, success_status: str) -> str:
    if baseline_status == candidate_status:
        return "unchanged"
    if candidate_status == success_status:
        return "improved"
    if baseline_status == success_status:
        return "regressed"
    return "changed"


def _to_json(payload: Mapping[str, object], *, indent: int | None = 2) -> str:
    return (
        json.dumps(
            payload,
            indent=indent,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )


def _json_sha256(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == _SHA256_HEX_LENGTH and all(
        character in "0123456789abcdef" for character in value
    )


def _object(payload: object, label: str) -> dict[str, object]:
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise ValueError(f"{label} must be an object with string keys")
    return cast("dict[str, object]", payload)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _number(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    return float(value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _exact_keys(data: dict[str, object], expected: frozenset[str], label: str) -> None:
    actual = frozenset(data)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(f"invalid {label} fields; missing={missing}, unexpected={unexpected}")
