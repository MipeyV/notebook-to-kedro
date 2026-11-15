"""Bounded explicit I/O configuration for a linear functional workflow."""

from __future__ import annotations

import json
import keyword
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, TypeAlias, cast

from notebook_to_kedro.exceptions import FunctionalWorkflowError

if TYPE_CHECKING:
    from notebook_to_kedro.ir.facts import JsonPrimitive

FunctionalParameterValue: TypeAlias = "JsonPrimitive | tuple[tuple[str, JsonPrimitive], ...]"

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


def _finite_scalar(value: object) -> bool:
    return type(value) in (str, bool, int, float, type(None)) and not (
        isinstance(value, float) and not math.isfinite(value)
    )


def _validate_parameter(value: object, schema_version: str) -> None:
    if _finite_scalar(value):
        return
    if schema_version not in ("1.1", "1.2", "1.3") or not isinstance(value, tuple):
        raise FunctionalWorkflowError(
            "Workflow parameters require finite JSON scalars; flat mappings require schema 1.1+ "
            "and immutable pairs"
        )
    if any(
        not isinstance(item, tuple)
        or len(item) != _PAIR_LENGTH
        or not isinstance(item[0], str)
        or not _finite_scalar(item[1])
        for item in value
    ):
        raise FunctionalWorkflowError(
            "Parameter mappings require string keys and finite JSON scalars"
        )
    if len({key for key, _ in value}) != len(value):
        raise FunctionalWorkflowError("Parameter mappings cannot repeat keys")


def _decode_parameter(value: object) -> FunctionalParameterValue:
    if isinstance(value, dict):
        return tuple(value.items())
    if not _finite_scalar(value):
        raise FunctionalWorkflowError(
            "Workflow parameters must be finite JSON scalars or flat objects"
        )
    return cast("JsonPrimitive", value)


@dataclass(frozen=True, slots=True)
class FunctionalWorkflowConfiguration:
    """One entrypoint, JSON inputs, immutable explicit parameters and one JSON output."""

    entrypoint: str
    inputs: tuple[tuple[str, str], ...]
    parameters: tuple[tuple[str, FunctionalParameterValue], ...]
    outputs: tuple[tuple[str, str], ...]
    schema_version: str = "1.0"
    source_package: str | None = None

    def __post_init__(self) -> None:
        """Validate both direct API values and decoded configuration."""
        if self.schema_version not in ("1.0", "1.1", "1.2", "1.3") or not _public_name(
            self.entrypoint
        ):
            raise FunctionalWorkflowError(
                "Workflow requires schema_version 1.0 through 1.3 and a public entrypoint"
            )
        if self.schema_version == "1.3":
            if (
                not isinstance(self.source_package, str)
                or not self.source_package
                or PurePosixPath(self.source_package).is_absolute()
                or PurePosixPath(self.source_package).as_posix() != self.source_package
                or ".." in PurePosixPath(self.source_package).parts
                or "\\" in self.source_package
                or ":" in self.source_package
            ):
                raise FunctionalWorkflowError(
                    "Schema 1.3 requires a contained relative source_package path"
                )
        elif self.source_package is not None:
            raise FunctionalWorkflowError("source_package requires workflow schema 1.3")
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
        for _, value in self.parameters:
            _validate_parameter(value, self.schema_version)

    def parameter_values(self) -> dict[str, JsonPrimitive | dict[str, JsonPrimitive]]:
        """Return fresh JSON objects without exposing mutable configuration state."""
        return {
            key: dict(value) if isinstance(value, tuple) else value
            for key, value in self.parameters
        }

    def to_dict(self) -> dict[str, object]:
        """Export declarative values without importing source dependencies."""
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "entrypoint": self.entrypoint,
            "inputs": dict(self.inputs),
            "parameters": self.parameter_values(),
            "outputs": dict(self.outputs),
        }
        if self.source_package is not None:
            data["source_package"] = self.source_package
        return data

    @classmethod
    def from_dict(cls, data: object) -> FunctionalWorkflowConfiguration:
        """Reject unknown fields and non-mapping boundaries."""
        if (
            not isinstance(data, dict)
            or data.keys()
            != (_FIELDS | {"source_package"} if data.get("schema_version") == "1.3" else _FIELDS)
            or any(not isinstance(data[key], dict) for key in ("inputs", "parameters", "outputs"))
        ):
            raise FunctionalWorkflowError(
                "Required workflow fields: schema_version, entrypoint, inputs, parameters, "
                "outputs; schema 1.3 also requires source_package"
            )
        return cls(
            data["entrypoint"],
            tuple(data["inputs"].items()),
            tuple((key, _decode_parameter(value)) for key, value in data["parameters"].items()),
            tuple(data["outputs"].items()),
            data["schema_version"],
            data.get("source_package"),
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
