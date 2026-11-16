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
from notebook_to_kedro.semantic.application_project import ApplicationProject
from notebook_to_kedro.semantic.artifacts import MAX_ARTIFACT_DESTINATIONS, ArtifactDestination
from notebook_to_kedro.semantic.file_inputs import FileReferenceInput

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
    if schema_version not in ("1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7") or not isinstance(
        value, tuple
    ):
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
    """One entrypoint, explicit boundaries/parameters and one JSON or memory-only output."""

    entrypoint: str
    inputs: tuple[tuple[str, str], ...]
    parameters: tuple[tuple[str, FunctionalParameterValue], ...]
    outputs: tuple[tuple[str, str], ...]
    schema_version: str = "1.0"
    source_package: str | None = None
    file_inputs: tuple[tuple[str, FileReferenceInput], ...] = ()
    artifact_destinations: tuple[tuple[str, ArtifactDestination], ...] = ()
    application_project: ApplicationProject | None = None

    def __post_init__(self) -> None:
        """Validate both direct API values and decoded configuration."""
        if self.schema_version not in (
            "1.0",
            "1.1",
            "1.2",
            "1.3",
            "1.4",
            "1.5",
            "1.6",
            "1.7",
        ) or not _public_name(self.entrypoint):
            raise FunctionalWorkflowError(
                "Workflow requires schema_version 1.0 through 1.7 and a public entrypoint"
            )
        if self.schema_version in ("1.3", "1.4", "1.5", "1.6", "1.7"):
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
                    "Schema 1.3+ requires a contained relative source_package path"
                )
        elif self.source_package is not None:
            raise FunctionalWorkflowError("source_package requires workflow schema 1.3+")
        for pairs in (
            self.inputs,
            self.parameters,
            self.outputs,
            self.file_inputs,
            self.artifact_destinations,
        ):
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
        self._validate_file_inputs()
        if any(not isinstance(value, str) or not value for _, value in self.inputs):
            raise FunctionalWorkflowError("Workflow input paths must be nonempty strings")
        if len(self.outputs) != 1 or any(
            not isinstance(value, str)
            or (
                not (self.schema_version in ("1.5", "1.6", "1.7") and value == "memory")
                and re.fullmatch(r"data/08_reporting/[a-z][a-z0-9_]*\.json", value) is None
            )
            for _, value in self.outputs
        ):
            raise FunctionalWorkflowError(
                "Workflow requires one output under data/08_reporting/<name>.json; "
                "schema 1.5 also accepts the explicit memory target"
            )
        for _, value in self.parameters:
            _validate_parameter(value, self.schema_version)
        self._validate_artifacts()
        self._validate_application()

    def _validate_application(self) -> None:
        if self.schema_version == "1.7":
            if not isinstance(self.application_project, ApplicationProject):
                raise FunctionalWorkflowError(
                    "Schema 1.7 requires an immutable application_project"
                )
        elif self.application_project is not None:
            raise FunctionalWorkflowError("Application projects require workflow schema 1.7")

    def _validate_artifacts(self) -> None:
        if self.schema_version not in ("1.6", "1.7") and self.artifact_destinations:
            raise FunctionalWorkflowError("Artifact destinations require workflow schema 1.6")
        if len(self.artifact_destinations) > MAX_ARTIFACT_DESTINATIONS or any(
            not isinstance(value, ArtifactDestination) for _, value in self.artifact_destinations
        ):
            raise FunctionalWorkflowError(
                "Workflow supports up to eight immutable artifact destinations"
            )
        paths: set[str] = set()
        for _, destination in self.artifact_destinations:
            value = dict(self.parameters).get(destination.parameter)
            if (
                not isinstance(value, tuple)
                or dict(value).get(destination.key) != destination.path
                or destination.path in paths
            ):
                raise FunctionalWorkflowError(
                    "Artifact paths must match unique declared flat-parameter bindings"
                )
            paths.add(destination.path)

    def _validate_file_inputs(self) -> None:
        if self.schema_version not in ("1.4", "1.5", "1.6", "1.7") and self.file_inputs:
            raise FunctionalWorkflowError("File references require workflow schema 1.4+")
        if any(not isinstance(value, FileReferenceInput) for _, value in self.file_inputs) or set(
            dict(self.file_inputs)
        ) & (set(dict(self.inputs)) | set(dict(self.parameters))):
            raise FunctionalWorkflowError(
                "File inputs require immutable references and disjoint boundary names"
            )

    @property
    def memory_output(self) -> bool:
        """Select nonpersistent object retention without importing or inferring its type."""
        return self.outputs[0][1] == "memory"

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
        if self.schema_version in ("1.4", "1.5", "1.6", "1.7"):
            data["file_inputs"] = {name: value.to_dict() for name, value in self.file_inputs}
        if self.schema_version in ("1.6", "1.7"):
            data["artifact_destinations"] = {
                name: value.to_dict() for name, value in self.artifact_destinations
            }
        if self.application_project is not None:
            data["application_project"] = self.application_project.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: object) -> FunctionalWorkflowConfiguration:
        """Reject unknown fields and non-mapping boundaries."""
        fields = _FIELDS
        if isinstance(data, dict) and data.get("schema_version") in (
            "1.3",
            "1.4",
            "1.5",
            "1.6",
            "1.7",
        ):
            fields = fields | {"source_package"}
            if data["schema_version"] in ("1.4", "1.5", "1.6", "1.7"):
                fields = fields | {"file_inputs"}
            if data["schema_version"] in ("1.6", "1.7"):
                fields = fields | {"artifact_destinations"}
            if data["schema_version"] == "1.7":
                fields = fields | {"application_project"}
        if (
            not isinstance(data, dict)
            or data.keys() != fields
            or any(not isinstance(data[key], dict) for key in ("inputs", "parameters", "outputs"))
            or (
                data.get("schema_version") in ("1.4", "1.5", "1.6", "1.7")
                and not isinstance(data["file_inputs"], dict)
            )
            or (
                data.get("schema_version") in ("1.6", "1.7")
                and not isinstance(data["artifact_destinations"], dict)
            )
        ):
            raise FunctionalWorkflowError(
                "Required workflow fields: schema_version, entrypoint, inputs, parameters, "
                "outputs; schema 1.3+ requires source_package, 1.4+ file_inputs "
                "and 1.6+ artifact_destinations, 1.7 application_project"
            )
        return cls(
            data["entrypoint"],
            tuple(data["inputs"].items()),
            tuple((key, _decode_parameter(value)) for key, value in data["parameters"].items()),
            tuple(data["outputs"].items()),
            data["schema_version"],
            data.get("source_package"),
            tuple(
                (name, FileReferenceInput.from_dict(value))
                for name, value in data.get("file_inputs", {}).items()
            ),
            tuple(
                (name, ArtifactDestination.from_dict(value))
                for name, value in data.get("artifact_destinations", {}).items()
            ),
            ApplicationProject.from_dict(data["application_project"])
            if "application_project" in data
            else None,
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
