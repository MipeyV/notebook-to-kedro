"""Bounded explicit CSV fixtures and typed expectations for notebook projects."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from notebook_to_kedro.exceptions import ProjectGenerationError, WorkflowRegressionError
from notebook_to_kedro.generation.kedro.notebook_model_checks import validate_model_checks
from notebook_to_kedro.generation.kedro.notebook_regression_values import validate_descriptor
from notebook_to_kedro.generation.kedro.regression_contract import (
    MAX_REGRESSION_BYTES,
    MAX_REGRESSION_FIXTURE_BYTES,
    MAX_REGRESSION_FIXTURE_TOTAL_BYTES,
    MAX_SCENARIOS,
    _json_value,
    _read_fixture,
    _unique_object,
)
from notebook_to_kedro.generation.kedro.regression_outcomes import validate_outcome
from notebook_to_kedro.generation.writer import validate_project_files

_CAPTURE_PAIR_LENGTH = 2


def _identifier(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value) is not None


def _definitions(data: object) -> dict[str, Any]:
    _json_value(data)
    fields = {"schema_version", "fixtures", "scenarios"}
    if isinstance(data, dict) and data.get("schema_version") == "1.1":
        fields.add("model_checks")
    if (
        not isinstance(data, dict)
        or set(data) != fields
        or data["schema_version"] not in ("1.0", "1.1")
        or not isinstance(data["fixtures"], dict)
        or len(data["fixtures"]) > MAX_SCENARIOS
        or not isinstance(data["scenarios"], list)
        or len(data["scenarios"]) > MAX_SCENARIOS
    ):
        raise WorkflowRegressionError(
            "Notebook regressions require schema 1.0 or 1.1, fixtures and scenarios"
        )
    paths: set[str] = set()
    for name, item in data["fixtures"].items():
        if (
            not _identifier(name)
            or not isinstance(item, dict)
            or set(item) != {"path", "sha256"}
            or not isinstance(item["path"], str)
            or re.fullmatch(r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.csv", item["path"]) is None
            or item["path"].casefold() in paths
            or not isinstance(item["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
        ):
            raise WorkflowRegressionError("Fixtures require unique portable CSV paths and SHA-256")
        try:
            validate_project_files({Path(item["path"]): ""})
        except ProjectGenerationError as error:
            raise WorkflowRegressionError(
                "Fixture paths must be portable regular-file paths"
            ) from error
        paths.add(item["path"].casefold())
    return data


def _values(values: object, fixtures: set[str], *, inputs: bool) -> None:
    if not isinstance(values, dict) or (not inputs and not values):
        raise WorkflowRegressionError("Expectations require a nonempty named value object")
    for descriptor in values.values():
        validate_descriptor(descriptor, fixtures, input_value=inputs)


def _scenarios(data: dict[str, Any]) -> None:
    fixtures = set(data["fixtures"])
    seen: set[str] = set()
    used: set[str] = set()
    for case in data["scenarios"]:
        if (
            not isinstance(case, dict)
            or not {"id", "inputs", "parameters"}
            <= case.keys()
            <= {"id", "inputs", "parameters", "expected", "raises", "nodes"}
            or not _identifier(case["id"])
            or case["id"] in seen
            or not isinstance(case["inputs"], dict)
            or not isinstance(case["parameters"], dict)
            or not isinstance(case.get("nodes", {}), dict)
        ):
            raise WorkflowRegressionError("Invalid notebook regression scenario or duplicate ID")
        seen.add(case["id"])
        validate_outcome(case, pipeline=True, exceptions=True)
        for fixture in case["inputs"].values():
            if not isinstance(fixture, str) or fixture not in fixtures:
                raise WorkflowRegressionError(
                    "Pipeline inputs must reference declared CSV fixtures"
                )
            used.add(fixture)
        if "expected" in case:
            _values(case["expected"], fixtures, inputs=False)
        for node in case.get("nodes", {}).values():
            if not isinstance(node, dict) or not {"inputs"} <= node.keys() <= {
                "inputs",
                "expected",
                "raises",
            }:
                raise WorkflowRegressionError("Node cases require inputs and one explicit outcome")
            validate_outcome(node, pipeline=False, exceptions=True)
            _values(node["inputs"], fixtures, inputs=True)
            used.update(v["fixture"] for v in node["inputs"].values() if v["kind"] == "csv")
            if "expected" in node:
                _values(node["expected"], fixtures, inputs=False)
    used.update(validate_model_checks(data))
    if used != fixtures:
        raise WorkflowRegressionError("Every declared fixture must be used by a scenario")


@dataclass(frozen=True, slots=True)
class NotebookRegressionContract:
    """Immutable declarations and raw UTF-8 captures; no oracle inference or execution."""

    canonical_json: str
    fixture_texts: tuple[tuple[str, str], ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        """Validate direct construction as strictly as file loading."""
        try:
            if (
                not isinstance(self.canonical_json, str)
                or len(self.canonical_json.encode("utf-8")) > MAX_REGRESSION_BYTES
            ):
                raise WorkflowRegressionError("Notebook regression manifest exceeds 64 KiB")
            data = _definitions(json.loads(self.canonical_json, object_pairs_hook=_unique_object))
            _scenarios(data)
            self._validate_captures(data)
            object.__setattr__(
                self,
                "canonical_json",
                json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False),
            )
        except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise WorkflowRegressionError("Cannot decode notebook regression contract") from error

    def _validate_captures(self, data: dict[str, Any]) -> None:
        if not isinstance(self.fixture_texts, tuple) or any(
            not isinstance(pair, tuple)
            or len(pair) != _CAPTURE_PAIR_LENGTH
            or not all(isinstance(item, str) for item in pair)
            for pair in self.fixture_texts
        ):
            raise WorkflowRegressionError("Captured CSV fixtures require immutable name/text pairs")
        captures = dict(self.fixture_texts)
        if len(captures) != len(self.fixture_texts) or set(captures) != set(data["fixtures"]):
            raise WorkflowRegressionError("Every CSV fixture requires exactly one capture")
        total = 0
        for name, source in captures.items():
            raw = source.encode("utf-8")
            total += len(raw)
            if (
                len(raw) > MAX_REGRESSION_FIXTURE_BYTES
                or total > MAX_REGRESSION_FIXTURE_TOTAL_BYTES
            ):
                raise WorkflowRegressionError(
                    "CSV fixtures exceed the 1 MiB/file or 8 MiB total budget"
                )
            if hashlib.sha256(raw).hexdigest() != data["fixtures"][name]["sha256"]:
                raise WorkflowRegressionError(f"CSV fixture SHA-256 mismatch: {name}")

    @classmethod
    def from_dict(
        cls, data: object, *, fixture_texts: tuple[tuple[str, str], ...] = ()
    ) -> NotebookRegressionContract:
        """Capture supplied expectations without importing the source or ML libraries."""
        _json_value(data)
        return cls(json.dumps(data, sort_keys=True, allow_nan=False), fixture_texts)

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh declaration, preserving fixture references."""
        return json.loads(self.canonical_json)  # type: ignore[no-any-return]

    @property
    def sha256(self) -> str:
        """Identify declarations without authenticating their correctness or review."""
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


def load_notebook_regression_contract(path: str | Path) -> NotebookRegressionContract:
    """Load bounded contained regular CSV files after validating their declarations."""
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_REGRESSION_BYTES + 1)
        if len(raw) > MAX_REGRESSION_BYTES:
            raise WorkflowRegressionError("Notebook regression manifest exceeds 64 KiB")
        source = raw.decode("utf-8")
        data = _definitions(json.loads(source, object_pairs_hook=_unique_object))
        _scenarios(data)
        captures = []
        total = 0
        for name, definition in data["fixtures"].items():
            content = _read_fixture(
                Path(path).resolve().parent,
                definition["path"],
                MAX_REGRESSION_FIXTURE_TOTAL_BYTES - total,
            )
            total += len(content)
            captures.append((name, content.decode("utf-8")))
        return NotebookRegressionContract(source, tuple(captures))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise WorkflowRegressionError(
            f"Cannot read notebook regression contract: {path}"
        ) from error
