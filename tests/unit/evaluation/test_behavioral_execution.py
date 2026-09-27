from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from notebook_to_kedro.evaluation import (
    BEHAVIORAL_EXECUTION_SCHEMA_VERSION,
    BehavioralCase,
    BehavioralExecutionConfig,
    BehavioralExecutionException,
    BehavioralExecutionOutput,
    BehavioralExecutionResult,
    NodeCodeCase,
    ScalarBehaviorValue,
    behavioral_execution_result_to_dict,
    behavioral_execution_result_to_json,
    execute_behavioral_reference,
    load_behavioral_corpus,
    load_node_code_corpus,
)
from notebook_to_kedro.evaluation import behavioral_execution as execution
from notebook_to_kedro.evaluation import behavioral_worker as worker

BEHAVIOR_DIRECTORY = Path("tests/fixtures/evaluation/behavioral/v1")
NODE_DIRECTORY = Path("tests/fixtures/evaluation/node_code/v1")


def _reviewed_pair() -> tuple[BehavioralCase, NodeCodeCase]:
    case = load_behavioral_corpus(BEHAVIOR_DIRECTORY)[0]
    nodes = {item.case_id: item for item in load_node_code_corpus(NODE_DIRECTORY)}
    return case, nodes[case.node_code_case_id]


def _worker_payload(
    *,
    function_code: str = "def transform(value):\n    return value + 1\n",
    inputs: list[object] | None = None,
    output_names: list[str] | None = None,
    max_capture_bytes: int = 64,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "case_id": "case",
        "node_code_case_id": "node",
        "function_name": "transform",
        "function_code": function_code,
        "imports": [],
        "inputs": inputs or [{"kind": "scalar", "value": 1}],
        "output_names": output_names or ["result"],
        "max_capture_bytes": max_capture_bytes,
    }


def _worker_result(**changes: object) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": "1.0",
        "case_id": "case",
        "node_code_case_id": "node",
        "status": "success",
        "outputs": [{"output_name": "result", "value": {"kind": "scalar", "value": 2}}],
        "exception": None,
        "stdout": "",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "diagnostic_message": None,
    }
    result.update(changes)
    return result


def test_execution_config_validates_every_limit() -> None:
    assert BehavioralExecutionConfig().timeout_seconds == 10
    for values in (
        {"timeout_seconds": 0},
        {"timeout_seconds": float("inf")},
        {"max_request_bytes": 0},
        {"max_result_bytes": -1},
        {"max_capture_bytes": True},
    ):
        with pytest.raises(ValueError, match="positive"):
            BehavioralExecutionConfig(**values)


def test_execution_result_contract_and_serialization() -> None:
    result = BehavioralExecutionResult(
        schema_version=BEHAVIORAL_EXECUTION_SCHEMA_VERSION,
        case_id="case",
        node_code_case_id="node",
        status="exception",
        outputs=(),
        exception=BehavioralExecutionException("KeyError", "missing"),
        stdout="out",
        stderr="err",
        stdout_truncated=False,
        stderr_truncated=True,
        duration_seconds=0.25,
    )

    payload = behavioral_execution_result_to_dict(result)

    assert payload["exception"] == {"type_name": "KeyError", "message": "missing"}
    assert json.loads(behavioral_execution_result_to_json(result)) == payload

    success = BehavioralExecutionResult(
        schema_version="1.0",
        case_id="case",
        node_code_case_id="node",
        status="success",
        outputs=(BehavioralExecutionOutput("result", ScalarBehaviorValue(2)),),
        exception=None,
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        duration_seconds=0,
    )
    assert behavioral_execution_result_to_dict(success)["exception"] is None


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": "2.0"}, "schema version"),
        ({"case_id": ""}, "case IDs"),
        ({"status": "unknown"}, "status"),
        ({"duration_seconds": -1}, "duration_seconds"),
        ({"status": "success", "outputs": ()}, "requires outputs"),
        (
            {
                "status": "exception",
                "outputs": (),
                "exception": None,
            },
            "requires one exception",
        ),
        ({"status": "timeout", "outputs": (), "diagnostic_message": None}, "diagnostic"),
    ],
)
def test_execution_result_rejects_inconsistent_state(changes: dict[str, Any], message: str) -> None:
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "case_id": "case",
        "node_code_case_id": "node",
        "status": "success",
        "outputs": (BehavioralExecutionOutput("result", ScalarBehaviorValue(2)),),
        "exception": None,
        "stdout": "",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "duration_seconds": 0.1,
        "diagnostic_message": None,
    }
    values.update(changes)
    with pytest.raises(ValueError, match=message):
        BehavioralExecutionResult(**values)


def test_execution_output_and_exception_require_names() -> None:
    with pytest.raises(ValueError, match="output name"):
        BehavioralExecutionOutput("", ScalarBehaviorValue(1))
    with pytest.raises(ValueError, match="exception type"):
        BehavioralExecutionException("", "message")
    with pytest.raises(ValueError, match="serializable behavior value"):
        BehavioralExecutionOutput("result", cast("Any", object()))


def test_execution_result_rejects_wrong_runtime_member_types() -> None:
    common: dict[str, Any] = {
        "schema_version": "1.0",
        "case_id": "case",
        "node_code_case_id": "node",
        "status": "success",
        "outputs": (BehavioralExecutionOutput("result", ScalarBehaviorValue(2)),),
        "exception": None,
        "stdout": "",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "duration_seconds": 0,
    }
    with pytest.raises(ValueError, match="execution outputs"):
        BehavioralExecutionResult(**{**common, "outputs": (object(),)})
    with pytest.raises(ValueError, match="execution exception"):
        BehavioralExecutionResult(**{**common, "exception": object()})


def test_worker_executes_and_captures_bounded_text() -> None:
    payload = _worker_payload(
        function_code=(
            "def transform(value):\n"
            "    import sys\n"
            "    print('abcdefgh')\n"
            "    print('error', file=sys.stderr)\n"
            "    return {'value': value, 'items': [value, True]}\n"
        ),
        max_capture_bytes=5,
    )

    result = worker.run_worker_payload(payload)

    assert result["status"] == "success"
    assert result["stdout"] == "abcde"
    assert result["stderr"] == "error"
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True
    assert result["outputs"] == [
        {
            "output_name": "result",
            "value": {
                "kind": "object",
                "entries": [
                    {"key": "value", "value": {"kind": "scalar", "value": 1}},
                    {
                        "key": "items",
                        "value": {
                            "kind": "list",
                            "items": [
                                {"kind": "scalar", "value": 1},
                                {"kind": "scalar", "value": True},
                            ],
                        },
                    },
                ],
            },
        }
    ]


def test_worker_reports_call_exception() -> None:
    result = worker.run_worker_payload(
        _worker_payload(function_code="def transform(value):\n    raise KeyError('missing')\n")
    )

    assert result["status"] == "exception"
    assert result["exception"] == {"type_name": "KeyError", "message": "'missing'"}


@pytest.mark.parametrize(
    ("payload", "diagnostic"),
    [
        (
            _worker_payload(
                inputs=[{"kind": "array", "dtype": "invalid", "shape": [1], "values": [1]}]
            ),
            "TypeError",
        ),
        (_worker_payload(function_code="not valid python"), "SyntaxError"),
        (_worker_payload(function_code="transform = 1"), "not callable"),
    ],
)
def test_worker_reports_setup_failures(payload: object, diagnostic: str) -> None:
    result = worker.run_worker_payload(payload)

    assert result["status"] == "setup_failure"
    assert diagnostic in str(result["diagnostic_message"])


@pytest.mark.parametrize(
    ("function_code", "output_names", "diagnostic"),
    [
        ("def transform(value):\n    return object()\n", ["result"], "unsupported"),
        ("def transform(value):\n    return float('nan')\n", ["result"], "finite"),
        ("def transform(value):\n    return {1: value}\n", ["result"], "keys"),
        ("def transform(value):\n    return value\n", ["one", "two"], "matching tuple"),
    ],
)
def test_worker_reports_serialization_failures(
    function_code: str, output_names: list[str], diagnostic: str
) -> None:
    result = worker.run_worker_payload(
        _worker_payload(function_code=function_code, output_names=output_names)
    )

    assert result["status"] == "serialization_failure"
    assert diagnostic in str(result["diagnostic_message"])


def test_worker_materializes_and_serializes_arrays_tables_and_multiple_outputs() -> None:
    result = worker.run_worker_payload(
        _worker_payload(
            function_code="def transform(array, table):\n    return array, table\n",
            inputs=[
                {"kind": "array", "dtype": "int64", "shape": [2], "values": [1, 2]},
                {
                    "kind": "table",
                    "columns": ["value"],
                    "dtypes": ["int64"],
                    "rows": [[3], [4]],
                    "index": [10, 11],
                },
            ],
            output_names=["array", "table"],
        )
    )

    assert result["status"] == "success"
    outputs = cast("list[dict[str, Any]]", result["outputs"])
    assert outputs[0]["value"]["kind"] == "array"
    assert outputs[1]["value"]["kind"] == "table"
    assert outputs[1]["value"]["index"] == [10, 11]


def test_worker_materializes_nested_values_and_table_without_index() -> None:
    result = worker.run_worker_payload(
        _worker_payload(
            function_code=(
                "def transform(items, mapping, table):\n    return items, mapping, table\n"
            ),
            inputs=[
                {
                    "kind": "list",
                    "items": [{"kind": "scalar", "value": 1}],
                },
                {
                    "kind": "object",
                    "entries": [{"key": "name", "value": {"kind": "scalar", "value": "value"}}],
                },
                {
                    "kind": "table",
                    "columns": ["value"],
                    "dtypes": ["float64"],
                    "rows": [[1.5]],
                    "index": [],
                },
            ],
            output_names=["items", "mapping", "table"],
        )
    )

    assert result["status"] == "success"


def test_worker_rejects_non_string_table_columns_and_runtime_scalars() -> None:
    table_result = worker.run_worker_payload(
        _worker_payload(
            function_code=(
                "def transform(value):\n"
                "    import pandas as pd\n"
                "    return pd.DataFrame({1: [value]})\n"
            )
        )
    )
    assert table_result["status"] == "serialization_failure"
    assert "columns" in str(table_result["diagnostic_message"])

    assert worker._serialize(1.5) == ScalarBehaviorValue(1.5)
    numpy = pytest.importorskip("numpy")
    assert worker._runtime_primitive(numpy.int64(2)) == 2
    with pytest.raises(ValueError, match="unsupported runtime scalar"):
        worker._runtime_primitive(1j)


def test_bounded_capture_handles_multibyte_text_and_rejects_non_text() -> None:
    capture = worker._BoundedTextCapture(2)

    assert capture.writable() is True
    assert capture.write("e") == 1
    assert capture.write("\N{LATIN SMALL LETTER E WITH ACUTE}") == 1
    assert capture.getvalue() == "e"
    assert capture.truncated is True
    with pytest.raises(TypeError, match="text"):
        capture.write(cast("str", 1))


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "2.0"},
        {"max_capture_bytes": 0},
        {"imports": [""]},
        {"unexpected": True},
    ],
)
def test_worker_rejects_invalid_requests(change: dict[str, object]) -> None:
    payload = _worker_payload()
    payload.update(change)
    with pytest.raises(ValueError, match=r"."):
        worker.run_worker_payload(payload)


def test_worker_strict_helpers_reject_wrong_shapes() -> None:
    for invalid_object in (None, {1: "value"}):
        with pytest.raises(ValueError, match="object"):
            worker._object(invalid_object, "object")
    with pytest.raises(ValueError, match="array"):
        worker._array(None, "array")
    with pytest.raises(ValueError, match="string"):
        worker._string(1, "string")
    with pytest.raises(ValueError, match="empty"):
        worker._non_empty_string("", "name")
    for invalid_integer in (True, 0, "1"):
        with pytest.raises(ValueError, match="positive integer"):
            worker._positive_int(invalid_integer, "limit")
    with pytest.raises(ValueError, match="invalid payload fields"):
        worker._exact_keys({"extra": True}, {"required"}, "payload")


def test_worker_main_writes_results_and_bounds_large_results(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(_worker_payload()), encoding="utf-8")

    assert worker.main([str(request_path), str(result_path), "10000"]) == 0
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "success"

    assert worker.main([str(request_path), str(result_path), "300"]) == 0
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "serialization_failure"
    assert worker.main([str(request_path), str(result_path), "298"]) == 3


def test_worker_main_uses_process_arguments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(_worker_payload()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["worker", str(request_path), str(result_path), "10000"],
    )

    assert worker.main() == 0


@pytest.mark.parametrize(
    "arguments",
    [[], ["one", "two", "three", "four"], ["request", "result", "0"], ["missing", "result", "10"]],
)
def test_worker_main_rejects_invalid_invocations(arguments: list[str]) -> None:
    assert worker.main(arguments) in (2, 3)


def test_execute_reference_rejects_oversized_request() -> None:
    case, node = _reviewed_pair()
    with pytest.raises(ValueError, match="max_request_bytes"):
        execute_behavioral_reference(
            case,
            node,
            config=BehavioralExecutionConfig(max_request_bytes=1),
        )


class _FakeProcess:
    def __init__(self, return_code: int = 0, *, timeout: bool = False) -> None:
        self.pid = 123
        self.return_code = return_code
        self.timeout = timeout
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        if self.timeout:
            raise subprocess.TimeoutExpired("worker", timeout or 0.0)
        return self.return_code

    def kill(self) -> None:
        self.killed = True


def test_execute_reference_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    case, node = _reviewed_pair()
    process = _FakeProcess(timeout=True)

    def fake_popen(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        return cast("subprocess.Popen[bytes]", process)

    def ignore_termination(_candidate: subprocess.Popen[bytes]) -> None:
        return None

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(execution, "_terminate_process_tree", ignore_termination)

    result = execute_behavioral_reference(case, node)

    assert result.status == "timeout"
    assert "exceeded" in str(result.diagnostic_message)


def test_execute_reference_reports_nonzero_worker_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    case, node = _reviewed_pair()

    def fake_popen(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        return cast("subprocess.Popen[bytes]", _FakeProcess(return_code=7))

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    result = execute_behavioral_reference(case, node)

    assert result.status == "process_failure"
    assert result.diagnostic_message == "reference worker exited with code 7"


def test_execute_reference_reads_worker_result(monkeypatch: pytest.MonkeyPatch) -> None:
    case, node = _reviewed_pair()

    def fake_popen(command: tuple[str, ...], **_kwargs: object) -> subprocess.Popen[bytes]:
        Path(command[-2]).write_text(
            json.dumps(
                _worker_result(case_id=case.case_id, node_code_case_id=case.node_code_case_id)
            ),
            encoding="utf-8",
        )
        return cast("subprocess.Popen[bytes]", _FakeProcess())

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    result = execute_behavioral_reference(case, node)

    assert result.status == "success"
    assert result.outputs[0].value == ScalarBehaviorValue(2)


def test_execute_reference_rejects_worker_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, node = _reviewed_pair()

    def fake_popen(command: tuple[str, ...], **_kwargs: object) -> subprocess.Popen[bytes]:
        Path(command[-2]).write_text(json.dumps(_worker_result()), encoding="utf-8")
        return cast("subprocess.Popen[bytes]", _FakeProcess())

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    result = execute_behavioral_reference(case, node)

    assert result.status == "process_failure"
    assert "identity" in str(result.diagnostic_message)


def test_execute_reference_reports_invalid_worker_result(monkeypatch: pytest.MonkeyPatch) -> None:
    case, node = _reviewed_pair()

    def fake_popen(command: tuple[str, ...], **_kwargs: object) -> subprocess.Popen[bytes]:
        Path(command[-2]).write_text("not json", encoding="utf-8")
        return cast("subprocess.Popen[bytes]", _FakeProcess())

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    result = execute_behavioral_reference(case, node)

    assert result.status == "process_failure"


def test_execute_reference_rejects_oversized_worker_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, node = _reviewed_pair()

    def fake_popen(command: tuple[str, ...], **_kwargs: object) -> subprocess.Popen[bytes]:
        Path(command[-2]).write_bytes(b"x" * 101)
        return cast("subprocess.Popen[bytes]", _FakeProcess())

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    result = execute_behavioral_reference(
        case,
        node,
        config=BehavioralExecutionConfig(max_result_bytes=100),
    )

    assert result.status == "process_failure"
    assert "max_result_bytes" in str(result.diagnostic_message)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {**_worker_result(), "status": "unknown"},
        {**_worker_result(), "outputs": None},
        {**_worker_result(), "diagnostic_message": 1},
        {**_worker_result(), "schema_version": 1},
        {**_worker_result(), "stdout_truncated": 1},
        {**_worker_result(), "unexpected": True},
        {
            **_worker_result(),
            "outputs": [{"output_name": "result"}],
        },
    ],
)
def test_worker_result_parser_rejects_malformed_payloads(payload: object) -> None:
    with pytest.raises(ValueError, match=r"."):
        execution._result_from_worker(payload, 0.1)


def test_worker_result_parser_reads_exception() -> None:
    result = execution._result_from_worker(
        _worker_result(
            status="exception",
            outputs=[],
            exception={"type_name": "KeyError", "message": "missing"},
        ),
        0.1,
    )

    assert result.exception == BehavioralExecutionException("KeyError", "missing")


def test_process_environment_and_group_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SECRET", "hidden")
    environment = execution._filtered_environment(tmp_path)
    assert "SECRET" not in environment
    assert environment["HOME"] == str(tmp_path)


def test_start_worker_posix_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    received: dict[str, object] = {}

    def fake_popen(*_args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        received.update(kwargs)
        return cast("subprocess.Popen[bytes]", _FakeProcess())

    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    execution._start_worker(("python",), tmp_path)

    assert received["start_new_session"] is True


def test_terminate_process_tree_posix_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess()
    calls: list[int] = []
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(
        os,
        "killpg",
        lambda pid, _sig: calls.append(pid),
        raising=False,
    )

    execution._terminate_process_tree(cast("subprocess.Popen[bytes]", process))

    assert calls == [123]


def test_terminate_process_tree_ignores_missing_posix_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _FakeProcess()
    monkeypatch.setattr(os, "name", "posix")

    def missing_group(_pid: int, _signal: object) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(os, "killpg", missing_group, raising=False)

    execution._terminate_process_tree(cast("subprocess.Popen[bytes]", process))


def test_terminate_process_tree_windows_path(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _FakeProcess()
    commands: list[object] = []

    def fake_run(command: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        return subprocess.CompletedProcess([], 0)

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(subprocess, "run", fake_run)

    execution._terminate_process_tree(cast("subprocess.Popen[bytes]", process))

    assert commands == [("taskkill", "/PID", "123", "/T", "/F")]


def test_terminate_process_tree_forces_direct_process_after_second_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SecondTimeoutProcess(_FakeProcess):
        def __init__(self) -> None:
            super().__init__()
            self.waits = 0

        def wait(self, timeout: float | None = None) -> int:
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("worker", timeout or 0.0)
            return 0

    process = SecondTimeoutProcess()
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(os, "killpg", lambda _pid, _sig: None, raising=False)

    execution._terminate_process_tree(cast("subprocess.Popen[bytes]", process))

    assert process.killed is True
