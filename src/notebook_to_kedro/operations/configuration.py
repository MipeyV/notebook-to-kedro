"""Explicit local project settings; configuration contains data, never executable hooks."""

from __future__ import annotations

import json
import keyword
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Literal

from notebook_to_kedro.exceptions import LocalOperationError

MAX_LOCAL_CONFIGURATION_BYTES = 65_536
_REQUIRED = frozenset({"schema_version", "project_root", "source", "source_kind"})
_OPTIONAL = frozenset(
    {"package_name", "workflow_configuration", "architecture_profile", "regression_contract"}
)


def contained_path(root: Path, path: Path) -> Path:
    """Resolve a local API path and refuse the root itself or an escaping symlink."""
    if not isinstance(path, Path):
        raise LocalOperationError("LO001", "Operation paths must be pathlib.Path values")
    portable = PureWindowsPath(path.as_posix())
    if not path.is_absolute() and (portable.drive or portable.root or "\\" in path.as_posix()):
        raise LocalOperationError("LO001", "Ambiguous platform-specific relative path")
    resolved = (root / path).resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise LocalOperationError("LO001", f"Path must stay inside project_root: {path}")
    return resolved


@dataclass(frozen=True, slots=True)
class LocalProjectConfiguration:
    """Settings for one existing deterministic notebook or functional source."""

    project_root: Path
    source: Path
    source_kind: Literal["notebook", "functional"]
    package_name: str = "generated_project"
    workflow_configuration: Path | None = None
    architecture_profile: Path | None = None
    regression_contract: Path | None = None
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate direct API settings as well as loaded JSON."""
        if not isinstance(self.project_root, Path) or not isinstance(self.source, Path):
            raise LocalOperationError(
                "LO001", "project_root and source must be pathlib.Path values"
            )
        root = self.project_root.resolve()
        if self.schema_version != "1.0" or self.source_kind not in ("notebook", "functional"):
            raise LocalOperationError(
                "LO001", "Expected schema_version 1.0 and a supported source_kind"
            )
        if not root.is_dir():
            raise LocalOperationError("LO001", "project_root must be an existing directory")
        if (
            not isinstance(self.package_name, str)
            or not self.package_name.isidentifier()
            or (self.package_name.startswith("_") or keyword.iskeyword(self.package_name))
        ):
            raise LocalOperationError("LO001", "package_name must be a public Python identifier")
        if self.source_kind == "functional":
            if self.workflow_configuration is None:
                raise LocalOperationError(
                    "LO001", "Functional operations require workflow_configuration"
                )
        elif self.workflow_configuration is not None or self.regression_contract is not None:
            raise LocalOperationError(
                "LO001", "Notebook operations do not accept workflow or regression settings"
            )
        object.__setattr__(self, "project_root", root)
        for field in (
            "source",
            "workflow_configuration",
            "architecture_profile",
            "regression_contract",
        ):
            value = getattr(self, field)
            if value is not None:
                if not isinstance(value, Path):
                    raise LocalOperationError("LO001", f"{field} must be a pathlib.Path")
                object.__setattr__(self, field, contained_path(root, value))

    def to_dict(self) -> dict[str, object]:
        """Export explicit settings with root-relative file paths."""
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "project_root": self.project_root.as_posix(),
            "source_kind": self.source_kind,
            "source": self.source.relative_to(self.project_root).as_posix(),
            "package_name": self.package_name,
        }
        for field in ("workflow_configuration", "architecture_profile", "regression_contract"):
            value = getattr(self, field)
            if value is not None:
                data[field] = value.relative_to(self.project_root).as_posix()
        return data


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LocalOperationError("LO001", f"Duplicate local configuration field: {key}")
        result[key] = value
    return result


def _relative_file(value: object) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or (PureWindowsPath(value).drive or PureWindowsPath(value).root)
    ):
        raise LocalOperationError(
            "LO001", "File settings must be nonempty relative paths with / separators"
        )
    return Path(value)


def load_local_project_configuration(path: str | Path) -> LocalProjectConfiguration:
    """Load one bounded JSON file; anchor project_root to its directory, never the CWD."""
    location = Path(path).resolve()
    try:
        with location.open("rb") as stream:
            content = stream.read(MAX_LOCAL_CONFIGURATION_BYTES + 1)
        if len(content) > MAX_LOCAL_CONFIGURATION_BYTES:
            raise LocalOperationError("LO001", "Local configuration exceeds 64 KiB")
        data = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
        if (
            not isinstance(data, dict)
            or not data.keys() >= _REQUIRED
            or data.keys() - (_REQUIRED | _OPTIONAL)
        ):
            raise LocalOperationError("LO001", "Local configuration has missing or unknown fields")
        if not isinstance(data["project_root"], str) or not data["project_root"]:
            raise LocalOperationError("LO001", "project_root must be a nonempty path string")
        root_path = Path(data["project_root"])
        if not root_path.is_absolute() and PureWindowsPath(data["project_root"]).drive:
            raise LocalOperationError(
                "LO001", "project_root cannot use a foreign or drive-relative path"
            )
        return LocalProjectConfiguration(
            project_root=location.parent / root_path,
            source=_relative_file(data["source"]),
            source_kind=data["source_kind"],
            package_name=data.get("package_name", "generated_project"),
            schema_version=data["schema_version"],
            **{
                key: _relative_file(data[key])
                for key in ("workflow_configuration", "architecture_profile", "regression_contract")
                if key in data
            },
        )
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, LocalOperationError):
            raise
        raise LocalOperationError(
            "LO001", f"Cannot read local configuration: {location}: {error}"
        ) from error
