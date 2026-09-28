"""Isolated execution of statically validated behavioral functions."""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

from notebook_to_kedro.evaluation.behavioral import (
    ArrayBehaviorValue,
    BehaviorValue,
    ListBehaviorValue,
    ObjectBehaviorValue,
    ScalarBehaviorValue,
    TableBehaviorValue,
    behavior_value_from_dict,
    behavior_value_to_dict,
    validate_behavioral_case,
)
from notebook_to_kedro.generation.code import validate_node_code

if TYPE_CHECKING:
    from collections.abc import Callable

    from notebook_to_kedro.evaluation.behavioral import BehavioralCase
    from notebook_to_kedro.evaluation.node_code_corpus import NodeCodeCase
    from notebook_to_kedro.generation.code import NodeCodeRequest, NodeCodeResponse

BEHAVIORAL_EXECUTION_SCHEMA_VERSION = "1.0"
BehavioralExecutionStatus: TypeAlias = Literal[
    "success",
    "exception",
    "setup_failure",
    "timeout",
    "process_failure",
    "serialization_failure",
]
_WORKER_MODULE = "notebook_to_kedro.evaluation.behavioral_worker"
_KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)
_WORKER_RESULT_KEYS = {
    "schema_version",
    "case_id",
    "node_code_case_id",
    "status",
    "outputs",
    "exception",
    "stdout",
    "stderr",
    "stdout_truncated",
    "stderr_truncated",
    "diagnostic_message",
}
_ALLOWED_ENVIRONMENT = frozenset(
    {
        "COMSPEC",
        "LD_LIBRARY_PATH",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
    }
)


@dataclass(frozen=True, slots=True)
class BehavioralExecutionConfig:
    """Resource and output bounds for one behavioral subprocess."""

    timeout_seconds: float = 10.0
    max_request_bytes: int = 1_000_000
    max_result_bytes: int = 1_000_000
    max_capture_bytes: int = 16_384

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive finite number")
        for field_name in ("max_request_bytes", "max_result_bytes", "max_capture_bytes"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class BehavioralExecutionOutput:
    """One named value returned by the reviewed reference function."""

    output_name: str
    value: BehaviorValue

    def __post_init__(self) -> None:
        if not self.output_name.strip():
            raise ValueError("execution output name must not be empty")
        if not isinstance(
            self.value,
            (
                ScalarBehaviorValue,
                ListBehaviorValue,
                ObjectBehaviorValue,
                ArrayBehaviorValue,
                TableBehaviorValue,
            ),
        ):
            raise ValueError("execution output must contain a serializable behavior value")


@dataclass(frozen=True, slots=True)
class BehavioralExecutionException:
    """Exception raised while calling the reviewed reference function."""

    type_name: str
    message: str

    def __post_init__(self) -> None:
        if not self.type_name.strip():
            raise ValueError("execution exception type must not be empty")


@dataclass(frozen=True, slots=True)
class BehavioralExecutionResult:
    """Versioned observation from one isolated behavioral execution."""

    schema_version: str
    case_id: str
    node_code_case_id: str
    status: BehavioralExecutionStatus
    outputs: tuple[BehavioralExecutionOutput, ...]
    exception: BehavioralExecutionException | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    duration_seconds: float
    diagnostic_message: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != BEHAVIORAL_EXECUTION_SCHEMA_VERSION:
            raise ValueError(f"unsupported execution schema version: {self.schema_version!r}")
        if not self.case_id.strip() or not self.node_code_case_id.strip():
            raise ValueError("execution case IDs must not be empty")
        if self.status not in (
            "success",
            "exception",
            "setup_failure",
            "timeout",
            "process_failure",
            "serialization_failure",
        ):
            raise ValueError(f"unsupported execution status: {self.status!r}")
        if not math.isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise ValueError("duration_seconds must be a non-negative finite number")
        if any(not isinstance(output, BehavioralExecutionOutput) for output in self.outputs):
            raise ValueError("execution outputs must use BehavioralExecutionOutput values")
        if self.exception is not None and not isinstance(
            self.exception, BehavioralExecutionException
        ):
            raise ValueError("execution exception must use BehavioralExecutionException or null")
        if self.status == "success" and (not self.outputs or self.exception is not None):
            raise ValueError("successful execution requires outputs and no exception")
        if self.status == "exception" and (self.outputs or self.exception is None):
            raise ValueError("exception execution requires one exception and no outputs")
        if self.status not in ("success", "exception") and (
            self.outputs or self.exception is not None or not self.diagnostic_message
        ):
            raise ValueError("failed execution requires only a diagnostic message")


def execute_behavioral_reference(
    case: BehavioralCase,
    node_code_case: NodeCodeCase,
    *,
    config: BehavioralExecutionConfig | None = None,
) -> BehavioralExecutionResult:
    """Execute one approved reference in a fresh isolated Python subprocess."""
    return _execute_behavioral_response(
        case,
        node_code_case,
        node_code_case.reference_response,
        target="reference",
        config=config,
    )


def execute_behavioral_proposal(
    case: BehavioralCase,
    node_code_case: NodeCodeCase,
    proposal: NodeCodeResponse,
    *,
    allow_untrusted_code_execution: bool = False,
    config: BehavioralExecutionConfig | None = None,
) -> BehavioralExecutionResult:
    """Validate and execute one proposal in a fresh isolated Python subprocess."""
    if allow_untrusted_code_execution is not True:
        raise ValueError(
            "proposal execution requires allow_untrusted_code_execution=True because "
            "process isolation is not an OS sandbox"
        )
    return _execute_behavioral_response(
        case,
        node_code_case,
        proposal,
        target="proposal",
        config=config,
    )


def _execute_behavioral_response(
    case: BehavioralCase,
    node_code_case: NodeCodeCase,
    response: NodeCodeResponse,
    *,
    target: Literal["reference", "proposal"],
    config: BehavioralExecutionConfig | None,
) -> BehavioralExecutionResult:
    validate_behavioral_case(case, node_code_case)
    validate_node_code(node_code_case.request, response)
    settings = config or BehavioralExecutionConfig()
    request = _worker_request(case, node_code_case.request, response, settings)
    encoded_request = json.dumps(request, ensure_ascii=True, allow_nan=False).encode("utf-8")
    if len(encoded_request) > settings.max_request_bytes:
        raise ValueError("behavioral execution request exceeds max_request_bytes")

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="notebook-to-kedro-") as directory:
        working_directory = Path(directory)
        request_path = working_directory / "request.json"
        result_path = working_directory / "result.json"
        request_path.write_bytes(encoded_request)
        command = (
            sys.executable,
            "-I",
            "-m",
            _WORKER_MODULE,
            str(request_path),
            str(result_path),
            str(settings.max_result_bytes),
        )
        process = _start_worker(command, working_directory)
        try:
            return_code = process.wait(timeout=settings.timeout_seconds)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            return _failed_result(
                case,
                "timeout",
                time.perf_counter() - started,
                f"{target} execution exceeded {settings.timeout_seconds:g} seconds",
            )
        duration = time.perf_counter() - started
        if return_code != 0:
            return _failed_result(
                case,
                "process_failure",
                duration,
                f"{target} worker exited with code {return_code}",
            )
        try:
            if result_path.stat().st_size > settings.max_result_bytes:
                raise ValueError(f"{target} worker result exceeds max_result_bytes")
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            result = _result_from_worker(payload, duration)
            if (result.case_id, result.node_code_case_id) != (
                case.case_id,
                case.node_code_case_id,
            ):
                raise ValueError(f"{target} worker result identity does not match request")
            return result
        except (OSError, json.JSONDecodeError, ValueError) as error:
            return _failed_result(case, "process_failure", duration, str(error))


def behavioral_execution_result_to_dict(result: BehavioralExecutionResult) -> dict[str, object]:
    """Return one execution result as a canonical JSON-compatible dictionary."""
    return {
        "schema_version": result.schema_version,
        "case_id": result.case_id,
        "node_code_case_id": result.node_code_case_id,
        "status": result.status,
        "outputs": [
            {
                "output_name": output.output_name,
                "value": behavior_value_to_dict(output.value),
            }
            for output in result.outputs
        ],
        "exception": (
            None
            if result.exception is None
            else {
                "type_name": result.exception.type_name,
                "message": result.exception.message,
            }
        ),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "stdout_truncated": result.stdout_truncated,
        "stderr_truncated": result.stderr_truncated,
        "duration_seconds": result.duration_seconds,
        "diagnostic_message": result.diagnostic_message,
    }


def behavioral_execution_result_to_json(
    result: BehavioralExecutionResult, *, indent: int | None = 2
) -> str:
    """Serialize one execution result deterministically."""
    return (
        json.dumps(
            behavioral_execution_result_to_dict(result),
            indent=indent,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )


def _worker_request(
    case: BehavioralCase,
    request: NodeCodeRequest,
    response: NodeCodeResponse,
    config: BehavioralExecutionConfig,
) -> dict[str, object]:
    return {
        "schema_version": BEHAVIORAL_EXECUTION_SCHEMA_VERSION,
        "case_id": case.case_id,
        "node_code_case_id": case.node_code_case_id,
        "function_name": request.node_name,
        "function_code": response.function_code,
        "imports": list(response.imports),
        "inputs": [behavior_value_to_dict(item.value) for item in case.inputs],
        "output_names": list(request.outputs),
        "max_capture_bytes": config.max_capture_bytes,
    }


def _result_from_worker(payload: object, duration: float) -> BehavioralExecutionResult:
    data = _object(payload, "worker result")
    _exact_keys(data, _WORKER_RESULT_KEYS, "worker result")
    status = _status(data["status"])
    outputs = tuple(_execution_output(item) for item in _array(data["outputs"], "outputs"))
    exception_payload = data["exception"]
    exception = None if exception_payload is None else _execution_exception(exception_payload)
    diagnostic = data["diagnostic_message"]
    if diagnostic is not None and not isinstance(diagnostic, str):
        raise ValueError("worker diagnostic_message must be a string or null")
    return BehavioralExecutionResult(
        schema_version=_string(data["schema_version"], "schema_version"),
        case_id=_string(data["case_id"], "case_id"),
        node_code_case_id=_string(data["node_code_case_id"], "node_code_case_id"),
        status=status,
        outputs=outputs,
        exception=exception,
        stdout=_string(data["stdout"], "stdout"),
        stderr=_string(data["stderr"], "stderr"),
        stdout_truncated=_bool(data["stdout_truncated"], "stdout_truncated"),
        stderr_truncated=_bool(data["stderr_truncated"], "stderr_truncated"),
        duration_seconds=duration,
        diagnostic_message=diagnostic,
    )


def _failed_result(
    case: BehavioralCase,
    status: BehavioralExecutionStatus,
    duration: float,
    message: str,
) -> BehavioralExecutionResult:
    return BehavioralExecutionResult(
        schema_version=BEHAVIORAL_EXECUTION_SCHEMA_VERSION,
        case_id=case.case_id,
        node_code_case_id=case.node_code_case_id,
        status=status,
        outputs=(),
        exception=None,
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        duration_seconds=duration,
        diagnostic_message=message,
    )


def _filtered_environment(directory: Path) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if key in _ALLOWED_ENVIRONMENT}
    temporary = str(directory)
    environment.update(
        {
            "HOME": temporary,
            "USERPROFILE": temporary,
            "TEMP": temporary,
            "TMP": temporary,
        }
    )
    return environment


def _start_worker(command: tuple[str, ...], directory: Path) -> subprocess.Popen[bytes]:
    environment = _filtered_environment(directory)
    if _is_windows():
        creation_flags = cast("int", vars(subprocess)["CREATE_NEW_PROCESS_GROUP"])
        return subprocess.Popen(
            command,
            cwd=directory,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    return subprocess.Popen(
        command,
        cwd=directory,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if _is_windows():
        subprocess.run(
            ("taskkill", "/PID", str(process.pid), "/T", "/F"),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        with suppress(ProcessLookupError):
            kill_process_group = cast("Callable[[int, object], None]", vars(os)["killpg"])
            kill_process_group(process.pid, _KILL_SIGNAL)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _is_windows() -> bool:
    return sys.platform == "win32"


def _execution_output(payload: object) -> BehavioralExecutionOutput:
    data = _object(payload, "execution output")
    _exact_keys(data, {"output_name", "value"}, "execution output")
    return BehavioralExecutionOutput(
        _string(data["output_name"], "output_name"),
        behavior_value_from_dict(data["value"]),
    )


def _execution_exception(payload: object) -> BehavioralExecutionException:
    data = _object(payload, "execution exception")
    _exact_keys(data, {"type_name", "message"}, "execution exception")
    return BehavioralExecutionException(
        _string(data["type_name"], "type_name"),
        _string(data["message"], "message"),
    )


def _status(value: object) -> BehavioralExecutionStatus:
    if value not in (
        "success",
        "exception",
        "setup_failure",
        "timeout",
        "process_failure",
        "serialization_failure",
    ):
        raise ValueError(f"unsupported worker status: {value!r}")
    return value


def _object(payload: object, label: str) -> dict[str, object]:
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise ValueError(f"{label} must be an object with string keys")
    return cast("dict[str, object]", payload)


def _array(payload: object, label: str) -> list[object]:
    if not isinstance(payload, list):
        raise ValueError(f"{label} must be an array")
    return payload


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _exact_keys(data: dict[str, object], expected: set[str], label: str) -> None:
    actual = set(data)
    if actual != expected:
        raise ValueError(
            f"invalid {label} fields; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )
