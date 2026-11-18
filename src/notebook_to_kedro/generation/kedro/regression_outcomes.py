"""Explicit finite-JSON value or narrow built-in exception expectations."""

from __future__ import annotations

from typing import Any

from notebook_to_kedro.exceptions import WorkflowRegressionError

EXCEPTION_NAMES = frozenset(
    {
        "ValueError",
        "TypeError",
        "KeyError",
        "IndexError",
        "RuntimeError",
        "ZeroDivisionError",
        "AssertionError",
    }
)
MAX_EXCEPTION_MESSAGE_BYTES = 4096


def validate_outcome(case: dict[str, Any], *, pipeline: bool, exceptions: bool) -> None:
    """Require exactly one outcome; never import a class or infer a source failure."""
    if len({"expected", "raises"} & case.keys()) != 1:
        raise WorkflowRegressionError("Cases require exactly one of expected or raises")
    if "raises" not in case:
        return
    expectation = case["raises"]
    fields = {"type", "message", "node"} if pipeline else {"type", "message"}
    if (
        not exceptions
        or not isinstance(expectation, dict)
        or set(expectation) != fields
        or not isinstance(expectation["type"], str)
        or expectation["type"] not in EXCEPTION_NAMES
        or not isinstance(expectation["message"], str)
        or len(expectation["message"].encode("utf-8")) > MAX_EXCEPTION_MESSAGE_BYTES
        or (pipeline and (not isinstance(expectation["node"], str) or not expectation["node"]))
    ):
        raise WorkflowRegressionError(
            "Exception expectations require a supported exact built-in type, a UTF-8 message "
            "within 4 KiB and, for pipelines, the unprefixed failing node"
        )
