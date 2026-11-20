"""Closed, finite representations for supplied procedural test inputs and observations."""

from __future__ import annotations

from typing import Any

from notebook_to_kedro.exceptions import WorkflowRegressionError

NUMERIC_DTYPES = frozenset(
    {
        "bool",
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "float16",
        "float32",
        "float64",
    }
)
TABLE_DTYPES = NUMERIC_DTYPES | {"object", "string", "str", "Int64", "Float64", "boolean"}
_FIELDS = {
    "json": {"kind", "value"},
    "csv": {"kind", "fixture"},
    "number": {"kind", "value", "abs_tol", "rel_tol"},
    "array": {"kind", "dtype", "data"},
    "frame": {"kind", "columns", "index", "index_name", "column_name", "dtypes", "data"},
    "series": {"kind", "name", "index", "index_name", "dtype", "data"},
}


def _number(value: object) -> bool:
    return type(value) in (int, float)


def _index(value: object) -> bool:
    return isinstance(value, list) and all(
        type(item) in (str, int, float, bool, type(None)) for item in value
    )


def _name(value: object) -> bool:
    return value is None or isinstance(value, str)


def _dtype(value: object, allowed: frozenset[str]) -> bool:
    return isinstance(value, str) and value in allowed


def _numeric_shape(value: object) -> tuple[int, ...]:
    if isinstance(value, list):
        shapes = {_numeric_shape(item) for item in value}
        if len(shapes) > 1:
            raise WorkflowRegressionError("Array expectations require rectangular numeric JSON")
        return (len(value), *next(iter(shapes), ()))
    if not (_number(value) or isinstance(value, bool)):
        raise WorkflowRegressionError("Array expectations require numeric or boolean leaves")
    return ()


def validate_descriptor(value: object, fixtures: set[str], *, input_value: bool) -> None:
    """Validate supplied representations without importing pandas/numpy or running source."""
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("kind"), str)
        or value["kind"] not in _FIELDS
        or set(value) != _FIELDS[value["kind"]]
    ):
        raise WorkflowRegressionError("Test values require a known kind and its exact fields")
    kind = value["kind"]
    if kind == "json":
        return
    if kind == "csv":
        if (
            not input_value
            or not isinstance(value["fixture"], str)
            or value["fixture"] not in fixtures
        ):
            raise WorkflowRegressionError("CSV inputs must reference a declared fixture")
    elif kind == "number":
        if (
            input_value
            or not all(_number(value[key]) for key in ("value", "abs_tol", "rel_tol"))
            or (value["abs_tol"] < 0 or value["rel_tol"] < 0)
        ):
            raise WorkflowRegressionError(
                "Number observations require nonnegative explicit tolerances"
            )
    elif kind == "array":
        if not _dtype(value["dtype"], NUMERIC_DTYPES) or not isinstance(value["data"], list):
            raise WorkflowRegressionError("Array values require a supported numeric dtype and list")
        _numeric_shape(value["data"])
    elif kind == "frame":
        _validate_frame(value)
    else:
        _validate_series(value)


def _validate_frame(value: dict[str, Any]) -> None:
    columns, data, dtypes = value["columns"], value["data"], value["dtypes"]
    if (
        not isinstance(columns, list)
        or any(not isinstance(name, str) for name in columns)
        or len(set(columns)) != len(columns)
        or not isinstance(data, list)
        or any(not isinstance(row, list) or len(row) != len(columns) for row in data)
        or not isinstance(dtypes, list)
        or len(dtypes) != len(columns)
        or any(not _dtype(dtype, TABLE_DTYPES) for dtype in dtypes)
        or not _index(value["index"])
        or len(value["index"]) != len(data)
        or not _name(value["index_name"])
        or not _name(value["column_name"])
    ):
        raise WorkflowRegressionError(
            "Frame values require matching columns, rows, index and dtypes"
        )


def _validate_series(value: dict[str, Any]) -> None:
    if (
        not _name(value["name"])
        or not _name(value["index_name"])
        or not _index(value["index"])
        or not isinstance(value["data"], list)
        or len(value["data"]) != len(value["index"])
        or not _dtype(value["dtype"], TABLE_DTYPES)
    ):
        raise WorkflowRegressionError(
            "Series values require matching data/index and a supported dtype"
        )
