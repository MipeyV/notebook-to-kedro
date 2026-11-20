"""Closed representations reject ambiguous, nonrectangular and undeclared test values."""

from __future__ import annotations

from typing import Any

import pytest

from notebook_to_kedro.exceptions import WorkflowRegressionError
from notebook_to_kedro.generation.kedro.notebook_regression_values import validate_descriptor

FRAME = {
    "kind": "frame",
    "columns": ["x"],
    "index": [0],
    "index_name": None,
    "column_name": None,
    "dtypes": ["int64"],
    "data": [[1]],
}
SERIES = {
    "kind": "series",
    "name": "y",
    "index": [0],
    "index_name": "row",
    "dtype": "int64",
    "data": [1],
}


@pytest.mark.parametrize(
    ("value", "inputs"),
    [
        ({"kind": "json", "value": {"x": [1, True, None]}}, True),
        ({"kind": "json", "value": [1, 2]}, False),
        ({"kind": "csv", "fixture": "training"}, True),
        ({"kind": "number", "value": 1.0, "abs_tol": 0.1, "rel_tol": 0.0}, False),
        ({"kind": "array", "dtype": "float64", "data": [[1.0], [2.0]]}, True),
        ({"kind": "array", "dtype": "bool", "data": [True]}, False),
        ({"kind": "array", "dtype": "int64", "data": []}, False),
        (FRAME, True),
        (SERIES, False),
    ],
)
def test_supported_descriptors(value: Any, *, inputs: bool) -> None:
    validate_descriptor(value, {"training"}, input_value=inputs)


@pytest.mark.parametrize(
    ("value", "inputs"),
    [
        (None, True),
        ({"kind": []}, True),
        ({"kind": "pickle", "value": "x"}, False),
        ({"kind": "json"}, False),
        ({"kind": "csv", "fixture": "training"}, False),
        ({"kind": "csv", "fixture": []}, True),
        ({"kind": "csv", "fixture": "other"}, True),
        ({"kind": "number", "value": 1, "abs_tol": 0, "rel_tol": 0}, True),
        ({"kind": "number", "value": True, "abs_tol": 0, "rel_tol": 0}, False),
        ({"kind": "number", "value": 1, "abs_tol": -1, "rel_tol": 0}, False),
        ({"kind": "number", "value": 1, "abs_tol": 0, "rel_tol": -1}, False),
        ({"kind": "array", "dtype": [], "data": []}, True),
        ({"kind": "array", "dtype": "object", "data": []}, True),
        ({"kind": "array", "dtype": "int64", "data": {}}, True),
        ({"kind": "array", "dtype": "int64", "data": [[1], []]}, True),
        ({"kind": "array", "dtype": "int64", "data": ["x"]}, True),
    ],
)
def test_invalid_descriptors(value: Any, *, inputs: bool) -> None:
    with pytest.raises(WorkflowRegressionError):
        validate_descriptor(value, {"training"}, input_value=inputs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("columns", None),
        ("columns", [1]),
        ("columns", ["x", "x"]),
        ("data", {}),
        ("data", [1]),
        ("data", [[1, 2]]),
        ("dtypes", {}),
        ("dtypes", []),
        ("dtypes", ["date"]),
        ("index", {}),
        ("index", [[]]),
        ("index", []),
        ("index_name", 1),
        ("column_name", []),
    ],
)
def test_invalid_frames(field: str, value: Any) -> None:
    with pytest.raises(WorkflowRegressionError):
        validate_descriptor({**FRAME, field: value}, set(), input_value=True)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", []),
        ("index_name", {}),
        ("index", None),
        ("index", [{}]),
        ("data", {}),
        ("data", []),
        ("dtype", None),
        ("dtype", "datetime64[ns]"),
    ],
)
def test_invalid_series(field: str, value: Any) -> None:
    with pytest.raises(WorkflowRegressionError):
        validate_descriptor({**SERIES, field: value}, set(), input_value=False)
