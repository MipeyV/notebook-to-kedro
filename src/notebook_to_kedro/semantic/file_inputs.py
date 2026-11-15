"""Explicit immutable raw-file references, separate from JSON-value inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from notebook_to_kedro.exceptions import FunctionalWorkflowError

MAX_SIDECARS = 16


def _relative_file(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value != "."
        and not PurePosixPath(value).is_absolute()
        and PurePosixPath(value).as_posix() == value
        and ".." not in PurePosixPath(value).parts
        and "\\" not in value
        and ":" not in value
    )


@dataclass(frozen=True, slots=True)
class FileReferenceInput:
    """A primary file and explicitly named sibling sidecars; no inferred formats or schemas."""

    path: str
    sidecars: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not _relative_file(self.path)
            or not isinstance(self.sidecars, tuple)
            or len(self.sidecars) > MAX_SIDECARS
            or any(not _relative_file(value) for value in self.sidecars)
        ):
            raise FunctionalWorkflowError(
                "File references require relative POSIX files and up to 16 immutable sidecars"
            )
        paths = (self.path, *self.sidecars)
        if len(set(paths)) != len(paths) or any(
            PurePosixPath(value).parent != PurePosixPath(self.path).parent
            for value in self.sidecars
        ):
            raise FunctionalWorkflowError("Sidecars must be distinct siblings of the primary file")

    def to_dict(self) -> dict[str, object]:
        """Export fresh declarative values without reading file contents."""
        return {"path": self.path, "sidecars": list(self.sidecars)}

    @classmethod
    def from_dict(cls, data: object) -> FileReferenceInput:
        """Require an explicit sidecar list, including when it is empty."""
        if (
            not isinstance(data, dict)
            or data.keys() != {"path", "sidecars"}
            or not isinstance(data["sidecars"], list)
        ):
            raise FunctionalWorkflowError("File reference fields must be exactly path and sidecars")
        return cls(data["path"], tuple(data["sidecars"]))
