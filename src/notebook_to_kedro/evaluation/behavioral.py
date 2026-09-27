"""Versioned behavioral-comparison evidence contracts without code execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite, prod
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

if TYPE_CHECKING:
    from notebook_to_kedro.ir import JsonPrimitive

    from .node_code_corpus import NodeCodeCase

BEHAVIORAL_CASE_SCHEMA_VERSION = "1.0"
ComparatorKind: TypeAlias = Literal["exact", "numeric", "array", "table"]


@dataclass(frozen=True, slots=True)
class ScalarBehaviorValue:
    """One deterministic JSON scalar."""

    value: JsonPrimitive
    kind: Literal["scalar"] = "scalar"

    def __post_init__(self) -> None:
        _require_primitive(self.value, "scalar value")


@dataclass(frozen=True, slots=True)
class ListBehaviorValue:
    """An ordered immutable collection of serializable behavior values."""

    items: tuple[BehaviorValue, ...]
    kind: Literal["list"] = "list"

    def __post_init__(self) -> None:
        if any(not _is_behavior_value(item) for item in self.items):
            raise ValueError("list items must be serializable behavior values")


@dataclass(frozen=True, slots=True)
class ObjectBehaviorValue:
    """An ordered immutable string-key mapping."""

    entries: tuple[tuple[str, BehaviorValue], ...]
    kind: Literal["object"] = "object"

    def __post_init__(self) -> None:
        keys = tuple(key for key, _ in self.entries)
        if any(not key for key in keys):
            raise ValueError("object keys must not be empty")
        _require_unique(keys, "object keys")
        if any(not _is_behavior_value(value) for _, value in self.entries):
            raise ValueError("object entries must contain serializable behavior values")


@dataclass(frozen=True, slots=True)
class ArrayBehaviorValue:
    """A flattened typed array with an explicit shape."""

    dtype: str
    shape: tuple[int, ...]
    values: tuple[JsonPrimitive, ...]
    kind: Literal["array"] = "array"

    def __post_init__(self) -> None:
        _require_non_empty(self.dtype, "array dtype")
        if not self.shape or any(dimension < 0 for dimension in self.shape):
            raise ValueError("array shape must contain non-negative dimensions")
        if prod(self.shape) != len(self.values):
            raise ValueError("array shape must match flattened value count")
        for value in self.values:
            _require_primitive(value, "array value")


@dataclass(frozen=True, slots=True)
class TableBehaviorValue:
    """A typed rectangular table with optional explicit index values."""

    columns: tuple[str, ...]
    dtypes: tuple[str, ...]
    rows: tuple[tuple[JsonPrimitive, ...], ...]
    index: tuple[JsonPrimitive, ...] = ()
    kind: Literal["table"] = "table"

    def __post_init__(self) -> None:
        if not self.columns or any(not column for column in self.columns):
            raise ValueError("table columns must contain non-empty names")
        _require_unique(self.columns, "table columns")
        if len(self.dtypes) != len(self.columns) or any(not dtype for dtype in self.dtypes):
            raise ValueError("table dtypes must match columns and be non-empty")
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("table rows must match the column count")
        if self.index and len(self.index) != len(self.rows):
            raise ValueError("table index must be empty or match the row count")
        for value in (*self.index, *(value for row in self.rows for value in row)):
            _require_primitive(value, "table value")


BehaviorValue: TypeAlias = (
    ScalarBehaviorValue
    | ListBehaviorValue
    | ObjectBehaviorValue
    | ArrayBehaviorValue
    | TableBehaviorValue
)


@dataclass(frozen=True, slots=True)
class ComparisonSpec:
    """Comparator settings selected explicitly for one expected output."""

    kind: ComparatorKind
    absolute_tolerance: float | None = None
    relative_tolerance: float | None = None
    equal_nan: bool | None = None
    check_dtype: bool | None = None
    check_order: bool | None = None
    check_index: bool | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("exact", "numeric", "array", "table"):
            raise ValueError(f"unsupported comparator kind: {self.kind!r}")
        tolerance_fields = (self.absolute_tolerance, self.relative_tolerance)
        if any(
            value is not None and (not isfinite(value) or value < 0) for value in tolerance_fields
        ):
            raise ValueError("comparison tolerances must be non-negative finite numbers")
        expected_fields = {
            "exact": (False, False, False, False, False, False),
            "numeric": (True, True, True, False, False, False),
            "array": (True, True, True, True, False, False),
            "table": (True, True, True, True, True, True),
        }[self.kind]
        actual_fields = tuple(
            value is not None
            for value in (
                *tolerance_fields,
                self.equal_nan,
                self.check_dtype,
                self.check_order,
                self.check_index,
            )
        )
        if actual_fields != expected_fields:
            raise ValueError(f"comparator fields do not match kind {self.kind!r}")


@dataclass(frozen=True, slots=True)
class BehaviorInput:
    """One exact function argument and its serializable value."""

    argument_name: str
    value: BehaviorValue

    def __post_init__(self) -> None:
        _require_non_empty(self.argument_name, "behavior input argument name")
        if not _is_behavior_value(self.value):
            raise ValueError("behavior input must contain a serializable value")


@dataclass(frozen=True, slots=True)
class ExpectedBehaviorOutput:
    """One named output, reviewed value and comparison policy."""

    output_name: str
    value: BehaviorValue
    comparison: ComparisonSpec

    def __post_init__(self) -> None:
        _require_non_empty(self.output_name, "behavior output name")
        if not _is_behavior_value(self.value):
            raise ValueError("behavior output must contain a serializable value")
        if self.comparison.kind == "numeric" and not (
            isinstance(self.value, ScalarBehaviorValue)
            and isinstance(self.value.value, (int, float))
            and not isinstance(self.value.value, bool)
        ):
            raise ValueError("numeric comparison requires a numeric scalar value")
        if self.comparison.kind == "array" and not isinstance(self.value, ArrayBehaviorValue):
            raise ValueError("array comparison requires an array value")
        if self.comparison.kind == "table" and not isinstance(self.value, TableBehaviorValue):
            raise ValueError("table comparison requires a table value")
        if self.comparison.kind == "exact" and isinstance(
            self.value, (ArrayBehaviorValue, TableBehaviorValue)
        ):
            raise ValueError("array and table values require their dedicated comparator")


@dataclass(frozen=True, slots=True)
class ExpectedBehaviorException:
    """An exception type and optional stable message fragment expected from execution."""

    type_name: str
    message_contains: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.type_name, "expected exception type")
        if self.message_contains is not None:
            _require_non_empty(self.message_contains, "expected exception message fragment")


@dataclass(frozen=True, slots=True)
class BehavioralCase:
    """Reviewed runtime evidence linked to one independent node-code case."""

    schema_version: str
    case_id: str
    node_code_case_id: str
    review_status: str
    inputs: tuple[BehaviorInput, ...]
    expected_outputs: tuple[ExpectedBehaviorOutput, ...] = ()
    expected_exception: ExpectedBehaviorException | None = None

    def __post_init__(self) -> None:
        if self.schema_version != BEHAVIORAL_CASE_SCHEMA_VERSION:
            raise ValueError(f"unsupported behavioral case schema version: {self.schema_version!r}")
        _require_non_empty(self.case_id, "behavioral case id")
        _require_non_empty(self.node_code_case_id, "node code case id")
        if self.review_status != "approved":
            raise ValueError("behavioral cases must be explicitly approved")
        if any(not isinstance(item, BehaviorInput) for item in self.inputs):
            raise ValueError("behavioral inputs must use BehaviorInput values")
        if any(not isinstance(item, ExpectedBehaviorOutput) for item in self.expected_outputs):
            raise ValueError("behavioral outputs must use ExpectedBehaviorOutput values")
        if self.expected_exception is not None and not isinstance(
            self.expected_exception, ExpectedBehaviorException
        ):
            raise ValueError("expected_exception must use ExpectedBehaviorException or null")
        _require_unique(tuple(item.argument_name for item in self.inputs), "behavior input names")
        _require_unique(
            tuple(item.output_name for item in self.expected_outputs), "behavior output names"
        )
        if self.expected_exception is not None and self.expected_outputs:
            raise ValueError("behavioral case cannot expect both outputs and an exception")


def validate_behavioral_case(case: BehavioralCase, node_code_case: NodeCodeCase) -> None:
    """Check reviewed runtime evidence against the linked node-code interface."""
    if case.node_code_case_id != node_code_case.case_id:
        raise ValueError("behavioral case references the wrong node code case")
    actual_arguments = tuple(item.argument_name for item in case.inputs)
    if actual_arguments != node_code_case.request.arguments:
        raise ValueError("behavior input names and order must match the node arguments")
    if case.expected_exception is None:
        actual_outputs = tuple(item.output_name for item in case.expected_outputs)
        if actual_outputs != node_code_case.request.outputs:
            raise ValueError("behavior output names and order must match the node outputs")


def validate_behavioral_corpus(
    cases: tuple[BehavioralCase, ...], node_code_cases: tuple[NodeCodeCase, ...]
) -> None:
    """Validate unique reviewed cases and all links without executing functions."""
    if not cases:
        raise ValueError("behavioral corpus requires at least one case")
    _require_unique(tuple(case.case_id for case in cases), "behavioral case IDs")
    nodes_by_id = {case.case_id: case for case in node_code_cases}
    if len(nodes_by_id) != len(node_code_cases):
        raise ValueError("node code case IDs must be unique")
    for case in cases:
        node_case = nodes_by_id.get(case.node_code_case_id)
        if node_case is None:
            raise ValueError(f"unknown node code case: {case.node_code_case_id}")
        validate_behavioral_case(case, node_case)


def behavioral_case_to_dict(case: BehavioralCase) -> dict[str, object]:
    """Return a canonical JSON-compatible behavior case dictionary."""
    return {
        "schema_version": case.schema_version,
        "case_id": case.case_id,
        "node_code_case_id": case.node_code_case_id,
        "review_status": case.review_status,
        "inputs": [
            {"argument_name": item.argument_name, "value": _value_to_dict(item.value)}
            for item in case.inputs
        ],
        "expected_outputs": [
            {
                "output_name": item.output_name,
                "value": _value_to_dict(item.value),
                "comparison": _comparison_to_dict(item.comparison),
            }
            for item in case.expected_outputs
        ],
        "expected_exception": (
            None
            if case.expected_exception is None
            else {
                "type_name": case.expected_exception.type_name,
                "message_contains": case.expected_exception.message_contains,
            }
        ),
    }


def behavioral_case_to_json(case: BehavioralCase, *, indent: int | None = 2) -> str:
    """Serialize one behavior case deterministically and reject non-finite JSON."""
    return (
        json.dumps(behavioral_case_to_dict(case), indent=indent, ensure_ascii=True, allow_nan=False)
        + "\n"
    )


def behavioral_case_from_dict(payload: object) -> BehavioralCase:
    """Strictly reconstruct a behavior case from decoded JSON."""
    data = _object(payload, "behavioral case")
    _exact_keys(
        data,
        {
            "schema_version",
            "case_id",
            "node_code_case_id",
            "review_status",
            "inputs",
            "expected_outputs",
            "expected_exception",
        },
        "behavioral case",
    )
    review_status = _string(data["review_status"], "review_status")
    if review_status != "approved":
        raise ValueError("review_status must be 'approved'")
    inputs = _array(data["inputs"], "inputs")
    outputs = _array(data["expected_outputs"], "expected_outputs")
    exception_value = data["expected_exception"]
    return BehavioralCase(
        schema_version=_string(data["schema_version"], "schema_version"),
        case_id=_string(data["case_id"], "case_id"),
        node_code_case_id=_string(data["node_code_case_id"], "node_code_case_id"),
        review_status="approved",
        inputs=tuple(_input(item) for item in inputs),
        expected_outputs=tuple(_output(item) for item in outputs),
        expected_exception=(
            None if exception_value is None else _expected_exception(exception_value)
        ),
    )


def behavioral_case_from_json(payload: str) -> BehavioralCase:
    """Strictly reconstruct a behavior case from JSON text."""
    try:
        decoded = json.loads(
            payload,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid behavioral case JSON: {error}") from error
    return behavioral_case_from_dict(decoded)


def load_behavioral_case(path: str | Path) -> BehavioralCase:
    """Load one behavior case from disk."""
    case_path = Path(path)
    try:
        payload = case_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read behavioral case {case_path}: {error}") from error
    return behavioral_case_from_json(payload)


def load_behavioral_corpus(directory: str | Path) -> tuple[BehavioralCase, ...]:
    """Load behavior cases in deterministic filename order."""
    corpus_path = Path(directory)
    paths = tuple(sorted(corpus_path.glob("*.json")))
    if not paths:
        raise ValueError(f"behavioral corpus contains no JSON cases: {corpus_path}")
    cases = tuple(load_behavioral_case(path) for path in paths)
    _require_unique(tuple(case.case_id for case in cases), "behavioral case IDs")
    return cases


def _value_to_dict(value: BehaviorValue) -> dict[str, object]:
    if isinstance(value, ScalarBehaviorValue):
        return {"kind": value.kind, "value": value.value}
    if isinstance(value, ListBehaviorValue):
        return {"kind": value.kind, "items": [_value_to_dict(item) for item in value.items]}
    if isinstance(value, ObjectBehaviorValue):
        return {
            "kind": value.kind,
            "entries": [{"key": key, "value": _value_to_dict(item)} for key, item in value.entries],
        }
    if isinstance(value, ArrayBehaviorValue):
        return {
            "kind": value.kind,
            "dtype": value.dtype,
            "shape": list(value.shape),
            "values": list(value.values),
        }
    return {
        "kind": value.kind,
        "columns": list(value.columns),
        "dtypes": list(value.dtypes),
        "rows": [list(row) for row in value.rows],
        "index": list(value.index),
    }


def _value(payload: object) -> BehaviorValue:
    data = _object(payload, "behavior value")
    kind = _string(data.get("kind"), "behavior value kind")
    if kind == "scalar":
        _exact_keys(data, {"kind", "value"}, "scalar behavior value")
        value = data["value"]
        _require_primitive(value, "scalar value")
        return ScalarBehaviorValue(cast("JsonPrimitive", value))
    if kind == "list":
        _exact_keys(data, {"kind", "items"}, "list behavior value")
        return ListBehaviorValue(tuple(_value(item) for item in _array(data["items"], "items")))
    if kind == "object":
        _exact_keys(data, {"kind", "entries"}, "object behavior value")
        entries = []
        for payload_entry in _array(data["entries"], "entries"):
            entry = _object(payload_entry, "object entry")
            _exact_keys(entry, {"key", "value"}, "object entry")
            entries.append((_string(entry["key"], "object key"), _value(entry["value"])))
        return ObjectBehaviorValue(tuple(entries))
    if kind == "array":
        _exact_keys(data, {"kind", "dtype", "shape", "values"}, "array behavior value")
        shape_values = _array(data["shape"], "shape")
        if not all(isinstance(item, int) and not isinstance(item, bool) for item in shape_values):
            raise ValueError("array shape must contain integers")
        values = _primitives(data["values"], "array values")
        return ArrayBehaviorValue(
            dtype=_string(data["dtype"], "array dtype"),
            shape=tuple(cast("list[int]", shape_values)),
            values=values,
        )
    if kind == "table":
        _exact_keys(data, {"kind", "columns", "dtypes", "rows", "index"}, "table behavior value")
        rows = tuple(_primitives(row, "table row") for row in _array(data["rows"], "rows"))
        return TableBehaviorValue(
            columns=_strings(data["columns"], "columns"),
            dtypes=_strings(data["dtypes"], "dtypes"),
            rows=rows,
            index=_primitives(data["index"], "index"),
        )
    raise ValueError(f"unsupported behavior value kind: {kind!r}")


def _comparison_to_dict(comparison: ComparisonSpec) -> dict[str, object]:
    return {
        "kind": comparison.kind,
        "absolute_tolerance": comparison.absolute_tolerance,
        "relative_tolerance": comparison.relative_tolerance,
        "equal_nan": comparison.equal_nan,
        "check_dtype": comparison.check_dtype,
        "check_order": comparison.check_order,
        "check_index": comparison.check_index,
    }


def _comparison(payload: object) -> ComparisonSpec:
    data = _object(payload, "comparison")
    _exact_keys(
        data,
        {
            "kind",
            "absolute_tolerance",
            "relative_tolerance",
            "equal_nan",
            "check_dtype",
            "check_order",
            "check_index",
        },
        "comparison",
    )
    kind = _string(data["kind"], "comparison kind")
    if kind not in ("exact", "numeric", "array", "table"):
        raise ValueError(f"unsupported comparator kind: {kind!r}")
    return ComparisonSpec(
        kind=cast("ComparatorKind", kind),
        absolute_tolerance=_optional_float(data["absolute_tolerance"], "absolute_tolerance"),
        relative_tolerance=_optional_float(data["relative_tolerance"], "relative_tolerance"),
        equal_nan=_optional_bool(data["equal_nan"], "equal_nan"),
        check_dtype=_optional_bool(data["check_dtype"], "check_dtype"),
        check_order=_optional_bool(data["check_order"], "check_order"),
        check_index=_optional_bool(data["check_index"], "check_index"),
    )


def _input(payload: object) -> BehaviorInput:
    data = _object(payload, "behavior input")
    _exact_keys(data, {"argument_name", "value"}, "behavior input")
    return BehaviorInput(_string(data["argument_name"], "argument_name"), _value(data["value"]))


def _output(payload: object) -> ExpectedBehaviorOutput:
    data = _object(payload, "expected behavior output")
    _exact_keys(data, {"output_name", "value", "comparison"}, "expected behavior output")
    return ExpectedBehaviorOutput(
        _string(data["output_name"], "output_name"),
        _value(data["value"]),
        _comparison(data["comparison"]),
    )


def _expected_exception(payload: object) -> ExpectedBehaviorException:
    data = _object(payload, "expected behavior exception")
    _exact_keys(data, {"type_name", "message_contains"}, "expected behavior exception")
    message = data["message_contains"]
    if message is not None and not isinstance(message, str):
        raise ValueError("message_contains must be a string or null")
    return ExpectedBehaviorException(_string(data["type_name"], "type_name"), message)


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
    if not all(isinstance(item, str) for item in values):
        raise ValueError(f"{label} must contain strings")
    return tuple(cast("list[str]", values))


def _primitives(payload: object, label: str) -> tuple[JsonPrimitive, ...]:
    values = _array(payload, label)
    for value in values:
        _require_primitive(value, label)
    return tuple(cast("list[JsonPrimitive]", values))


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _optional_float(value: object, label: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be a number or null")
    return float(value)


def _optional_bool(value: object, label: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean or null")
    return value


def _exact_keys(data: dict[str, object], expected: set[str], label: str) -> None:
    actual = set(data)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(f"invalid {label} fields; missing={missing}, unexpected={unexpected}")


def _require_primitive(value: object, label: str) -> None:
    if not isinstance(value, (str, int, float, bool, type(None))):
        raise ValueError(f"{label} must be a JSON scalar")
    if isinstance(value, float) and not isfinite(value):
        raise ValueError(f"{label} must be finite")


def _is_behavior_value(value: object) -> bool:
    return isinstance(
        value,
        (
            ScalarBehaviorValue,
            ListBehaviorValue,
            ObjectBehaviorValue,
            ArrayBehaviorValue,
            TableBehaviorValue,
        ),
    )


def _require_non_empty(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is unsupported: {value}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result
