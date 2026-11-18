"""Explicit, immutable JSON expectations for tests shipped with functional projects."""

from __future__ import annotations

import hashlib
import json
import math
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from notebook_to_kedro.exceptions import ProjectGenerationError, WorkflowRegressionError
from notebook_to_kedro.generation.kedro.regression_outcomes import validate_outcome
from notebook_to_kedro.generation.writer import validate_project_files
from notebook_to_kedro.semantic.functional_config import FunctionalWorkflowConfiguration

if TYPE_CHECKING:
    from notebook_to_kedro.semantic.functional_workflow import FunctionalWorkflowPlan

MAX_REGRESSION_BYTES = 65_536
MAX_REGRESSION_DEPTH = 16
MAX_SCENARIOS = 100
MAX_REGRESSION_FIXTURE_BYTES = 1024 * 1024
MAX_REGRESSION_FIXTURE_TOTAL_BYTES = 8 * 1024 * 1024
_REPARSE_POINT = 0x400
_SCENARIO_FIELDS = frozenset({"id", "inputs", "parameters", "expected", "nodes"})


def _valid_header(data: dict[str, Any], storage: str) -> bool:
    legacy = "1.0" if storage == "inline" else "1.1"
    return (
        data.get("schema_version") == legacy and set(data) == {"schema_version", "scenarios"}
    ) or (
        data.get("schema_version") == "1.2"
        and data.get("storage") == storage
        and set(data) == {"schema_version", "storage", "scenarios"}
    )


def _uses_fixtures(data: object) -> bool:
    return isinstance(data, dict) and (
        data.get("schema_version") == "1.1"
        or (data.get("schema_version") == "1.2" and data.get("storage") == "fixtures")
    )


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
    if not isinstance(data, dict) or not _valid_header(data, "inline"):
        raise WorkflowRegressionError(
            "Regression contract requires inline schema 1.0 or schema 1.2 with explicit storage"
        )
    exceptions = data["schema_version"] == "1.2"
    allowed = _SCENARIO_FIELDS | ({"raises"} if exceptions else set())
    scenarios = data["scenarios"]
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= MAX_SCENARIOS:
        raise WorkflowRegressionError("Regression contract requires 1 to 100 scenarios")
    seen: set[str] = set()
    for scenario in scenarios:
        if (
            not isinstance(scenario, dict)
            or not {"id", "inputs", "parameters"} <= scenario.keys() <= allowed
        ):
            raise WorkflowRegressionError(
                "Regression scenarios require id/inputs/parameters and one explicit outcome; "
                "only nodes is optional"
            )
        validate_outcome(scenario, pipeline=True, exceptions=exceptions)
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
                or not {"inputs"}
                <= case.keys()
                <= ({"inputs", "expected", "raises"} if exceptions else {"inputs", "expected"})
                or not isinstance(case["inputs"], dict)
            ):
                raise WorkflowRegressionError(
                    "Node cases require inputs (object) and one explicit outcome"
                )
            validate_outcome(case, pipeline=False, exceptions=exceptions)


def _fixture_definitions(data: dict[str, Any]) -> list[dict[str, str]]:
    _json_value(data)
    scenarios = data.get("scenarios")
    if (
        not _valid_header(data, "fixtures")
        or not isinstance(scenarios, list)
        or not 1 <= len(scenarios) <= MAX_SCENARIOS
    ):
        raise WorkflowRegressionError("Fixture contracts require 1 to 100 scenario references")
    seen: set[str] = set()
    definitions: list[dict[str, str]] = []
    for item in scenarios:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "sha256"}
            or not isinstance(item["path"], str)
            or re.fullmatch(r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.json", item["path"]) is None
            or not isinstance(item["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
            or item["path"].casefold() in seen
        ):
            raise WorkflowRegressionError(
                "Scenario references require distinct portable relative JSON paths and SHA-256"
            )
        try:
            validate_project_files({Path(item["path"]): ""})
        except ProjectGenerationError as error:
            raise WorkflowRegressionError(
                "Fixture paths must be portable regular-file paths"
            ) from error
        seen.add(item["path"].casefold())
        definitions.append(item)
    return definitions


def _resolved_fixtures(data: dict[str, Any], captures: tuple[str, ...]) -> dict[str, Any]:
    definitions = _fixture_definitions(data)
    if len(captures) != len(definitions):
        raise WorkflowRegressionError("Fixture contracts require every captured scenario")
    scenarios: list[Any] = []
    total = 0
    for definition, source in zip(definitions, captures, strict=True):
        if not isinstance(source, str):
            raise WorkflowRegressionError("Captured fixtures must be immutable UTF-8 JSON text")
        content = source.encode("utf-8")
        total += len(content)
        if (
            len(content) > MAX_REGRESSION_FIXTURE_BYTES
            or total > MAX_REGRESSION_FIXTURE_TOTAL_BYTES
        ):
            raise WorkflowRegressionError(
                "Regression fixtures exceed the 1 MiB/file or 8 MiB total budget"
            )
        if hashlib.sha256(content).hexdigest() != definition["sha256"]:
            raise WorkflowRegressionError(
                f"Regression fixture SHA-256 mismatch: {definition['path']}"
            )
        scenarios.append(json.loads(source, object_pairs_hook=_unique_object))
    resolved = {"schema_version": "1.0", "scenarios": scenarios}
    if data["schema_version"] == "1.2":
        resolved.update(schema_version="1.2", storage="inline")
    _validate(resolved)
    return resolved


def _read_fixture(root: Path, relative: str, remaining: int) -> bytes:
    current = root
    for part in Path(relative).parts:
        current /= part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            raise WorkflowRegressionError(
                "Regression fixtures cannot traverse links or reparse points"
            )
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise WorkflowRegressionError(
                "Regression fixtures require regular files and directories"
            )
    if not current.is_file() or not current.resolve().is_relative_to(root):
        raise WorkflowRegressionError("Regression fixtures must be contained regular files")
    with current.open("rb") as stream:
        content = stream.read(min(MAX_REGRESSION_FIXTURE_BYTES, remaining) + 1)
    if len(content) > MAX_REGRESSION_FIXTURE_BYTES or len(content) > remaining:
        raise WorkflowRegressionError(
            "Regression fixtures exceed the 1 MiB/file or 8 MiB total budget"
        )
    return content


@dataclass(frozen=True, slots=True)
class WorkflowRegressionContract:
    """Canonical serialized values prevent mutable nested expectations from drifting."""

    canonical_json: str
    fixture_jsons: tuple[str, ...] = field(default=(), repr=False)

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
            if not isinstance(self.fixture_jsons, tuple):
                raise WorkflowRegressionError("Captured fixtures must be an immutable tuple")
            if _uses_fixtures(data):
                _resolved_fixtures(data, self.fixture_jsons)
            else:
                if self.fixture_jsons:
                    raise WorkflowRegressionError("Inline contracts cannot carry captured fixtures")
                _validate(data)
        except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise WorkflowRegressionError("Cannot decode regression contract") from error
        object.__setattr__(
            self,
            "canonical_json",
            json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False),
        )

    @classmethod
    def from_dict(
        cls, data: object, *, fixture_jsons: tuple[str, ...] = ()
    ) -> WorkflowRegressionContract:
        """Copy supplied JSON expectations into immutable validated storage."""
        _json_value(data)
        try:
            source = json.dumps(data, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as error:
            raise WorkflowRegressionError("Cannot serialize regression contract") from error
        return cls(source, fixture_jsons)

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh declaration, retaining any pinned fixture references."""
        return json.loads(self.canonical_json)  # type: ignore[no-any-return]

    def resolved_dict(self) -> dict[str, Any]:
        """Return fresh inline scenario values from captured text, without filesystem access."""
        data = self.to_dict()
        return _resolved_fixtures(data, self.fixture_jsons) if self.fixture_jsons else data

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
        source = content.decode("utf-8")
        data = json.loads(source, object_pairs_hook=_unique_object)
        captures: list[str] = []
        if _uses_fixtures(data):
            root = Path(path).resolve().parent
            total = 0
            for definition in _fixture_definitions(data):
                raw = _read_fixture(
                    root, definition["path"], MAX_REGRESSION_FIXTURE_TOTAL_BYTES - total
                )
                total += len(raw)
                captures.append(raw.decode("utf-8"))
        return WorkflowRegressionContract(source, tuple(captures))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise WorkflowRegressionError(f"Cannot read regression contract: {path}") from error


def validate_regression_binding(
    contract: WorkflowRegressionContract, plan: FunctionalWorkflowPlan
) -> None:
    """Require exact input names and parameter overrides under the workflow's own schema."""
    if plan.configuration.artifact_destinations:
        raise WorkflowRegressionError(
            "JSON regression contracts do not define runtime artifact expectations"
        )
    if plan.configuration.memory_output:
        raise WorkflowRegressionError(
            "JSON regression contracts do not define typed memory-result expectations"
        )
    if plan.configuration.file_inputs:
        raise WorkflowRegressionError(
            "JSON regression contracts do not define file-reference fixtures"
        )
    steps = {step.name: step for step in plan.steps}
    for scenario in contract.resolved_dict()["scenarios"]:
        if "raises" in scenario and scenario["raises"]["node"] not in steps:
            raise WorkflowRegressionError("Pipeline exceptions must name a known unprefixed node")
        if set(scenario["inputs"]) != set(dict(plan.configuration.inputs)) or set(
            scenario["parameters"]
        ) != set(dict(plan.configuration.parameters)):
            raise WorkflowRegressionError(
                "Regression inputs/parameters must match the workflow boundaries exactly"
            )
        # Reuse the real workflow parameter contract rather than accepting mutable overrides.
        settings = plan.configuration.to_dict()
        settings["parameters"] = scenario["parameters"]
        FunctionalWorkflowConfiguration.from_dict(settings)
        for name, case in scenario.get("nodes", {}).items():
            if name not in steps or set(case["inputs"]) != {
                value for _, value in steps[name].inputs
            }:
                raise WorkflowRegressionError(
                    "Regression node cases must match known step names and wrapper arguments"
                )
