"""Closed supplied prediction probes for freshly reloaded notebook model artifacts."""

from __future__ import annotations

import re
from typing import Any

from notebook_to_kedro.exceptions import WorkflowRegressionError
from notebook_to_kedro.generation.kedro.notebook_regression_values import (
    _numeric_shape,
    validate_descriptor,
)
from notebook_to_kedro.generation.kedro.regression_contract import MAX_SCENARIOS

_FIELDS = {"id", "scenario", "method", "input", "expected", "abs_tol", "rel_tol"}


def validate_model_checks(data: dict[str, Any]) -> set[str]:
    """Validate finite declarations only; do not import models or derive predictions."""
    checks = data.get("model_checks", [])
    if not isinstance(checks, list) or len(checks) > MAX_SCENARIOS:
        raise WorkflowRegressionError("model_checks must be a bounded list")
    scenarios = {case["id"]: case for case in data["scenarios"]}
    fixtures, used, seen = set(data["fixtures"]), set(), set()
    for check in checks:
        if (
            not isinstance(check, dict)
            or set(check) != _FIELDS
            or not isinstance(check["id"], str)
            or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", check["id"]) is None
            or check["id"] in seen
        ):
            raise WorkflowRegressionError("Model checks require exact fields and unique IDs")
        seen.add(check["id"])
        scenario = check["scenario"]
        if (
            not isinstance(scenario, str)
            or scenario not in scenarios
            or "expected" not in scenarios[scenario]
        ):
            raise WorkflowRegressionError(
                "Model checks require an existing positive pipeline scenario"
            )
        if check["method"] not in ("predict", "predict_proba"):
            raise WorkflowRegressionError("Model checks support predict or predict_proba only")
        for name in ("abs_tol", "rel_tol"):
            if type(check[name]) not in (int, float) or check[name] < 0:
                raise WorkflowRegressionError(
                    "Model checks require explicit nonnegative tolerances"
                )
        validate_descriptor(check["input"], fixtures, input_value=True)
        validate_descriptor(check["expected"], fixtures, input_value=False)
        if (
            check["input"]["kind"] not in {"array", "frame", "csv"}
            or check["expected"]["kind"] != "array"
        ):
            raise WorkflowRegressionError(
                "Model checks require array/frame/CSV probes and numeric array expectations"
            )
        shape = _numeric_shape(check["expected"]["data"])
        if len(shape) not in (1, 2) or 0 in shape:
            raise WorkflowRegressionError(
                "Model checks require nonempty prediction vectors or matrices"
            )
        if check["input"]["kind"] == "csv":
            used.add(check["input"]["fixture"])
    return used
