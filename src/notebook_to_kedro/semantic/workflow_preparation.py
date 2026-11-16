"""Explicit orchestration declarations, separate from observed source and persistent I/O."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from notebook_to_kedro.exceptions import FunctionalWorkflowError
from notebook_to_kedro.semantic.application_project import ApplicationProject
from notebook_to_kedro.semantic.functional_config import (
    MAX_CONFIGURATION_BYTES,
    _public_name,
    _unique_object,
)

MAX_PREPARATION_ITEMS = 64
_PAIR_LENGTH = 2
_FIELDS = frozenset(
    {"schema_version", "source_package", "entrypoint", "arguments", "calls", "output"}
)


@dataclass(frozen=True, slots=True)
class WorkflowCall:
    """One operator-declared call; arguments bind source parameter names to workflow values."""

    function: str
    arguments: tuple[tuple[str, str], ...]
    output: str

    def __post_init__(self) -> None:
        if (
            not _public_name(self.function)
            or not _public_name(self.output)
            or not isinstance(self.arguments, tuple)
            or len(self.arguments) > MAX_PREPARATION_ITEMS
            or any(
                not isinstance(item, tuple)
                or len(item) != _PAIR_LENGTH
                or not all(_public_name(value) for value in item)
                for item in self.arguments
            )
            or len(dict(self.arguments)) != len(self.arguments)
        ):
            raise FunctionalWorkflowError(
                "Calls require public names and unique immutable argument pairs"
            )


@dataclass(frozen=True, slots=True)
class WorkflowPreparationDefinition:
    """An unreviewed call sequence, without inferred dataset types, paths or execution approval."""

    source_package: str
    entrypoint: str
    arguments: tuple[str, ...]
    calls: tuple[WorkflowCall, ...]
    output: str
    schema_version: str = "1.0"
    application_project: ApplicationProject | None = None

    def __post_init__(self) -> None:
        if (
            self.schema_version not in ("1.0", "1.1")
            or not isinstance(self.source_package, str)
            or not self.source_package
            or PurePosixPath(self.source_package).is_absolute()
            or PurePosixPath(self.source_package).as_posix() != self.source_package
            or ".." in PurePosixPath(self.source_package).parts
            or "\\" in self.source_package
            or ":" in self.source_package
            or not _public_name(self.entrypoint)
            or not _public_name(self.output)
        ):
            raise FunctionalWorkflowError(
                "Preparation requires schema 1.0 or 1.1, a relative package and public names"
            )
        if self.schema_version == "1.1":
            if not isinstance(self.application_project, ApplicationProject):
                raise FunctionalWorkflowError("Preparation schema 1.1 requires application_project")
        elif self.application_project is not None:
            raise FunctionalWorkflowError("Application preparation requires schema 1.1")
        if (
            not isinstance(self.arguments, tuple)
            or len(self.arguments) > MAX_PREPARATION_ITEMS
            or any(not _public_name(value) for value in self.arguments)
            or len(set(self.arguments)) != len(self.arguments)
            or not isinstance(self.calls, tuple)
            or not 1 <= len(self.calls) <= MAX_PREPARATION_ITEMS
            or any(not isinstance(call, WorkflowCall) for call in self.calls)
        ):
            raise FunctionalWorkflowError(
                "Preparation requires up to 64 unique arguments and 1-64 immutable calls"
            )

    def to_dict(self) -> dict[str, object]:
        """Return fresh JSON values for review, without importing source."""
        data = asdict(self)
        if self.application_project is None:
            data.pop("application_project")
        else:
            data["application_project"] = self.application_project.to_dict()
        data["arguments"] = list(self.arguments)
        data["calls"] = [
            {"function": call.function, "arguments": dict(call.arguments), "output": call.output}
            for call in self.calls
        ]
        return data

    @classmethod
    def from_dict(cls, data: object) -> WorkflowPreparationDefinition:
        """Reject unknown fields and freeze explicitly declared calls."""
        fields = _FIELDS
        if isinstance(data, dict) and data.get("schema_version") == "1.1":
            fields = fields | {"application_project"}
        if (
            not isinstance(data, dict)
            or data.keys() != fields
            or not isinstance(data["arguments"], list)
            or not isinstance(data["calls"], list)
            or any(
                not isinstance(call, dict)
                or call.keys() != {"function", "arguments", "output"}
                or not isinstance(call["arguments"], dict)
                for call in data["calls"]
            )
        ):
            raise FunctionalWorkflowError("Invalid preparation fields or call declarations")
        return cls(
            data["source_package"],
            data["entrypoint"],
            tuple(data["arguments"]),
            tuple(
                WorkflowCall(call["function"], tuple(call["arguments"].items()), call["output"])
                for call in data["calls"]
            ),
            data["output"],
            data["schema_version"],
            ApplicationProject.from_dict(data["application_project"])
            if "application_project" in data
            else None,
        )


def load_workflow_preparation_definition(path: str | Path) -> WorkflowPreparationDefinition:
    """Load a bounded declaration without code evaluation or source discovery."""
    try:
        with Path(path).open("rb") as stream:
            content = stream.read(MAX_CONFIGURATION_BYTES + 1)
        if len(content) > MAX_CONFIGURATION_BYTES:
            raise FunctionalWorkflowError("Preparation definition exceeds 64 KiB")
        data = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise FunctionalWorkflowError(f"Cannot read preparation definition: {path}") from error
    return WorkflowPreparationDefinition.from_dict(cast("object", data))
