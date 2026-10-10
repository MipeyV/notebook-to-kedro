"""Exclusive pre-validation provider evidence, separate from scored artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.evaluation.behavioral import validate_behavioral_corpus
from notebook_to_kedro.evaluation.behavioral_artifacts import (
    BehavioralBenchmarkConfiguration,
    BehavioralBenchmarkProvenance,
    _boolean,
    _exact_keys,
    _integer,
    _json_sha256,
    _number,
    _object,
    _optional_string,
    _string,
    write_json_exclusive,
)
from notebook_to_kedro.evaluation.behavioral_benchmark import (
    BEHAVIORAL_PROPOSAL_EXECUTION_POLICY,
    _preflight,
    run_behavioral_code_benchmark,
)
from notebook_to_kedro.evaluation.behavioral_execution import BehavioralExecutionConfig
from notebook_to_kedro.evaluation.corpus_bound_code import (
    _decode_corpus,
    _snapshot,
    run_corpus_bound_code_benchmark,
)
from notebook_to_kedro.evaluation.node_body_benchmark import run_node_body_benchmark
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError, NodeCodeProviderError
from notebook_to_kedro.generation.code import NODE_CODE_VALIDATOR_VERSION, build_parameter_evidence
from notebook_to_kedro.generation.code.serialization import _unique_object

if TYPE_CHECKING:
    from collections.abc import Sequence

    from notebook_to_kedro.evaluation.behavioral import BehavioralCase
    from notebook_to_kedro.evaluation.behavioral_benchmark import BehavioralCodeBenchmarkReport
    from notebook_to_kedro.evaluation.corpus_bound_code import CorpusBoundCodeBenchmarkReport
    from notebook_to_kedro.evaluation.node_body_benchmark import NodeBodyBenchmarkReport
    from notebook_to_kedro.evaluation.node_code_corpus import NodeCodeCase
    from notebook_to_kedro.generation.code import (
        NodeBodyProvider,
        NodeCodeProvider,
        NodeCodeRequest,
    )

RESPONSE_CAPTURE_SCHEMA_VERSION = "1.0"
_FORMATS = ("full-code", "bound-full-code", "node-body")
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "artifact_kind",
        "proposal_format",
        "provider_name",
        "model_name",
        "prompt_version",
        "validator_version",
        "execution_policy",
        "provenance",
        "configuration",
        "corpus",
        "corpus_sha256",
    }
)
_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "artifact_kind",
        "manifest_sha256",
        "request_sha256",
        "status",
        "raw_response",
        "raw_response_sha256",
        "diagnostic_code",
        "diagnostic_message",
    }
)
_ATTEMPT_KEYS = frozenset({"manifest_sha256", "request_sha256"})


@dataclass(frozen=True, slots=True)
class ResponseCapture:
    """An integrity-checked snapshot, possibly missing provider outcomes, never scores."""

    manifest: dict[str, object]
    manifest_sha256: str
    responses: tuple[dict[str, object], ...]
    capture_sha256: str

    @property
    def configuration(self) -> BehavioralBenchmarkConfiguration:
        """Return the original provider and execution bounds after integrity validation."""
        _validate_capture(self)
        return _configuration(self.manifest["configuration"])

    @property
    def missing_node_code_case_ids(self) -> tuple[str, ...]:
        """Return all nodes without a published provider outcome."""
        _validate_capture(self)
        recorded = {row["request_sha256"] for row in self.responses}
        _, nodes = _decode_corpus(_object(self.manifest["corpus"], "corpus"))
        return tuple(
            node.case_id for node in nodes if _request_sha256(node.request) not in recorded
        )


class ResponseCaptureProvider:
    """Persist an exact response or expected provider failure before returning it."""

    def __init__(
        self,
        directory: Path,
        manifest: dict[str, object],
        provider: NodeCodeProvider | NodeBodyProvider,
    ) -> None:
        """Use a new manifest published by create_response_capture."""
        self.provider_name = _string(manifest["provider_name"], "provider_name")
        self.model_name = _string(manifest["model_name"], "model_name")
        self.prompt_version = _string(manifest["prompt_version"], "prompt_version")
        self._directory = directory
        self._provider = provider
        self._manifest_sha256 = _json_sha256(manifest)
        _, nodes = _decode_corpus(_object(manifest["corpus"], "corpus"))
        self._requests = {_request_sha256(node.request) for node in nodes}

    def complete(self, request: NodeCodeRequest) -> str:
        """Reserve once, call once, and fail closed if response publication fails."""
        digest = _request_sha256(request)
        if digest not in self._requests:
            raise BehavioralBenchmarkArtifactError(
                "capture request does not match the exact corpus"
            )
        write_json_exclusive(
            self._directory / "attempts" / f"{digest}.json",
            {"manifest_sha256": self._manifest_sha256, "request_sha256": digest},
        )
        record: dict[str, object] = {
            "schema_version": RESPONSE_CAPTURE_SCHEMA_VERSION,
            "artifact_kind": "provider-response",
            "manifest_sha256": self._manifest_sha256,
            "request_sha256": digest,
            "status": "response",
            "raw_response": None,
            "raw_response_sha256": None,
            "diagnostic_code": None,
            "diagnostic_message": None,
        }
        destination = self._directory / "responses" / f"{digest}.json"
        try:
            raw = self._provider.complete(request)
        except NodeCodeProviderError as error:
            record.update(
                status="provider_error",
                diagnostic_code=error.code,
                diagnostic_message=error.message,
            )
            write_json_exclusive(destination, record)
            raise
        if not isinstance(raw, str):
            raise BehavioralBenchmarkArtifactError("provider raw response must be a string")
        record.update(raw_response=raw, raw_response_sha256=_raw_sha256(raw))
        write_json_exclusive(destination, record)
        return raw


def create_response_capture(  # noqa: PLR0913
    directory: str | Path,
    behavioral_cases: Sequence[BehavioralCase],
    node_code_cases: Sequence[NodeCodeCase],
    provider: NodeCodeProvider | NodeBodyProvider,
    *,
    provenance: BehavioralBenchmarkProvenance,
    configuration: BehavioralBenchmarkConfiguration,
    prompt_version: str,
    proposal_format: str = "full-code",
    allow_untrusted_code_execution: bool = False,
    project_root: str | Path = ".",
) -> ResponseCaptureProvider:
    """Preflight and publish a fresh capture before any generation request."""
    if allow_untrusted_code_execution is not True:
        raise ValueError("response capture requires allow_untrusted_code_execution=True")
    behaviors, nodes = tuple(behavioral_cases), tuple(node_code_cases)
    _preflight(behaviors, nodes, Path(project_root).resolve())
    corpus = _snapshot(behaviors, nodes)
    manifest: dict[str, object] = {
        "schema_version": RESPONSE_CAPTURE_SCHEMA_VERSION,
        "artifact_kind": "behavioral-response-capture",
        "proposal_format": proposal_format,
        "provider_name": provider.provider_name,
        "model_name": provider.model_name,
        "prompt_version": prompt_version,
        "validator_version": NODE_CODE_VALIDATOR_VERSION,
        "execution_policy": BEHAVIORAL_PROPOSAL_EXECUTION_POLICY,
        "provenance": asdict(provenance),
        "configuration": asdict(configuration),
        "corpus": corpus,
        "corpus_sha256": _json_sha256(corpus),
    }
    _validate_manifest(manifest)
    if configuration.include_parameter_evidence:
        for node in nodes:
            build_parameter_evidence(node.request)
    destination = Path(directory)
    try:
        destination.mkdir(parents=True, exist_ok=False)
        (destination / "attempts").mkdir()
        (destination / "responses").mkdir()
    except OSError as error:
        raise BehavioralBenchmarkArtifactError(
            f"cannot create new capture {destination}: {error}"
        ) from error
    write_json_exclusive(destination / "manifest.json", manifest)
    return ResponseCaptureProvider(destination, manifest, provider)


def load_response_capture(directory: str | Path) -> ResponseCapture:
    """Inspect partial or complete evidence without parsing or executing model code."""
    root = Path(directory)
    try:
        manifest = _read_json(root / "manifest.json")
        _validate_manifest(manifest)
        manifest_digest = _json_sha256(manifest)
        _, nodes = _decode_corpus(_object(manifest["corpus"], "corpus"))
        expected = {_request_sha256(node.request) for node in nodes}
        attempts = set()
        for path in sorted((root / "attempts").glob("*.json")):
            record = _read_json(path)
            _exact_keys(record, _ATTEMPT_KEYS, "capture attempt")
            if path.stem not in expected or record != {
                "manifest_sha256": manifest_digest,
                "request_sha256": path.stem,
            }:
                raise ValueError("capture attempt identity does not match manifest")
            attempts.add(path.stem)
        responses = []
        for path in sorted((root / "responses").glob("*.json")):
            record = _read_json(path)
            if path.stem not in attempts or record.get("request_sha256") != path.stem:
                raise ValueError("capture response requires its exact reserved request")
            responses.append(record)
        rows = tuple(responses)
        capture = ResponseCapture(manifest, manifest_digest, rows, _capture_sha256(manifest, rows))
        _validate_capture(capture)
        return capture
    except (OSError, ValueError) as error:
        raise BehavioralBenchmarkArtifactError(
            f"cannot load response capture {root}: {error}"
        ) from error


def recover_response_capture(
    capture: ResponseCapture,
    behavioral_cases: Sequence[BehavioralCase],
    node_code_cases: Sequence[NodeCodeCase],
    *,
    allow_untrusted_code_execution: bool = False,
    project_root: str | Path = ".",
) -> BehavioralCodeBenchmarkReport | CorpusBoundCodeBenchmarkReport | NodeBodyBenchmarkReport:
    """Revalidate and evaluate a complete capture offline, never retry missing requests."""
    if allow_untrusted_code_execution is not True:
        raise ValueError("capture recovery requires allow_untrusted_code_execution=True")
    _validate_capture(capture)
    if _snapshot(behavioral_cases, node_code_cases) != capture.manifest["corpus"]:
        raise ValueError("capture recovery requires the exact complete corpus")
    if capture.missing_node_code_case_ids:
        raise ValueError(
            f"capture is incomplete; missing outcomes: {capture.missing_node_code_case_ids}"
        )
    provider = _CapturedProvider(capture)
    configuration = _configuration(capture.manifest["configuration"])
    # Keep the existing preflight, parser, assembler, validator and execution pipeline.
    if capture.manifest["proposal_format"] == "node-body":
        return run_node_body_benchmark(
            behavioral_cases,
            node_code_cases,
            provider,
            allow_untrusted_code_execution=allow_untrusted_code_execution,
            project_root=project_root,
            execution_config=configuration.execution,
            clock=lambda: 0.0,
        )
    runner = (
        run_corpus_bound_code_benchmark
        if capture.manifest["proposal_format"] == "bound-full-code"
        else run_behavioral_code_benchmark
    )
    return runner(
        behavioral_cases,
        node_code_cases,
        provider,
        allow_untrusted_code_execution=allow_untrusted_code_execution,
        project_root=project_root,
        execution_config=configuration.execution,
        prompt_version=provider.prompt_version,
        clock=lambda: 0.0,
    )


class _CapturedProvider:
    def __init__(self, capture: ResponseCapture) -> None:
        self.provider_name = _string(capture.manifest["provider_name"], "provider_name")
        self.model_name = _string(capture.manifest["model_name"], "model_name")
        self.prompt_version = _string(capture.manifest["prompt_version"], "prompt_version")
        self._records = {row["request_sha256"]: row for row in capture.responses}

    def complete(self, request: NodeCodeRequest) -> str:
        record = self._records[_request_sha256(request)]
        if record["status"] == "provider_error":
            raise NodeCodeProviderError(
                _string(record["diagnostic_code"], "diagnostic_code"),
                _string(record["diagnostic_message"], "diagnostic_message"),
            )
        return _string(record["raw_response"], "raw_response")


def _validate_capture(capture: ResponseCapture) -> None:
    _validate_manifest(capture.manifest)
    if capture.manifest_sha256 != _json_sha256(
        capture.manifest
    ) or capture.capture_sha256 != _capture_sha256(capture.manifest, capture.responses):
        raise ValueError("capture digest does not match stored evidence")
    _, nodes = _decode_corpus(_object(capture.manifest["corpus"], "corpus"))
    expected = {_request_sha256(node.request) for node in nodes}
    seen = set()
    for record in capture.responses:
        _exact_keys(record, _RECORD_KEYS, "capture response")
        digest = _string(record["request_sha256"], "request_sha256")
        if (
            record["schema_version"] != RESPONSE_CAPTURE_SCHEMA_VERSION
            or record["artifact_kind"] != "provider-response"
            or record["manifest_sha256"] != capture.manifest_sha256
            or digest not in expected
            or digest in seen
        ):
            raise ValueError("capture response identity does not match manifest")
        seen.add(digest)
        if record["status"] == "response":
            raw = _string(record["raw_response"], "raw_response")
            if (
                record["raw_response_sha256"] != _raw_sha256(raw)
                or record["diagnostic_code"] is not None
                or record["diagnostic_message"] is not None
            ):
                raise ValueError("capture raw response hash or diagnostic does not match")
        elif record["status"] == "provider_error":
            if (
                record["raw_response"] is not None
                or record["raw_response_sha256"] is not None
                or not _string(record["diagnostic_code"], "diagnostic_code").strip()
                or not _string(record["diagnostic_message"], "diagnostic_message").strip()
            ):
                raise ValueError("capture provider failure requires only an exact diagnostic")
        else:
            raise ValueError("unsupported capture response status")


def _validate_manifest(manifest: dict[str, object]) -> None:
    _exact_keys(manifest, _MANIFEST_KEYS, "capture manifest")
    if (
        manifest["schema_version"] != RESPONSE_CAPTURE_SCHEMA_VERSION
        or manifest["artifact_kind"] != "behavioral-response-capture"
        or manifest["proposal_format"] not in _FORMATS
        or manifest["validator_version"] != NODE_CODE_VALIDATOR_VERSION
        or manifest["execution_policy"] != BEHAVIORAL_PROPOSAL_EXECUTION_POLICY
    ):
        raise ValueError("unsupported capture schema, format or validation policy")
    for name in ("provider_name", "model_name", "prompt_version"):
        if not _string(manifest[name], name).strip():
            raise ValueError(f"capture {name} must not be empty")
    configuration = _configuration(manifest["configuration"])
    _provenance(manifest["provenance"])
    if manifest["proposal_format"] == "node-body" and not configuration.include_parameter_evidence:
        raise ValueError("body captures require parameter evidence")
    corpus = _object(manifest["corpus"], "corpus")
    if manifest["corpus_sha256"] != _json_sha256(corpus):
        raise ValueError("capture corpus hash does not match")
    behaviors, nodes = _decode_corpus(corpus)
    if not nodes or not behaviors or len({node.request.request_id for node in nodes}) != len(nodes):
        raise ValueError("capture requires nonempty corpora and unique request IDs")
    validate_behavioral_corpus(behaviors, nodes)


def _configuration(payload: object) -> BehavioralBenchmarkConfiguration:
    data = _object(payload, "capture configuration")
    _exact_keys(
        data,
        frozenset(
            {
                "ollama_base_url",
                "provider_timeout_seconds",
                "include_parameter_evidence",
                "execution",
            }
        ),
        "capture configuration",
    )
    execution = _object(data["execution"], "execution")
    _exact_keys(
        execution,
        frozenset(
            {"timeout_seconds", "max_request_bytes", "max_result_bytes", "max_capture_bytes"}
        ),
        "execution",
    )
    return BehavioralBenchmarkConfiguration(
        _string(data["ollama_base_url"], "ollama_base_url"),
        _number(data["provider_timeout_seconds"], "provider_timeout_seconds"),
        _boolean(data["include_parameter_evidence"], "include_parameter_evidence"),
        BehavioralExecutionConfig(
            _number(execution["timeout_seconds"], "timeout_seconds"),
            _integer(execution["max_request_bytes"], "max_request_bytes"),
            _integer(execution["max_result_bytes"], "max_result_bytes"),
            _integer(execution["max_capture_bytes"], "max_capture_bytes"),
        ),
    )


def _provenance(payload: object) -> BehavioralBenchmarkProvenance:
    data = _object(payload, "capture provenance")
    _exact_keys(
        data,
        frozenset(
            {
                "created_at_utc",
                "repository_revision",
                "python_version",
                "platform",
                "ollama_version",
                "model_digest",
            }
        ),
        "capture provenance",
    )
    return BehavioralBenchmarkProvenance(
        _string(data["created_at_utc"], "created_at_utc"),
        _optional_string(data["repository_revision"], "repository_revision"),
        _string(data["python_version"], "python_version"),
        _string(data["platform"], "platform"),
        _optional_string(data["ollama_version"], "ollama_version"),
        _optional_string(data["model_digest"], "model_digest"),
    )


def _read_json(path: Path) -> dict[str, object]:
    return _object(
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object),
        "capture JSON",
    )


def _request_sha256(request: NodeCodeRequest) -> str:
    return _json_sha256(json.loads(request.to_json()))


def _raw_sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _capture_sha256(manifest: dict[str, object], responses: tuple[dict[str, object], ...]) -> str:
    return _json_sha256(
        {
            "manifest": manifest,
            "responses": sorted(
                responses, key=lambda row: _string(row.get("request_sha256"), "request_sha256")
            ),
        }
    )


def response_capture_summary(capture: ResponseCapture) -> dict[str, object]:
    """Describe evidence completeness without interpreting raw code or assigning scores."""
    missing = capture.missing_node_code_case_ids
    _, nodes = _decode_corpus(_object(capture.manifest["corpus"], "corpus"))
    return {
        "artifact_kind": "behavioral-response-capture",
        "manifest_sha256": capture.manifest_sha256,
        "capture_sha256": capture.capture_sha256,
        "proposal_format": capture.manifest["proposal_format"],
        "expected_node_count": len(nodes),
        "recorded_outcome_count": len(capture.responses),
        "provider_error_count": sum(row["status"] == "provider_error" for row in capture.responses),
        "missing_node_code_case_ids": list(missing),
        "complete": not missing,
        "benchmark_completed": False,
    }
