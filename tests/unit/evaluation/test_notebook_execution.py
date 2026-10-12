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
from notebook_to_kedro.evaluation import notebook_execution as execution_module
from notebook_to_kedro.evaluation import notebook_worker as worker
from notebook_to_kedro.evaluation.behavioral_execution import _result_from_worker
from notebook_to_kedro.evaluation.behavioral_worker import _base_result
from notebook_to_kedro.evaluation.notebook_capture import _raw_sha256
from notebook_to_kedro.evaluation.notebook_sources import _read_file
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
        return "fixture-request", _result_from_worker(
            _successful(binding, capture.content_sha256), 0.0
        )

    with pytest.MonkeyPatch.context() as context:
        context.setattr(execution_module, "_execute", capture_payload)
        run = run_notebook_pipeline_capture(
            directory, binding, TARGETS, project_root=ROOT, allow_untrusted_code_execution=True
        )
    return _Prepared(binding, directory, payload, run)


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
    assert result["status"] == expected
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
