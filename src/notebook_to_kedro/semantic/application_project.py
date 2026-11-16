"""Explicit source project selection for application distribution metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from notebook_to_kedro.exceptions import FunctionalWorkflowError
from notebook_to_kedro.semantic.file_inputs import _relative_file


@dataclass(frozen=True, slots=True)
class ApplicationProject:
    """Select a source pyproject and additional files relative to its directory."""

    pyproject: str
    files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not _relative_file(self.pyproject)
            or PurePosixPath(self.pyproject).name != "pyproject.toml"
            or not isinstance(self.files, tuple)
            or any(not _relative_file(path) for path in self.files)
            or len(set(self.files)) != len(self.files)
        ):
            raise FunctionalWorkflowError(
                "Application project requires a relative pyproject.toml "
                "and unique immutable file paths"
            )

    def to_dict(self) -> dict[str, object]:
        """Export independent JSON values for the selected source project."""
        return {"pyproject": self.pyproject, "files": list(self.files)}

    @classmethod
    def from_dict(cls, data: object) -> ApplicationProject:
        """Load the explicit metadata path and additional-file list."""
        if (
            not isinstance(data, dict)
            or data.keys() != {"pyproject", "files"}
            or not isinstance(data["files"], list)
        ):
            raise FunctionalWorkflowError("Application project fields must be pyproject and files")
        return cls(data["pyproject"], tuple(data["files"]))
