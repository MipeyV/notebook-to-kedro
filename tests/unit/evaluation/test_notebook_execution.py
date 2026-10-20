"""Draft whole-pipeline gates, transport failures and trusted worker observations."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from notebook_to_kedro import generate_kedro_project, plan_notebook_path
from notebook_to_kedro.evaluation import (
    BehavioralExecutionConfig,
    ComparisonSpec,
    ExpectedBehaviorOutput,
    NotebookBodyRecord,
    NotebookObservation,
    NotebookPipelineRun,
    ScalarBehaviorValue,
    TableBehaviorValue,
    compare_notebook_pipeline_run,
    create_notebook_body_capture,
    create_notebook_source_binding,
    record_notebook_body_response,
    reserve_notebook_body_request,
    run_notebook_pipeline_capture,
)
from notebook_to_kedro.evaluation import notebook_artifacts as artifacts
from notebook_to_kedro.evaluation import notebook_execution as execution_module
from notebook_to_kedro.evaluation import notebook_ledger as ledger_module
from notebook_to_kedro.evaluation import notebook_worker as worker
from notebook_to_kedro.evaluation.behavioral_artifacts import _json_sha256, write_json_exclusive
from notebook_to_kedro.evaluation.behavioral_execution import _result_from_worker
from notebook_to_kedro.evaluation.behavioral_worker import _base_result
from notebook_to_kedro.evaluation.notebook_capture import _raw_sha256
from notebook_to_kedro.evaluation.notebook_sources import _read_file
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError
from notebook_to_kedro.generation.code import NodeBodyResponse

if TYPE_CHECKING:
    from notebook_to_kedro.evaluation.behavioral import BehaviorValue
    from notebook_to_kedro.evaluation.behavioral_execution import BehavioralExecutionResult
    from notebook_to_kedro.evaluation.notebook_capture import NotebookBodyCapture
    from notebook_to_kedro.evaluation.notebook_sources import (
        NotebookSourceBinding,
        NotebookSourceFile,
    )

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = Path("tests/fixtures/evaluation/pilots/customer_churn_v1/contract.json")
NOTEBOOK = Path("tests/fixtures/notebooks/pilots/customer_churn_v1/customer_churn.ipynb")
TARGETS = (NotebookObservation("accuracy"),)
EXPECTED = (ExpectedBehaviorOutput("accuracy", ScalarBehaviorValue(1.0), ComparisonSpec("exact")),)


@dataclass
class _Prepared:
    binding: NotebookSourceBinding
    directory: Path
    payload: dict[str, Any]
    run: NotebookPipelineRun


def _successful(binding: NotebookSourceBinding, capture_digest: str) -> dict[str, object]:
    result = _base_result(binding.case_id, capture_digest)
    result.update(
        status="success",
        outputs=[
            {"output_name": "accuracy", "value": {"kind": "scalar", "value": 1.0}},
        ],
    )
    return result


@pytest.fixture(scope="module")
def prepared(tmp_path_factory: pytest.TempPathFactory) -> _Prepared:
    binding = create_notebook_source_binding(
        plan_notebook_path(ROOT / NOTEBOOK, project_root=ROOT),
        project_root=ROOT,
        contract_path=CONTRACT,
        expected_catalog_path=CONTRACT.with_name("expected_catalog.yml"),
    )
    directory = create_notebook_body_capture(
        tmp_path_factory.mktemp("worker-evidence") / "capture",
        binding,
        project_root=ROOT,
        provider_name="offline",
        model_name="trusted-source-echo",
        prompt_version="fixture-1",
    )
    for request in binding.requests:
        source = request.raw_source
        if request.node_name == "join_customer_features":
            source = source.replace(
                '{"net_revenue": 0.0, "completed_orders": 0}',
                "join_customer_features_fillna_values",
            )
        raw = NodeBodyResponse("1.0", request.request_id, request.task_id, source).to_json()
        reserve_notebook_body_request(directory, binding, request.request_id, project_root=ROOT)
        record_notebook_body_response(
            directory, binding, NotebookBodyRecord(request.request_id, raw), project_root=ROOT
        )
    payload: dict[str, Any] = {}

    def capture_payload(
        _directory: Path,
        data: dict[str, object],
        capture: NotebookBodyCapture,
        _config: BehavioralExecutionConfig,
    ) -> tuple[str, BehavioralExecutionResult]:
        payload.update(data)
        digest = hashlib.sha256(
            json.dumps(data, ensure_ascii=True, allow_nan=False).encode()
        ).hexdigest()
        return digest, _result_from_worker(_successful(binding, capture.content_sha256), 0.0)

    with pytest.MonkeyPatch.context() as context:
        context.setattr(execution_module, "_execute", capture_payload)
        run = run_notebook_pipeline_capture(
            directory, binding, TARGETS, project_root=ROOT, allow_untrusted_code_execution=True
        )
    return _Prepared(binding, directory, payload, run)


def _artifact_file(
    tmp_path: Path, run: NotebookPipelineRun
) -> tuple[Path, artifacts.NotebookPipelineArtifact]:
    artifact = artifacts.create_notebook_pipeline_artifact(run, EXPECTED)
    path = artifacts.write_notebook_pipeline_artifact(tmp_path / "report.json", artifact)
    return path, artifact


def _load_artifact(
    path: Path, prepared: _Prepared, **kwargs: Any
) -> artifacts.NotebookPipelineArtifact:
    return artifacts.load_notebook_pipeline_artifact(
        path, prepared.binding, prepared.directory, project_root=ROOT, **kwargs
    )


def _resign(payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_sha256"] = _json_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    return payload


def test_artifact_round_trip_inspects_without_execution(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, artifact = _artifact_file(tmp_path, prepared.run)
    monkeypatch.setattr(
        artifacts,
        "run_notebook_pipeline_capture",
        lambda *_a, **_k: pytest.fail("must not execute"),
    )
    assert _load_artifact(path, prepared) == artifact
    payload = artifacts.notebook_pipeline_artifact_to_dict(artifact)
    assert payload["capture"]["binding"]["review_json"] == prepared.binding.review_json  # type: ignore[index]
    assert artifact.comparison.status == "matched"
    with pytest.raises(BehavioralBenchmarkArtifactError, match="exists"):
        artifacts.write_notebook_pipeline_artifact(path, artifact)
    assert _load_artifact(path, prepared) == artifact


@pytest.mark.parametrize(
    "mode",
    [
        "partial",
        "unfinished",
        "provider_error",
        "invalid_json",
        "invalid_code",
        "timeout",
        "exception",
        "mismatch",
    ],
)
def test_artifacts_retain_failed_and_partial_outcomes(
    tmp_path: Path, prepared: _Prepared, mode: str
) -> None:
    directory = tmp_path / "capture"
    if mode in ("partial", "unfinished", "provider_error", "invalid_json", "invalid_code"):
        artifacts_capture = create_notebook_body_capture(
            directory,
            prepared.binding,
            project_root=ROOT,
            provider_name="offline",
            model_name="fixture",
            prompt_version="fixture-1",
        )
        if mode == "unfinished":
            reserve_notebook_body_request(
                artifacts_capture,
                prepared.binding,
                prepared.binding.requests[0].request_id,
                project_root=ROOT,
            )
        elif mode != "partial":
            request = prepared.binding.requests[0]
            reserve_notebook_body_request(
                artifacts_capture, prepared.binding, request.request_id, project_root=ROOT
            )
            record = (
                NotebookBodyRecord(request.request_id, provider_error=("failure", "offline"))
                if mode == "provider_error"
                else NotebookBodyRecord(
                    request.request_id,
                    "{"
                    if mode == "invalid_json"
                    else NodeBodyResponse(
                        "1.0", request.request_id, request.task_id, "wrong = 1"
                    ).to_json(),
                )
            )
            record_notebook_body_response(
                artifacts_capture, prepared.binding, record, project_root=ROOT
            )
        run = _run(prepared, directory)
    else:
        directory = prepared.directory
        assert prepared.run.execution is not None
        result = _successful(prepared.binding, prepared.run.capture.content_sha256)
        if mode == "mismatch":
            result["outputs"] = [
                {"output_name": "accuracy", "value": {"kind": "scalar", "value": 0.0}}
            ]
        else:
            result.update(status=mode, outputs=[])
            if mode == "exception":
                result["exception"] = {"type_name": "ValueError", "message": "fixture"}
            else:
                result["diagnostic_message"] = "fixture timeout"
        run = replace(prepared.run, execution=_result_from_worker(result, 0.1))
    path, artifact = _artifact_file(tmp_path, run)
    restored = artifacts.load_notebook_pipeline_artifact(
        path, prepared.binding, directory, project_root=ROOT
    )
    assert restored == artifact
    assert restored.comparison.status == ("mismatch" if mode == "mismatch" else "not_evaluated")
    assert len(restored.run.static.batch.proposals) == len(prepared.binding.requests)
    assert len(restored.comparison.outputs) == 1
    if mode == "unfinished":
        assert restored.run.capture.unfinished_request_ids == (
            prepared.binding.requests[0].request_id,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "old"),
        ("content_sha256", "bad"),
        ("source_artifact_sha256", "bad"),
        ("module_sha256", "0" * 64),
        ("request_sha256", "bad"),
        ("observations", {}),
        ("observations", [{"dataset": "accuracy", "kind": "wrong"}]),
        ("observations", [{"dataset": "accuracy", "kind": "value", "extra": True}]),
        ("observations", []),
        ("runtime_before", {}),
        ("expectations", []),
    ],
)
def test_artifact_rejects_malformed_fields(
    tmp_path: Path, prepared: _Prepared, field: str, value: Any
) -> None:
    payload = artifacts.notebook_pipeline_artifact_to_dict(
        artifacts.create_notebook_pipeline_artifact(prepared.run, EXPECTED)
    )
    payload[field] = value
    if field != "content_sha256":
        _resign(payload)
    path = tmp_path / "bad.json"
    write_json_exclusive(path, payload)
    with pytest.raises(
        ValueError, match=r"unsupported|SHA256|mismatch|array|fields|outputs|inventory|string"
    ):
        _load_artifact(path, prepared)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("comparison", "status", "mismatch"),
        ("static", "module_source", "wrong"),
        ("capture", "model_name", "other"),
        ("capture", "attempted_request_ids", []),
        ("configuration", "timeout_seconds", True),
        ("configuration", "max_request_bytes", True),
        ("configuration", "max_result_bytes", 0),
        ("configuration", "extra", True),
        ("execution", "duration_seconds", -1),
        ("execution", "case_id", "other"),
        ("execution", "stdout", "x" * 16_385),
        ("execution", "extra", True),
        ("runtime_before", "packages", [["name"]]),
        ("runtime_before", "packages", [["wrong", "1"]]),
        ("runtime_before", "package_sha256", "bad"),
        ("runtime_before", "lock_sha256", "bad"),
        ("runtime_before", "python_version", ""),
    ],
)
def test_artifact_recomputes_evidence_even_after_rehash(
    tmp_path: Path, prepared: _Prepared, section: str, field: str, value: Any
) -> None:
    payload: dict[str, Any] = artifacts.notebook_pipeline_artifact_to_dict(
        artifacts.create_notebook_pipeline_artifact(prepared.run, EXPECTED)
    )
    payload[section][field] = value
    write_json_exclusive(tmp_path / "bad.json", _resign(payload))
    with pytest.raises(
        ValueError,
        match=r"mismatch|number|integer|positive|fields|non-negative|capture|version|SHA256|non-empty",
    ):
        _load_artifact(tmp_path / "bad.json", prepared)


@pytest.mark.parametrize("payload", ['{"x":1,"x":2}', '{"x":NaN}', "[]", "{"])
def test_artifact_rejects_invalid_json(tmp_path: Path, prepared: _Prepared, payload: str) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match=r"duplicate|constant|finite|object|Expecting"):
        _load_artifact(path, prepared)


def test_artifact_file_bounds_and_integrity(tmp_path: Path, prepared: _Prepared) -> None:
    path, artifact = _artifact_file(tmp_path, prepared.run)
    assert _load_artifact(path, prepared, max_file_bytes=path.stat().st_size) == artifact
    for limit in (0, True, 1):
        with pytest.raises(ValueError, match="max_file_bytes"):
            _load_artifact(path, prepared, max_file_bytes=limit)
        with pytest.raises(ValueError, match="max_file_bytes"):
            artifacts.write_notebook_pipeline_artifact(
                tmp_path / f"limit{limit}.json", artifact, max_file_bytes=limit
            )
    with pytest.raises(ValueError, match="regular file"):
        _load_artifact(tmp_path, prepared)
    payload = json.loads(path.read_text())
    payload["capture"]["model_name"] = "changed"
    write_json_exclusive(tmp_path / "corrupt.json", payload)
    with pytest.raises(ValueError, match="integrity"):
        _load_artifact(tmp_path / "corrupt.json", prepared)
    payload.pop("runtime_after")
    write_json_exclusive(tmp_path / "missing.json", payload)
    with pytest.raises(ValueError, match="fields"):
        _load_artifact(tmp_path / "missing.json", prepared)


@pytest.mark.parametrize(
    "mode",
    ["version", "binding", "runtime", "observations", "module", "request", "execution", "blocked"],
)
def test_artifact_factory_refuses_inconsistent_runs(prepared: _Prepared, mode: str) -> None:
    run = prepared.run
    if mode == "version":
        run = replace(run, schema_version="old")
    elif mode == "binding":
        run = replace(
            run, static=replace(run.static, binding=replace(prepared.binding, case_id="other"))
        )
    elif mode == "runtime":
        run = replace(run, runtime_after=None)
    elif mode == "observations":
        run = replace(run, observations=(NotebookObservation("missing"),))
    elif mode == "module":
        run = replace(run, module_sha256=None)
    elif mode == "request":
        run = replace(run, request_sha256=None)
    elif mode == "execution":
        run = replace(run, execution=None)
    else:
        run = replace(
            run, static=replace(run.static, batch=replace(run.static.batch, module_source=None))
        )
    with pytest.raises(
        ValueError, match=r"version|binding|runtime|outputs|digest|string|outcome|blocked"
    ):
        artifacts.create_notebook_pipeline_artifact(run, EXPECTED)


def test_artifact_serializer_rejects_forged_comparison(prepared: _Prepared) -> None:
    artifact = artifacts.create_notebook_pipeline_artifact(prepared.run, EXPECTED)
    with pytest.raises(ValueError, match="comparison mismatch"):
        artifacts.notebook_pipeline_artifact_to_dict(
            replace(artifact, comparison=replace(artifact.comparison, status="mismatch"))
        )


@pytest.mark.parametrize("consent", [False, None, 1])
def test_artifact_replay_requires_consent_before_io(prepared: _Prepared, consent: Any) -> None:
    with pytest.raises(ValueError, match="allow_untrusted_code_execution"):
        artifacts.replay_notebook_pipeline_artifact(
            "missing",
            prepared.binding,
            "missing",
            project_root=ROOT,
            allow_untrusted_code_execution=consent,
        )


def test_artifact_replay_reexecutes_and_links_source(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, source = _artifact_file(tmp_path, prepared.run)
    calls = []

    def run_again(*args: Any, **kwargs: Any) -> NotebookPipelineRun:
        calls.append((args, kwargs))
        assert prepared.run.execution is not None
        return replace(
            prepared.run, execution=replace(prepared.run.execution, duration_seconds=2.0)
        )

    monkeypatch.setattr(artifacts, "run_notebook_pipeline_capture", run_again)
    replay = artifacts.replay_notebook_pipeline_artifact(
        path,
        prepared.binding,
        prepared.directory,
        project_root=ROOT,
        allow_untrusted_code_execution=True,
    )
    assert len(calls) == 1
    assert calls[0][1]["config"] == source.run.configuration
    assert calls[0][1]["allow_untrusted_code_execution"] is True
    assert calls[0][1]["expected_capture_sha256"] == prepared.run.capture.content_sha256
    assert (
        replay.source_artifact_sha256
        == artifacts.notebook_pipeline_artifact_to_dict(source)["content_sha256"]
    )
    assert replay.run.execution is not None
    assert replay.run.execution.duration_seconds == 2.0
    assert replay.comparison == source.comparison


@pytest.mark.parametrize("mode", ["current", "after", "unknown", "unknown_packages", "during"])
def test_artifact_replay_refuses_runtime_drift(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    before = prepared.run.runtime_before
    assert before is not None
    changed = replace(before, python_version="different")
    run = prepared.run
    if mode == "after":
        run = replace(run, runtime_after=changed)
    if mode == "unknown":
        run = replace(run, runtime_before=replace(before, lock_sha256=None))
    if mode == "unknown_packages":
        run = replace(
            run,
            runtime_before=replace(
                before, packages=tuple((name, None) for name, _ in before.packages)
            ),
        )
    path, _artifact = _artifact_file(tmp_path, run)
    calls = []

    def execute(*_a: Any, **_k: Any) -> NotebookPipelineRun:
        calls.append(True)
        return replace(prepared.run, runtime_after=changed)

    monkeypatch.setattr(artifacts, "run_notebook_pipeline_capture", execute)
    if mode == "current":
        monkeypatch.setattr(artifacts, "collect_notebook_runtime_identity", lambda _r: changed)
    assert _load_artifact(path, prepared).run == run
    with pytest.raises(ValueError, match="runtime compatibility"):
        artifacts.replay_notebook_pipeline_artifact(
            path,
            prepared.binding,
            prepared.directory,
            project_root=ROOT,
            allow_untrusted_code_execution=True,
        )
    assert bool(calls) is (mode == "during")


def test_worker_frozen_capture_check_precedes_execution(prepared: _Prepared) -> None:
    with pytest.raises(ValueError, match="frozen replay identity"):
        _run(prepared, prepared.directory, expected_capture_sha256="0" * 64)


def test_artifact_normalizes_integer_duration(tmp_path: Path, prepared: _Prepared) -> None:
    assert prepared.run.execution is not None
    run = replace(prepared.run, execution=replace(prepared.run.execution, duration_seconds=0))
    path, artifact = _artifact_file(tmp_path, run)
    assert _load_artifact(path, prepared) == artifact
    assert isinstance(json.loads(path.read_text())["execution"]["duration_seconds"], float)


def test_artifact_refuses_boolean_timeout(prepared: _Prepared) -> None:
    run = replace(
        prepared.run, configuration=replace(prepared.run.configuration, timeout_seconds=True)
    )
    with pytest.raises(ValueError, match="timeout_seconds must be a number"):
        artifacts.create_notebook_pipeline_artifact(run, EXPECTED)


def test_artifact_normalizes_numeric_comparison(tmp_path: Path, prepared: _Prepared) -> None:
    expectations = (
        ExpectedBehaviorOutput(
            "accuracy",
            ScalarBehaviorValue(1.0),
            ComparisonSpec("numeric", absolute_tolerance=0, relative_tolerance=0, equal_nan=False),
        ),
    )
    artifact = artifacts.create_notebook_pipeline_artifact(prepared.run, expectations)
    path = artifacts.write_notebook_pipeline_artifact(tmp_path / "numeric.json", artifact)
    assert _load_artifact(path, prepared) == artifact
    assert isinstance(artifact.expectations[0].comparison.absolute_tolerance, float)


def test_artifact_replay_refuses_changed_request_identity(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _artifact = _artifact_file(tmp_path, prepared.run)
    monkeypatch.setattr(
        artifacts,
        "run_notebook_pipeline_capture",
        lambda *_a, **_k: replace(prepared.run, request_sha256="0" * 64),
    )
    with pytest.raises(ValueError, match="request identity mismatch"):
        artifacts.replay_notebook_pipeline_artifact(
            path,
            prepared.binding,
            prepared.directory,
            project_root=ROOT,
            allow_untrusted_code_execution=True,
        )


def test_artifact_load_refuses_changed_capture(tmp_path: Path, prepared: _Prepared) -> None:
    path, _artifact = _artifact_file(tmp_path, prepared.run)
    directory = create_notebook_body_capture(
        tmp_path / "different",
        prepared.binding,
        project_root=ROOT,
        provider_name="offline",
        model_name="fixture",
        prompt_version="fixture-1",
    )
    with pytest.raises(ValueError, match="blocked static report"):
        artifacts.load_notebook_pipeline_artifact(
            path, prepared.binding, directory, project_root=ROOT
        )


@pytest.fixture
def capture_directory(tmp_path: Path, prepared: _Prepared) -> Path:
    path = tmp_path / "capture"
    shutil.copytree(prepared.directory, path)
    return path


def _run(prepared: _Prepared, path: Path, **kwargs: Any) -> NotebookPipelineRun:
    return run_notebook_pipeline_capture(
        path,
        prepared.binding,
        TARGETS,
        project_root=ROOT,
        allow_untrusted_code_execution=True,
        **kwargs,
    )


def test_consent_is_required_before_reading_or_starting(
    prepared: _Prepared,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("consent must precede I/O and process start")

    monkeypatch.setattr(execution_module, "load_notebook_body_capture", forbidden)
    consents: tuple[Any, ...] = (False, None, 1)
    for consent in consents:
        with pytest.raises(ValueError, match="allow_untrusted_code_execution"):
            run_notebook_pipeline_capture(
                "missing",
                prepared.binding,
                TARGETS,
                project_root=ROOT,
                allow_untrusted_code_execution=consent,
            )


@pytest.mark.parametrize("failure", ["missing", "provider", "schema", "body"])
def test_failed_static_slot_prevents_every_execution(
    prepared: _Prepared,
    capture_directory: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    response = next((capture_directory / "responses").iterdir())
    row = json.loads(response.read_text(encoding="utf-8"))
    if failure == "missing":
        response.unlink()
    elif failure == "provider":
        row.update(
            raw_response=None, raw_response_sha256=None, provider_error=["error", "offline failure"]
        )
    else:
        raw = (
            "not JSON"
            if failure == "schema"
            else row["raw_response"].replace("assert ", "assert False and ")
        )
        if raw == row["raw_response"]:
            body = json.loads(raw)
            body["body_code"] = "pass"
            raw = json.dumps(body)
        row.update(raw_response=raw, raw_response_sha256=_raw_sha256(raw))
    if failure != "missing":
        response.write_text(json.dumps(row), encoding="utf-8")

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("one rejection forbids any worker")

    monkeypatch.setattr(execution_module, "_start_worker", forbidden)
    run = _run(prepared, capture_directory)
    assert run.execution is None
    assert run.request_sha256 is None
    assert run.static.batch.planned_count == 9
    assert run.static.batch.accepted_count == 8
    compared = compare_notebook_pipeline_run(run, EXPECTED)
    assert compared.status == "not_evaluated"
    assert compared.outputs[0].status == "not_evaluated"


@pytest.mark.parametrize("targets", [(), ("bad",), (NotebookObservation("unknown"),), TARGETS * 2])
def test_invalid_observation_inventory_prevents_execution(
    prepared: _Prepared, targets: Any
) -> None:
    with pytest.raises(ValueError, match="observations"):
        run_notebook_pipeline_capture(
            prepared.directory,
            prepared.binding,
            targets,
            project_root=ROOT,
            allow_untrusted_code_execution=True,
        )


def test_observation_contract_and_source_integrity(prepared: _Prepared) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        NotebookObservation("")
    with pytest.raises(ValueError, match="kind"):
        NotebookObservation("accuracy", cast("Any", "unknown"))
    with pytest.raises(ValueError, match="hash mismatch"):
        run_notebook_pipeline_capture(
            prepared.directory,
            replace(prepared.binding, content_sha256="0" * 64),
            TARGETS,
            project_root=ROOT,
            allow_untrusted_code_execution=True,
        )


@pytest.mark.parametrize(
    "mode",
    [
        "timeout",
        "nonzero",
        "missing",
        "directory",
        "redirect",
        "oversized",
        "malformed",
        "identity",
        "outputs",
        "duplicate",
        "nan",
        "start",
        "logs",
        "success",
    ],
)
def test_parent_handles_worker_outcomes(
    prepared: _Prepared,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    settings = BehavioralExecutionConfig(max_result_bytes=2048, max_capture_bytes=16)

    class Process:
        def __init__(self, command: tuple[str, ...]) -> None:
            self.result = Path(command[5])

        def wait(self, *, timeout: float) -> int:
            assert timeout == settings.timeout_seconds
            if mode == "timeout":
                raise subprocess.TimeoutExpired("worker", timeout)
            if mode == "nonzero":
                return 7
            if mode == "missing":
                return 0
            if mode == "directory":
                self.result.mkdir()
                return 0
            result = _successful(prepared.binding, prepared.run.capture.content_sha256)
            if mode == "logs":
                result["stdout"] = "x" * 17
            if mode == "identity":
                result["case_id"] = "wrong"
            if mode == "outputs":
                result["outputs"] = [
                    {"output_name": "wrong", "value": {"kind": "scalar", "value": 1}}
                ]
            raw = json.dumps(result)
            if mode == "oversized":
                raw = "x" * (settings.max_result_bytes + 1)
            if mode == "malformed":
                raw = "broken"
            if mode == "duplicate":
                raw = '{"case_id":"a","case_id":"b"}'
            if mode == "nan":
                raw = '{"value":NaN}'
            self.result.write_text(raw, encoding="utf-8")
            return 0

    def start(command: tuple[str, ...], _directory: Path) -> Process:
        if mode == "start":
            raise OSError("controlled start failure")
        assert command[1:4] == ("-I", "-m", execution_module._WORKER)
        return Process(command)

    terminated: list[Process] = []
    monkeypatch.setattr(execution_module, "_start_worker", start)
    monkeypatch.setattr(execution_module, "_terminate_process_tree", terminated.append)
    if mode == "redirect":
        original_resolve = Path.resolve

        def redirected(self: Path, *args: Any, **kwargs: Any) -> Path:
            if self.name == "result.json":
                return ROOT / "README.md"
            return original_resolve(self, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", redirected)
    run = _run(prepared, prepared.directory, config=settings)
    assert run.execution is not None
    expected = {"timeout": "timeout", "start": "setup_failure", "success": "success"}.get(
        mode, "process_failure"
    )
    assert run.execution.status == expected
    assert bool(terminated) == (mode == "timeout")
    compared = compare_notebook_pipeline_run(run, EXPECTED)
    assert compared.status == ("matched" if mode == "success" else "not_evaluated")


def test_snapshot_project_and_envelope_bounds(prepared: _Prepared, tmp_path: Path) -> None:
    module = prepared.run.static.batch.module_source
    assert module is not None
    settings = BehavioralExecutionConfig(max_request_bytes=1)
    with pytest.raises(ValueError, match="snapshots exceed"):
        execution_module._prepare_project(
            tmp_path / "small", prepared.binding, module, ROOT, settings
        )
    source_size = sum(file.size_bytes for file in prepared.binding.files)
    with pytest.raises(ValueError, match="project exceeds"):
        execution_module._prepare_project(
            tmp_path / "project",
            prepared.binding,
            module,
            ROOT,
            replace(settings, max_request_bytes=source_size),
        )
    with pytest.raises(ValueError, match="envelope exceeds"):
        execution_module._execute(tmp_path, prepared.payload, prepared.run.capture, settings)


def test_changed_snapshot_and_catalog_fail_before_worker(
    prepared: _Prepared,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = prepared.run.static.batch.module_source
    assert module is not None
    read = _read_file

    def changed(*args: Any) -> tuple[NotebookSourceFile, bytes]:
        identity, data = read(*args)
        return replace(identity, size_bytes=identity.size_bytes + 1), data

    with monkeypatch.context() as context:
        context.setattr(execution_module, "_read_file", changed)
        with pytest.raises(ValueError, match="snapshot does not match"):
            execution_module._prepare_project(
                tmp_path / "changed", prepared.binding, module, ROOT, prepared.run.configuration
            )
    generate = generate_kedro_project

    def wrong_catalog(*args: Any, **kwargs: Any) -> tuple[Path, ...]:
        files = generate(*args, **kwargs)
        (Path(args[1]) / "conf/base/catalog.yml").write_text("wrong", encoding="utf-8")
        return files

    monkeypatch.setattr(execution_module, "generate_kedro_project", wrong_catalog)
    with pytest.raises(ValueError, match="catalog does not match"):
        execution_module._prepare_project(
            tmp_path / "catalog", prepared.binding, module, ROOT, prepared.run.configuration
        )


def test_comparison_inventory_mismatch_and_bounded_difference(prepared: _Prepared) -> None:
    with pytest.raises(ValueError, match="exact observation"):
        compare_notebook_pipeline_run(prepared.run, ())
    mismatch = compare_notebook_pipeline_run(
        prepared.run,
        (ExpectedBehaviorOutput("accuracy", ScalarBehaviorValue(0.0), ComparisonSpec("exact")),),
    )
    assert mismatch.status == "mismatch"
    assert mismatch.outputs[0].diagnostic_message is not None
    assert (
        mismatch.expectations_sha256
        != compare_notebook_pipeline_run(prepared.run, EXPECTED).expectations_sha256
    )
    assert prepared.run.execution is not None
    malformed = replace(
        prepared.run.execution,
        outputs=(replace(prepared.run.execution.outputs[0], output_name="wrong"),),
    )
    with pytest.raises(ValueError, match="comparison inventory"):
        compare_notebook_pipeline_run(replace(prepared.run, execution=malformed), EXPECTED)
    identity = replace(prepared.run.execution, case_id="wrong")
    with pytest.raises(ValueError, match="statically ready capture"):
        compare_notebook_pipeline_run(replace(prepared.run, execution=identity), EXPECTED)


@pytest.mark.parametrize("mode", ["success", "setup", "exception", "observation", "missing"])
def test_private_worker_states_with_trusted_payload(
    prepared: _Prepared,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    original = worker._run_project

    def controlled(
        project: Path,
        nodes: list[object],
        targets: tuple[NotebookObservation, ...],
    ) -> tuple[dict[str, BehaviorValue], tuple[Any, Any, Any]]:
        if mode == "setup":
            raise ImportError("controlled setup failure")
        observed, (runner, pipeline, catalog) = original(project, nodes, targets)

        class Runner:
            def run(self, _pipeline: object, _catalog: object) -> None:
                if mode == "exception":
                    raise RuntimeError("controlled pipeline exception")
                if mode == "observation":
                    raise RuntimeError("wrapped observation") from worker._ObservationError(
                        "unsupported output"
                    )
                if mode != "missing":
                    runner.run(pipeline, catalog)

        return observed, (Runner(), pipeline, catalog)

    monkeypatch.setattr(worker, "_run_project", controlled)
    result = worker.run_notebook_worker_payload(prepared.payload)
    expected = {
        "success": "success",
        "setup": "setup_failure",
        "exception": "exception",
        "observation": "serialization_failure",
        "missing": "serialization_failure",
    }[mode]
    assert result["status"] == expected, result
    if mode == "success":
        assert result["outputs"] == [
            {"output_name": "accuracy", "value": {"kind": "scalar", "value": 1.0}}
        ]
    else:
        assert result["outputs"] == []


def test_observers_preserve_nullable_table_series_model_and_reject_unsupported() -> None:
    pd = importlib.import_module("pandas")
    table = worker._observe(pd.DataFrame({"x": [1.0, float("nan")]}), "value")
    assert isinstance(table, TableBehaviorValue)
    assert table.rows == ((1.0,), (None,))
    assert table.dtypes == ("float64",)
    series = worker._observe(pd.Series([1, 2], index=[3, 7]), "series")
    assert isinstance(series, TableBehaviorValue)
    assert series.index == (3, 7)
    with pytest.raises(ValueError, match="Series"):
        worker._observe(1, "series")
    with pytest.raises(ValueError, match="DecisionTreeClassifier"):
        worker._observe(1, "decision_tree")
    with pytest.raises(ValueError, match="columns must"):
        worker._observe(pd.DataFrame({1: [2]}), "value")
    with pytest.raises(ValueError, match="finite"):
        worker._observe(pd.DataFrame({"x": [float("inf")]}), "value")
    tree = importlib.import_module("sklearn.tree").DecisionTreeClassifier(
        max_depth=2, random_state=7
    )
    tree.fit([[0], [1]], [0, 1])
    assert worker._observe(tree, "decision_tree").kind == "object"
    error = RuntimeError("cycle")
    error.__cause__ = error
    assert not worker._observation_failure(error)


@pytest.mark.parametrize("mode", ["wiring", "observation"])
def test_real_trusted_project_rejects_wiring_and_observer_failure(
    prepared: _Prepared,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    payload = dict(prepared.payload)
    if mode == "wiring":
        payload["nodes"] = []
    else:
        payload["observations"] = [{"dataset": "accuracy", "kind": "series"}]
    result = worker.run_notebook_worker_payload(payload)
    assert result["status"] == ("setup_failure" if mode == "wiring" else "serialization_failure")
    assert result["outputs"] == []
    assert result["exception"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "wrong"},
        {"extra": 1},
        {"observations": []},
        {"observations": [{"dataset": "accuracy", "kind": "value"}] * 2},
        {"observations": [{"dataset": "accuracy", "kind": "wrong"}]},
    ],
)
def test_worker_request_schema_rejects_changes(
    prepared: _Prepared, change: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match=r"version|fields|observations|kind"):
        worker.run_notebook_worker_payload({**prepared.payload, **change})


@pytest.mark.parametrize("mode", ["escape", "absolute", "root", "duplicate", "hash", "base64"])
def test_worker_snapshot_paths_and_bytes_are_checked(tmp_path: Path, mode: str) -> None:
    row = {
        "path": "file",
        "sha256": hashlib.sha256(b"ok").hexdigest(),
        "data": base64.b64encode(b"ok").decode(),
    }
    if mode == "escape":
        row["path"] = "../outside"
    if mode == "absolute":
        row["path"] = str(tmp_path / "absolute")
    if mode == "root":
        row["path"] = "."
    if mode == "hash":
        row["sha256"] = "0" * 64
    if mode == "base64":
        row["data"] = "!"
    rows = [row, row] if mode == "duplicate" else [row]
    with pytest.raises(ValueError, match=r"snapshot|base64"):
        worker._files(tmp_path / "snapshots", rows)


def test_worker_snapshot_preserves_empty_file_bytes(tmp_path: Path) -> None:
    worker._files(
        tmp_path / "snapshots",
        [
            {
                "path": "empty.csv",
                "data": "",
                "sha256": hashlib.sha256(b"").hexdigest(),
            }
        ],
    )
    assert (tmp_path / "snapshots/empty.csv").read_bytes() == b""


@pytest.mark.parametrize(
    "mode",
    [
        "success",
        "oversized",
        "tiny",
        "request_size",
        "hash",
        "invalid",
        "duplicate",
        "nan",
        "negative",
        "bad_limit",
        "argv",
        "arguments",
    ],
)
def test_worker_main_bounds_request_and_result(
    prepared: _Prepared,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    raw = json.dumps(prepared.payload).encode()
    request, result = tmp_path / "request.json", tmp_path / "result.json"
    if mode == "invalid":
        raw = b"broken"
    if mode == "duplicate":
        raw = b'{"x":1,"x":2}'
    if mode == "nan":
        raw = b'{"x":NaN}'
    request.write_bytes(raw)
    args = [str(request), str(result), str(len(raw) + 1), "1024", hashlib.sha256(raw).hexdigest()]
    if mode == "request_size":
        args[2] = str(len(raw) - 1)
    if mode == "hash":
        args[4] = "0" * 64
    if mode == "negative":
        args[3] = "0"
    if mode == "bad_limit":
        args[2] = "bad"
    if mode == "tiny":
        args[3] = "1"
    if mode == "arguments":
        args = []

    def outcome(_payload: object) -> dict[str, object]:
        response = _successful(prepared.binding, prepared.run.capture.content_sha256)
        if mode in ("oversized", "tiny"):
            response["stdout"] = "x" * 5000
        return response

    monkeypatch.setattr(worker, "run_notebook_worker_payload", outcome)
    if mode == "argv":
        monkeypatch.setattr(sys, "argv", ["worker", *args])
        code = worker.main()
    else:
        code = worker.main(args)
    expected = (
        0
        if mode in ("success", "oversized", "argv")
        else 2
        if mode in ("negative", "arguments")
        else 3
    )
    assert code == expected
    if code == 0:
        payload = json.loads(result.read_text(encoding="utf-8"))
        assert payload["status"] == ("serialization_failure" if mode == "oversized" else "success")


@pytest.mark.integration
@pytest.mark.parametrize("mode", ["timeout", "result_limit", "observer"])
def test_public_worker_runtime_failures_on_trusted_capture(prepared: _Prepared, mode: str) -> None:
    targets = TARGETS
    config = BehavioralExecutionConfig(timeout_seconds=60)
    if mode == "timeout":
        config = replace(config, timeout_seconds=0.001)
    elif mode == "result_limit":
        config = replace(config, max_result_bytes=1024, max_capture_bytes=16384)
    else:
        targets = (NotebookObservation("accuracy", "series"),)
    run = run_notebook_pipeline_capture(
        prepared.directory,
        prepared.binding,
        targets,
        project_root=ROOT,
        allow_untrusted_code_execution=True,
        config=config,
    )
    assert run.execution is not None
    assert run.execution.status == ("timeout" if mode == "timeout" else "serialization_failure")
    assert run.execution.outputs == ()
    assert compare_notebook_pipeline_run(run, EXPECTED).status == "not_evaluated"


def _ledger(tmp_path: Path, prepared: _Prepared, **kwargs: Any) -> Path:
    return ledger_module.create_notebook_execution_ledger(
        tmp_path / "ledger",
        prepared.binding,
        prepared.directory,
        TARGETS,
        EXPECTED,
        project_root=ROOT,
        **kwargs,
    )


def _inspect_ledger(
    path: Path, prepared: _Prepared, **kwargs: Any
) -> ledger_module.NotebookExecutionLedger:
    return ledger_module.load_notebook_execution_ledger(
        path, prepared.binding, prepared.directory, project_root=ROOT, **kwargs
    )


def _attempt(
    path: Path, prepared: _Prepared, identifier: str = "attempt-1", **kwargs: Any
) -> ledger_module.NotebookPipelineAttempt:
    return ledger_module.run_notebook_pipeline_attempt(
        path,
        prepared.binding,
        prepared.directory,
        identifier,
        project_root=ROOT,
        allow_untrusted_code_execution=True,
        **kwargs,
    )


def _reserve(
    path: Path, prepared: _Prepared, identifier: str = "attempt-1"
) -> ledger_module.NotebookPipelineAttempt:
    return ledger_module.reserve_notebook_pipeline_attempt(
        path, prepared.binding, prepared.directory, identifier, project_root=ROOT
    )


def _ledger_worker(
    monkeypatch: pytest.MonkeyPatch, prepared: _Prepared, run: NotebookPipelineRun | None = None
) -> None:
    monkeypatch.setattr(
        ledger_module, "run_notebook_pipeline_capture", lambda *_a, **_k: run or prepared.run
    )


def _rewrite_ledger(path: Path, **changes: Any) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(_resign({**payload, **changes})), encoding="utf-8")


def test_ledger_reserves_before_worker_and_counts_unfinished(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _ledger(tmp_path, prepared)
    assert _inspect_ledger(path, prepared).attempts == ()
    first = _reserve(path, prepared, "interrupted")
    assert first.status == "unfinished"

    def execute(*_args: Any, **kwargs: Any) -> NotebookPipelineRun:
        ledger = _inspect_ledger(path, prepared)
        assert {item.attempt_id for item in ledger.attempts} == {"interrupted", "complete"}
        assert all(item.status == "unfinished" for item in ledger.attempts)
        assert kwargs["allow_untrusted_code_execution"] is True
        assert kwargs["expected_capture_sha256"] == prepared.run.capture.content_sha256
        assert kwargs["config"] == prepared.run.configuration
        return prepared.run

    monkeypatch.setattr(ledger_module, "run_notebook_pipeline_capture", execute)
    complete = _attempt(path, prepared, "complete")
    assert complete.status == "matched"
    monkeypatch.setattr(
        ledger_module,
        "run_notebook_pipeline_capture",
        lambda *_a, **_k: pytest.fail("inspection must not execute"),
    )
    ledger = _inspect_ledger(path, prepared)
    assert set(ledger.attempts) == {first, complete}
    summary = ledger_module.notebook_execution_ledger_summary(ledger)
    assert summary["total_reserved"] == 2
    assert summary["published"] == summary["unfinished"] == 1
    assert summary["status_counts"] == {"unfinished": 1, "matched": 1}
    assert json.loads(prepared.binding.review_json)["status"] == "pending"
    before = {item: item.read_bytes() for item in (path / "results").iterdir()}
    for identifier in ("interrupted", "complete"):
        with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
            _attempt(path, prepared, identifier)
    assert all(item.read_bytes() == content for item, content in before.items())
    with pytest.raises(FileExistsError):
        _ledger(tmp_path, prepared)


@pytest.mark.parametrize("consent", [False, None, 1])
def test_ledger_consent_precedes_all_io(tmp_path: Path, prepared: _Prepared, consent: Any) -> None:
    with pytest.raises(ValueError, match="allow_untrusted_code_execution=True"):
        ledger_module.run_notebook_pipeline_attempt(
            tmp_path / "missing",
            prepared.binding,
            tmp_path / "missing",
            "attempt",
            project_root=tmp_path,
            allow_untrusted_code_execution=consent,
        )
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("failure", ["exception", "interrupt", "publication"])
def test_ledger_failures_leave_reservation_without_retry(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    path = _ledger(tmp_path, prepared)
    _ledger_worker(monkeypatch, prepared)
    expected_error: type[BaseException]
    if failure == "publication":
        original = ledger_module._write

        def write(destination: Path, payload: dict[str, object], limit: int) -> None:
            if destination.parent.name == "results":
                raise OSError("synthetic publication failure")
            return original(destination, payload, limit)

        monkeypatch.setattr(ledger_module, "_write", write)
        expected_error = OSError
    else:
        expected_error = KeyboardInterrupt if failure == "interrupt" else RuntimeError

        def execute(*_args: Any, **_kwargs: Any) -> NotebookPipelineRun:
            raise expected_error("synthetic interruption")

        monkeypatch.setattr(ledger_module, "run_notebook_pipeline_capture", execute)
    with pytest.raises(expected_error):
        _attempt(path, prepared)
    assert _inspect_ledger(path, prepared).attempts[0].status == "unfinished"
    assert list((path / "results").iterdir()) == []
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        _attempt(path, prepared)


@pytest.mark.parametrize(
    "status",
    [
        "matched",
        "mismatch",
        "timeout",
        "exception",
        "setup_failure",
        "process_failure",
        "serialization_failure",
        "static_rejected",
    ],
)
def test_ledger_retains_each_observed_outcome(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    current = prepared
    run = prepared.run
    if status == "static_rejected":
        directory = create_notebook_body_capture(
            tmp_path / "incomplete",
            prepared.binding,
            project_root=ROOT,
            provider_name="offline",
            model_name="missing",
            prompt_version="fixture-1",
        )
        run = _run(prepared, directory)
        current = replace(prepared, directory=directory, run=run)
    elif status != "matched":
        result = _successful(prepared.binding, prepared.run.capture.content_sha256)
        if status == "mismatch":
            result["outputs"] = [
                {"output_name": "accuracy", "value": {"kind": "scalar", "value": 0.0}}
            ]
        else:
            result.update(status=status, outputs=[], diagnostic_message="synthetic failure")
            if status == "exception":
                result["exception"] = {"type_name": "ValueError", "message": "synthetic"}
        run = replace(run, execution=_result_from_worker(result, 0.0))
    path = _ledger(tmp_path, current)
    _ledger_worker(monkeypatch, current, run)
    attempt = _attempt(path, current)
    assert attempt.status == status
    assert _inspect_ledger(path, current).attempts == (attempt,)
    summary = ledger_module.notebook_execution_ledger_summary(_inspect_ledger(path, current))
    assert summary["total_reserved"] == summary["published"] == 1
    assert summary["unfinished"] == 0
    assert summary["status_counts"] == {status: 1}


@pytest.mark.parametrize(
    "mode",
    [
        "version",
        "source",
        "extra",
        "missing",
        "observation_keys",
        "observation_kind",
        "expectations",
        "config",
        "boolean_timeout",
    ],
)
def test_ledger_rejects_bad_manifest_even_when_rehashed(
    tmp_path: Path, prepared: _Prepared, mode: str
) -> None:
    path = _ledger(tmp_path, prepared)
    target = path / "manifest.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    if mode == "version":
        payload["schema_version"] = "future"
    elif mode == "source":
        payload["binding_sha256"] = "0" * 64
    elif mode == "extra":
        payload["extra"] = True
    elif mode == "missing":
        del payload["observations"]
    elif mode == "observation_keys":
        payload["observations"][0]["extra"] = True
    elif mode == "observation_kind":
        payload["observations"][0]["kind"] = "pickle"
    elif mode == "expectations":
        payload["expectations"] = []
    elif mode == "config":
        payload["configuration"]["extra"] = 1
    else:
        payload["configuration"]["timeout_seconds"] = True
    target.write_text(json.dumps(_resign(payload)), encoding="utf-8")
    with pytest.raises(ValueError, match=r"ledger|fields|observation|timeout_seconds"):
        _inspect_ledger(path, prepared)


@pytest.mark.parametrize(
    "mode", ["timestamp", "naive_date", "noncanonical_date", "manifest", "filename", "extra"]
)
def test_ledger_rejects_bad_reservation(tmp_path: Path, prepared: _Prepared, mode: str) -> None:
    path = _ledger(tmp_path, prepared)
    _reserve(path, prepared)
    target = next((path / "attempts").iterdir())
    changes: dict[str, dict[str, object]] = {
        "timestamp": {"reserved_at": "not a date"},
        "naive_date": {"reserved_at": "2026-10-17T12:00:00"},
        "noncanonical_date": {"reserved_at": "2026-10-17T12:00:00Z"},
        "manifest": {"manifest_sha256": "0" * 64},
        "filename": {"attempt_id": "different"},
        "extra": {"extra": 1},
    }
    _rewrite_ledger(target, **changes[mode])
    with pytest.raises(ValueError, match=r"isoformat|UTC|identity mismatch|fields"):
        _inspect_ledger(path, prepared)


@pytest.mark.parametrize("mode", ["reservation", "extra", "artifact", "settings", "replay"])
def test_ledger_rejects_changed_result_even_when_rehashed(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    path = _ledger(tmp_path, prepared)
    _ledger_worker(monkeypatch, prepared)
    _attempt(path, prepared)
    target = next((path / "results").iterdir())
    payload = json.loads(target.read_text(encoding="utf-8"))
    if mode == "reservation":
        payload["reservation_sha256"] = "0" * 64
    elif mode == "extra":
        payload["extra"] = 1
    elif mode == "artifact":
        payload["artifact"]["comparison"]["status"] = "mismatch"
        _resign(payload["artifact"])
    else:
        run = (
            replace(
                prepared.run, configuration=replace(prepared.run.configuration, timeout_seconds=3)
            )
            if mode == "settings"
            else prepared.run
        )
        payload["artifact"] = artifacts.notebook_pipeline_artifact_to_dict(
            artifacts.create_notebook_pipeline_artifact(
                run, EXPECTED, source_artifact_sha256="1" * 64 if mode == "replay" else None
            )
        )
    target.write_text(json.dumps(_resign(payload)), encoding="utf-8")
    with pytest.raises(ValueError, match=r"ledger|artifact|invalid result fields"):
        _inspect_ledger(path, prepared)


@pytest.mark.parametrize(
    "mode",
    [
        "layout",
        "directory",
        "entry",
        "short",
        "hex",
        "regular",
        "orphan",
        "digest",
        "json",
        "duplicate",
        "nonfinite",
    ],
)
def test_ledger_rejects_invalid_layout_and_bytes(
    tmp_path: Path, prepared: _Prepared, mode: str
) -> None:
    path = _ledger(tmp_path, prepared)
    if mode == "layout":
        (path / "unexpected").touch()
    elif mode == "directory":
        (path / "results").rmdir()
        (path / "results").touch()
    elif mode in ("entry", "short", "hex", "regular"):
        filename = (
            "bad.txt"
            if mode == "entry"
            else "short.json"
            if mode == "short"
            else ("z" if mode == "hex" else "0") * 64 + ".json"
        )
        target = path / "attempts" / filename
        if mode == "regular":
            target.mkdir()
        else:
            target.touch()
    elif mode == "orphan":
        (path / "results" / ("0" * 64 + ".json")).touch()
    else:
        target = path / "manifest.json"
        raw = {
            "digest": '{"content_sha256":"' + "0" * 64 + '"}',
            "json": "{",
            "duplicate": '{"x":1,"x":2}',
            "nonfinite": '{"x":NaN}',
        }[mode]
        target.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match=r"ledger|SHA256|property name|duplicate|non-finite"):
        _inspect_ledger(path, prepared)


@pytest.mark.parametrize("mode", ["empty", "duplicate", "unknown", "expected", "bool", "limit"])
def test_ledger_preflight_does_not_create_invalid_setup(
    tmp_path: Path, prepared: _Prepared, mode: str
) -> None:
    targets = (
        ()
        if mode == "empty"
        else TARGETS * 2
        if mode == "duplicate"
        else (NotebookObservation("unknown"),)
        if mode == "unknown"
        else TARGETS
    )
    options = (
        {"config": replace(prepared.run.configuration, timeout_seconds=True)}
        if mode == "bool"
        else {"max_file_bytes": 1}
        if mode == "limit"
        else {}
    )
    with pytest.raises(ValueError, match=r"ledger|timeout_seconds"):
        ledger_module.create_notebook_execution_ledger(
            tmp_path / "invalid",
            prepared.binding,
            prepared.directory,
            targets,
            () if mode == "expected" else EXPECTED,
            project_root=ROOT,
            **options,
        )
    assert not (tmp_path / "invalid").exists()


def test_ledger_bounds_and_invalid_attempt_ids(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _ledger(tmp_path, prepared, config=prepared.run.configuration)
    for limit in (0, True, 1):
        with pytest.raises(ValueError, match="max_file_bytes"):
            _inspect_ledger(path, prepared, max_file_bytes=limit)
    for limit in (0, True):
        with pytest.raises(ValueError, match="max_attempts"):
            _inspect_ledger(path, prepared, max_attempts=limit)
    with pytest.raises(ValueError, match="attempt_id"):
        _reserve(path, prepared, " ")
    _reserve(path, prepared, "one")
    _reserve(path, prepared, "two")
    with pytest.raises(ValueError, match="max_attempts"):
        _inspect_ledger(path, prepared, max_attempts=1)
    monkeypatch.setattr(ledger_module, "DEFAULT_NOTEBOOK_LEDGER_ATTEMPTS", 2)
    with pytest.raises(ValueError, match="max_attempts"):
        _reserve(path, prepared, "three")
    with pytest.raises(ValueError, match="max_file_bytes"):
        ledger_module._write(tmp_path / "not-written", {}, 1)
    assert not (tmp_path / "not-written").exists()


@pytest.mark.parametrize("mode", ["settings", "capture", "reservation", "manifest"])
def test_ledger_refuses_worker_or_reservation_drift(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    path = _ledger(tmp_path, prepared)

    def execute(*_args: Any, **_kwargs: Any) -> NotebookPipelineRun:
        if mode == "settings":
            return replace(
                prepared.run, configuration=replace(prepared.run.configuration, timeout_seconds=3)
            )
        if mode == "capture":
            changed = replace(prepared.run.capture, content_sha256="0" * 64)
            assert prepared.run.execution is not None
            return replace(
                prepared.run,
                capture=changed,
                execution=replace(prepared.run.execution, node_code_case_id=changed.content_sha256),
            )
        if mode == "reservation":
            target = next((path / "attempts").iterdir())
            _rewrite_ledger(target, reserved_at="2026-10-17T00:00:00+00:00")
        else:
            target = path / "manifest.json"
            config = json.loads(target.read_text(encoding="utf-8"))["configuration"]
            config["timeout_seconds"] = 3.0
            _rewrite_ledger(target, configuration=config)
            reservation = next((path / "attempts").iterdir())
            _rewrite_ledger(
                reservation,
                manifest_sha256=json.loads(target.read_text(encoding="utf-8"))["content_sha256"],
            )
        return prepared.run

    monkeypatch.setattr(ledger_module, "run_notebook_pipeline_capture", execute)
    with pytest.raises(ValueError, match=r"ledger|binding|statically ready capture"):
        _attempt(path, prepared)
    assert not list((path / "results").iterdir())


def test_ledger_drift_between_reservation_and_execution_stops_worker(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _ledger(tmp_path, prepared)
    original = ledger_module.reserve_notebook_pipeline_attempt

    def reserve(*args: Any, **kwargs: Any) -> ledger_module.NotebookPipelineAttempt:
        attempt = original(*args, **kwargs)
        _rewrite_ledger(
            next((path / "attempts").iterdir()), reserved_at="2026-10-17T00:00:00+00:00"
        )
        return attempt

    monkeypatch.setattr(ledger_module, "reserve_notebook_pipeline_attempt", reserve)
    monkeypatch.setattr(
        ledger_module,
        "run_notebook_pipeline_capture",
        lambda *_a, **_k: pytest.fail("must not execute"),
    )
    with pytest.raises(ValueError, match="before execution"):
        _attempt(path, prepared)


@pytest.mark.parametrize("mode", ["symlink_directory", "escaped_directory", "escaped_file"])
def test_ledger_rejects_inventory_redirection(
    tmp_path: Path, prepared: _Prepared, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    path = _ledger(tmp_path, prepared)
    target = path / ("manifest.json" if mode == "escaped_file" else "attempts")
    if mode == "symlink_directory":
        original_symlink = Path.is_symlink
        monkeypatch.setattr(
            Path, "is_symlink", lambda value: value == target or original_symlink(value)
        )
    else:
        original_resolve = Path.resolve
        monkeypatch.setattr(
            Path,
            "resolve",
            lambda value, *args, **kwargs: (
                tmp_path if value == target else original_resolve(value, *args, **kwargs)
            ),
        )
    with pytest.raises(ValueError, match=r"ledger.*(local|contained)"):
        _inspect_ledger(path, prepared)


@pytest.mark.integration
def test_ledger_reservation_survives_abrupt_parent_exit(
    tmp_path: Path, prepared: _Prepared
) -> None:
    path = _ledger(tmp_path, prepared)
    script = """
import os
import sys
from pathlib import Path
from notebook_to_kedro import plan_notebook_path
from notebook_to_kedro.evaluation import (
    create_notebook_source_binding, reserve_notebook_pipeline_attempt,
)
root, ledger, capture = map(Path, sys.argv[1:])
contract = root / 'tests/fixtures/evaluation/pilots/customer_churn_v1/contract.json'
binding = create_notebook_source_binding(
    plan_notebook_path(
        root / 'tests/fixtures/notebooks/pilots/customer_churn_v1/customer_churn.ipynb',
        project_root=root,
    ),
    project_root=root, contract_path=contract,
    expected_catalog_path=contract.with_name('expected_catalog.yml'),
)
reserve_notebook_pipeline_attempt(ledger, binding, capture, 'abrupt-exit', project_root=root)
os._exit(17)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(ROOT), str(path), str(prepared.directory)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 17, result.stderr
    ledger = _inspect_ledger(path, prepared)
    assert [(item.attempt_id, item.status) for item in ledger.attempts] == [
        ("abrupt-exit", "unfinished")
    ]
    assert ledger_module.notebook_execution_ledger_summary(ledger)["total_reserved"] == 1
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        _attempt(path, prepared, "abrupt-exit")
