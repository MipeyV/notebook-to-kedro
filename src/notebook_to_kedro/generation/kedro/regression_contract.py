"""Explicit, immutable JSON expectations for tests shipped with functional projects."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from notebook_to_kedro.exceptions import WorkflowRegressionError
from notebook_to_kedro.semantic.functional_config import FunctionalWorkflowConfiguration

if TYPE_CHECKING:
    from notebook_to_kedro.semantic.functional_workflow import FunctionalWorkflowPlan

MAX_REGRESSION_BYTES = 65_536
MAX_REGRESSION_DEPTH = 16
MAX_SCENARIOS = 100
_SCENARIO_FIELDS = frozenset({"id", "inputs", "parameters", "expected", "nodes"})


def _json_value(value: object, depth: int = 0) -> None:
    if depth > MAX_REGRESSION_DEPTH:
        raise WorkflowRegressionError("Regression JSON nesting exceeds 16 levels")
    if isinstance(value, (dict, list)):
        if isinstance(value, dict) and any(not isinstance(key, str) for key in value):
            raise WorkflowRegressionError("Regression JSON keys must be strings")
        for item in value.values() if isinstance(value, dict) else value:
            _json_value(item, depth + 1)
    elif type(value) not in (str, bool, int, float, type(None)) or (
        isinstance(value, float) and not math.isfinite(value)
    ):
        raise WorkflowRegressionError("Regression values must be finite JSON values")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WorkflowRegressionError(f"Duplicate regression field: {key}")
        result[key] = value
    return result


def _validate(data: object) -> None:
    _json_value(data)
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "scenarios"}
        or data["schema_version"] != "1.0"
    ):
        raise WorkflowRegressionError(
            "Regression contract requires schema_version 1.0 and scenarios"
        )
    scenarios = data["scenarios"]
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= MAX_SCENARIOS:
        raise WorkflowRegressionError("Regression contract requires 1 to 100 scenarios")
    seen: set[str] = set()
    for scenario in scenarios:
        if (
            not isinstance(scenario, dict)
            or not {"id", "inputs", "parameters", "expected"} <= scenario.keys() <= _SCENARIO_FIELDS
        ):
            raise WorkflowRegressionError(
                "Regression scenarios require id/inputs/parameters/expected; only nodes is optional"
            )
        name = scenario["id"]
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name) is None
            or name in seen
        ):
            raise WorkflowRegressionError(
                "Regression scenario IDs must be unique public identifiers of at most 64 characters"
            )
        seen.add(name)
        if any(
            not isinstance(scenario[key], dict) for key in ("inputs", "parameters")
        ) or not isinstance(scenario.get("nodes", {}), dict):
            raise WorkflowRegressionError("Regression inputs, parameters and nodes must be objects")
        for case in scenario.get("nodes", {}).values():
            if (
                not isinstance(case, dict)
                or set(case) != {"inputs", "expected"}
                or not isinstance(case["inputs"], dict)
            ):
                raise WorkflowRegressionError(
                    "Node cases require exactly inputs (object) and expected"
                )


@dataclass(frozen=True, slots=True)
class WorkflowRegressionContract:
    """Canonical serialized values prevent mutable nested expectations from drifting."""

    canonical_json: str

    def __post_init__(self) -> None:
        """Validate direct construction without executing source to infer an oracle."""
        try:
            if (
                not isinstance(self.canonical_json, str)
                or len(self.canonical_json.encode("utf-8")) > MAX_REGRESSION_BYTES
            ):
                raise WorkflowRegressionError(
                    "Regression contract must be UTF-8 JSON within 64 KiB"
                )
            data = json.loads(self.canonical_json, object_pairs_hook=_unique_object)
        except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise WorkflowRegressionError("Cannot decode regression contract") from error
        _validate(data)
        object.__setattr__(
            self,
            "canonical_json",
            json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False),
        )

    @classmethod
    def from_dict(cls, data: object) -> WorkflowRegressionContract:
        """Copy supplied JSON expectations into immutable validated storage."""
        _json_value(data)
        try:
            source = json.dumps(data, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as error:
            raise WorkflowRegressionError("Cannot serialize regression contract") from error
        return cls(source)

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh tree; callers cannot mutate the stored oracle."""
        return json.loads(self.canonical_json)  # type: ignore[no-any-return]

    @property
    def sha256(self) -> str:
        """Identify supplied expectations, without authenticating review or correctness."""
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


def load_workflow_regression_contract(path: str | Path) -> WorkflowRegressionContract:
    """Read bounded declarative JSON without application imports or execution."""
    try:
        with Path(path).open("rb") as stream:
            content = stream.read(MAX_REGRESSION_BYTES + 1)
        if len(content) > MAX_REGRESSION_BYTES:
            raise WorkflowRegressionError("Regression contract exceeds 64 KiB")
        return WorkflowRegressionContract(content.decode("utf-8"))
    except (OSError, UnicodeError) as error:
        raise WorkflowRegressionError(f"Cannot read regression contract: {path}") from error


def validate_regression_binding(
    contract: WorkflowRegressionContract, plan: FunctionalWorkflowPlan
) -> None:
    """Require exact workflow/node input names and immutable scalar parameter overrides."""
    steps = {step.name: step for step in plan.steps}
    for scenario in contract.to_dict()["scenarios"]:
        if set(scenario["inputs"]) != set(dict(plan.configuration.inputs)) or set(
            scenario["parameters"]
        ) != set(dict(plan.configuration.parameters)):
            raise WorkflowRegressionError(
                "Regression inputs/parameters must match the workflow boundaries exactly"
            )
        # Reuse the real workflow parameter contract rather than accepting mutable overrides.
        FunctionalWorkflowConfiguration(
            plan.configuration.entrypoint,
            plan.configuration.inputs,
            tuple(scenario["parameters"].items()),
            plan.configuration.outputs,
        )
        for name, case in scenario.get("nodes", {}).items():
            if name not in steps or set(case["inputs"]) != {
                value for _, value in steps[name].inputs
            }:
                raise WorkflowRegressionError(
                    "Regression node cases must match known step names and wrapper arguments"
                )
