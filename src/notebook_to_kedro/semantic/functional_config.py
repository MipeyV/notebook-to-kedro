"""Bounded explicit I/O configuration for a linear functional workflow."""

from __future__ import annotations

import json
import keyword
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from notebook_to_kedro.exceptions import FunctionalWorkflowError

if TYPE_CHECKING:
    from notebook_to_kedro.ir.facts import JsonPrimitive

MAX_CONFIGURATION_BYTES = 65_536
_PAIR_LENGTH = 2
_FIELDS = frozenset({"schema_version", "entrypoint", "inputs", "parameters", "outputs"})


def _public_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and value != "parameters"
        and re.fullmatch(r"[a-z][a-z0-9_]*", value) is not None
        and not keyword.iskeyword(value)
    )


@dataclass(frozen=True, slots=True)
class FunctionalWorkflowConfiguration:
    """One entrypoint, JSON input files, scalar parameters and one JSON output."""

    entrypoint: str
    inputs: tuple[tuple[str, str], ...]
    parameters: tuple[tuple[str, JsonPrimitive], ...]
    outputs: tuple[tuple[str, str], ...]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate both direct API values and decoded configuration."""
        if self.schema_version != "1.0" or not _public_name(self.entrypoint):
            raise FunctionalWorkflowError(
                "Workflow requires schema_version 1.0 and a public entrypoint"
            )
        for pairs in (self.inputs, self.parameters, self.outputs):
            if not isinstance(pairs, tuple) or any(
                not isinstance(item, tuple)
                or len(item) != _PAIR_LENGTH
                or not _public_name(item[0])
                for item in pairs
            ):
                raise FunctionalWorkflowError(
                    "Workflow mappings require public argument names and immutable pairs"
                )
            if len({key for key, _ in pairs}) != len(pairs):
                raise FunctionalWorkflowError("Workflow mappings cannot repeat argument names")
        if set(dict(self.inputs)) & set(dict(self.parameters)):
            raise FunctionalWorkflowError("Workflow inputs and parameters must be disjoint")
        if any(not isinstance(value, str) or not value for _, value in self.inputs):
            raise FunctionalWorkflowError("Workflow input paths must be nonempty strings")
        if len(self.outputs) != 1 or any(
            not isinstance(value, str)
            or re.fullmatch(r"data/08_reporting/[a-z][a-z0-9_]*\.json", value) is None
            for _, value in self.outputs
        ):
            raise FunctionalWorkflowError(
                "Workflow requires one output under data/08_reporting/<name>.json"
            )
        if any(
            type(value) not in (str, bool, int, float, type(None))
            or (isinstance(value, float) and not math.isfinite(value))
            for _, value in self.parameters
        ):
            raise FunctionalWorkflowError("Workflow parameters must be finite JSON scalars")

    def to_dict(self) -> dict[str, object]:
        """Export declarative values without importing source dependencies."""
        return {
            "schema_version": self.schema_version,
            "entrypoint": self.entrypoint,
            "inputs": dict(self.inputs),
            "parameters": dict(self.parameters),
            "outputs": dict(self.outputs),
        }

    @classmethod
    def from_dict(cls, data: object) -> FunctionalWorkflowConfiguration:
        """Reject unknown fields and non-mapping boundaries."""
        if (
            not isinstance(data, dict)
            or data.keys() != _FIELDS
            or any(not isinstance(data[key], dict) for key in ("inputs", "parameters", "outputs"))
        ):
            raise FunctionalWorkflowError(
                "Required workflow fields: schema_version, entrypoint, inputs, parameters, outputs"
            )
        return cls(
            data["entrypoint"],
            tuple(data["inputs"].items()),
            tuple(data["parameters"].items()),
            tuple(data["outputs"].items()),
            data["schema_version"],
        )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise FunctionalWorkflowError(f"Duplicate workflow field: {key}")
        values[key] = value
    return values


def load_functional_workflow_configuration(path: str | Path) -> FunctionalWorkflowConfiguration:
    """Load bounded UTF-8 JSON, rejecting duplicate keys and executable configuration."""
    try:
        with Path(path).open("rb") as stream:
            content = stream.read(MAX_CONFIGURATION_BYTES + 1)
        if len(content) > MAX_CONFIGURATION_BYTES:
            raise FunctionalWorkflowError("Workflow configuration exceeds 64 KiB")
        data = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise FunctionalWorkflowError(f"Cannot read workflow configuration: {path}") from error
    return FunctionalWorkflowConfiguration.from_dict(cast("object", data))
