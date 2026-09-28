"""Private subprocess worker for validated behavioral function execution."""

from __future__ import annotations

import importlib
import io
import json
import math
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, cast

from notebook_to_kedro.evaluation.behavioral import (
    ArrayBehaviorValue,
    BehaviorValue,
    ListBehaviorValue,
    ObjectBehaviorValue,
    ScalarBehaviorValue,
    TableBehaviorValue,
    behavior_value_from_dict,
    behavior_value_to_dict,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from notebook_to_kedro.ir import JsonPrimitive

_WORKER_SCHEMA_VERSION = "1.0"
_ARGUMENT_COUNT = 3


class _BoundedTextCapture(io.TextIOBase):
    """Capture UTF-8 text up to a byte limit without retaining the remainder."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._chunks: list[bytes] = []
        self._size = 0
        self.truncated = False

    def writable(self) -> bool:
        """Return whether callers may write text."""
        return True

    def write(self, value: str) -> int:
        """Retain at most the remaining UTF-8 bytes and report the input length."""
        if not isinstance(value, str):
            raise TypeError("captured output must be text")
        encoded = value.encode("utf-8")
        remaining = self._limit - self._size
        if len(encoded) > remaining:
            self.truncated = True
        if remaining > 0:
            chunk = encoded[:remaining]
            while chunk:
                try:
                    chunk.decode("utf-8")
                except UnicodeDecodeError:
                    chunk = chunk[:-1]
                else:
                    break
            self._chunks.append(chunk)
            self._size += len(chunk)
        return len(value)

    def getvalue(self) -> str:
        """Return retained text."""
        return b"".join(self._chunks).decode("utf-8")


def run_worker_payload(payload: object) -> dict[str, object]:
    """Execute one validated worker payload and return a JSON-compatible result."""
    data = _object(payload, "worker request")
    _exact_keys(
        data,
        {
            "schema_version",
            "case_id",
            "node_code_case_id",
            "function_name",
            "function_code",
            "imports",
            "inputs",
            "output_names",
            "max_capture_bytes",
        },
        "worker request",
    )
    if _string(data["schema_version"], "schema_version") != _WORKER_SCHEMA_VERSION:
        raise ValueError("unsupported worker schema version")
    case_id = _non_empty_string(data["case_id"], "case_id")
    node_code_case_id = _non_empty_string(data["node_code_case_id"], "node_code_case_id")
    function_name = _non_empty_string(data["function_name"], "function_name")
    function_code = _non_empty_string(data["function_code"], "function_code")
    imports = _strings(data["imports"], "imports")
    output_names = _strings(data["output_names"], "output_names")
    max_capture_bytes = _positive_int(data["max_capture_bytes"], "max_capture_bytes")
    input_payloads = _array(data["inputs"], "inputs")
    stdout = _BoundedTextCapture(max_capture_bytes)
    stderr = _BoundedTextCapture(max_capture_bytes)
    result = _base_result(case_id, node_code_case_id)

    try:
        inputs = tuple(_materialize(behavior_value_from_dict(item)) for item in input_payloads)
    except Exception as error:
        return _failure_result(result, "setup_failure", error, stdout, stderr)

    namespace: dict[str, object] = {"__name__": "__behavioral_candidate__"}
    source = "\n".join((*imports, function_code))
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(compile(source, "<behavioral-candidate>", "exec"), namespace)
        function = namespace.get(function_name)
        if not callable(function):
            raise ValueError(f"behavioral function is not callable: {function_name}")
    except BaseException as error:
        return _failure_result(result, "setup_failure", error, stdout, stderr)

    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returned = function(*inputs)
    except BaseException as error:
        result.update(
            status="exception",
            exception=_exception_dict(error),
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
            stdout_truncated=stdout.truncated,
            stderr_truncated=stderr.truncated,
        )
        return result

    try:
        values = _split_outputs(returned, output_names)
        result["outputs"] = [
            {
                "output_name": name,
                "value": behavior_value_to_dict(_serialize(value)),
            }
            for name, value in zip(output_names, values, strict=True)
        ]
    except Exception as error:
        return _failure_result(result, "serialization_failure", error, stdout, stderr)
    result.update(
        status="success",
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
        stdout_truncated=stdout.truncated,
        stderr_truncated=stderr.truncated,
    )
    return result


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one request file and write one bounded result file."""
    args = tuple(sys.argv[1:] if arguments is None else arguments)
    if len(args) != _ARGUMENT_COUNT:
        return 2
    request_path = Path(args[0])
    result_path = Path(args[1])
    try:
        max_result_bytes = int(args[2])
        if max_result_bytes <= 0:
            return 2
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        encoded = json.dumps(
            run_worker_payload(payload), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
        if len(encoded) > max_result_bytes:
            fallback = _oversized_result(payload)
            encoded = json.dumps(fallback, ensure_ascii=True, allow_nan=False).encode("utf-8")
            if len(encoded) > max_result_bytes:
                return 3
        result_path.write_bytes(encoded)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return 3
    return 0


def _base_result(case_id: str, node_code_case_id: str) -> dict[str, object]:
    return {
        "schema_version": _WORKER_SCHEMA_VERSION,
        "case_id": case_id,
        "node_code_case_id": node_code_case_id,
        "status": "process_failure",
        "outputs": [],
        "exception": None,
        "stdout": "",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "diagnostic_message": None,
    }


def _failure_result(
    result: dict[str, object],
    status: str,
    error: BaseException,
    stdout: _BoundedTextCapture,
    stderr: _BoundedTextCapture,
) -> dict[str, object]:
    result.update(
        status=status,
        diagnostic_message=f"{type(error).__name__}: {error}",
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
        stdout_truncated=stdout.truncated,
        stderr_truncated=stderr.truncated,
    )
    return result


def _oversized_result(payload: object) -> dict[str, object]:
    data = _object(payload, "worker request")
    result = _base_result(
        _non_empty_string(data.get("case_id"), "case_id"),
        _non_empty_string(data.get("node_code_case_id"), "node_code_case_id"),
    )
    result.update(
        status="serialization_failure",
        diagnostic_message="serialized worker result exceeds max_result_bytes",
    )
    return result


def _materialize(value: BehaviorValue) -> object:
    if isinstance(value, ScalarBehaviorValue):
        return value.value
    if isinstance(value, ListBehaviorValue):
        return [_materialize(item) for item in value.items]
    if isinstance(value, ObjectBehaviorValue):
        return {key: _materialize(item) for key, item in value.entries}
    if isinstance(value, ArrayBehaviorValue):
        np = importlib.import_module("numpy")
        return np.asarray(value.values, dtype=value.dtype).reshape(value.shape)
    pd = importlib.import_module("pandas")
    frame = pd.DataFrame(value.rows, columns=value.columns)
    for column, dtype in zip(value.columns, value.dtypes, strict=True):
        frame[column] = frame[column].astype(dtype)
    if value.index:
        frame.index = pd.Index(value.index)
    return frame


def _serialize(value: object) -> BehaviorValue:
    primitive = _primitive(value)
    if primitive is not _UNSUPPORTED:
        return ScalarBehaviorValue(cast("JsonPrimitive", primitive))
    if isinstance(value, (list, tuple)):
        return ListBehaviorValue(tuple(_serialize(item) for item in value))
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("runtime object keys must be strings")
        return ObjectBehaviorValue(tuple((key, _serialize(item)) for key, item in value.items()))

    np = importlib.import_module("numpy")
    pd = importlib.import_module("pandas")

    if isinstance(value, np.ndarray):
        return ArrayBehaviorValue(
            dtype=str(value.dtype),
            shape=tuple(value.shape),
            values=tuple(_runtime_primitive(item) for item in value.reshape(-1).tolist()),
        )
    if isinstance(value, pd.DataFrame):
        if not all(isinstance(column, str) for column in value.columns):
            raise ValueError("runtime table columns must be strings")
        return TableBehaviorValue(
            columns=tuple(cast("Sequence[str]", value.columns.tolist())),
            dtypes=tuple(str(dtype) for dtype in value.dtypes),
            rows=tuple(
                tuple(_runtime_primitive(item) for item in row)
                for row in value.to_numpy(dtype=object).tolist()
            ),
            index=tuple(_runtime_primitive(item) for item in value.index.tolist()),
        )
    raise ValueError(f"unsupported runtime output type: {type(value).__name__}")


_UNSUPPORTED = object()


def _primitive(value: object) -> JsonPrimitive | object:
    if value is None or isinstance(value, (str, bool, int)):
        return cast("JsonPrimitive", value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("runtime scalar values must be finite")
        return value
    return _UNSUPPORTED


def _runtime_primitive(value: object) -> JsonPrimitive:
    primitive = _primitive(value)
    if primitive is _UNSUPPORTED and hasattr(value, "item"):
        primitive = _primitive(value.item())
    if primitive is _UNSUPPORTED:
        raise ValueError(f"unsupported runtime scalar type: {type(value).__name__}")
    return cast("JsonPrimitive", primitive)


def _split_outputs(value: object, output_names: tuple[str, ...]) -> tuple[object, ...]:
    if len(output_names) == 1:
        return (value,)
    if not isinstance(value, tuple) or len(value) != len(output_names):
        raise ValueError("multiple node outputs must be returned as a matching tuple")
    return value


def _exception_dict(error: BaseException) -> dict[str, str]:
    return {"type_name": type(error).__name__, "message": str(error)}


def _object(payload: object, label: str) -> dict[str, object]:
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise ValueError(f"{label} must be an object with string keys")
    return cast("dict[str, object]", payload)


def _array(payload: object, label: str) -> list[object]:
    if not isinstance(payload, list):
        raise ValueError(f"{label} must be an array")
    return payload


def _strings(payload: object, label: str) -> tuple[str, ...]:
    values = _array(payload, label)
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError(f"{label} must contain non-empty strings")
    return tuple(cast("list[str]", values))


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _non_empty_string(value: object, label: str) -> str:
    result = _string(value, label)
    if not result.strip():
        raise ValueError(f"{label} must not be empty")
    return result


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _exact_keys(data: dict[str, object], expected: set[str], label: str) -> None:
    actual = set(data)
    if actual != expected:
        raise ValueError(
            f"invalid {label} fields; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
