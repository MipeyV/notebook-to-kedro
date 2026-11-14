"""Prepare complete projects privately before publishing a new destination."""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from time import sleep
from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import ProjectGenerationError

if TYPE_CHECKING:
    from collections.abc import Mapping

_WINDOWS_DEVICES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in "123456789¹²³"}
)
_FIRST_PRINTABLE_CHARACTER = 32
_WINDOWS = os.name == "nt"
_RENAME_ATTEMPTS = 3
_RENAME_DELAY_SECONDS = 0.05


def _publish(staging: Path, root: Path) -> None:
    attempt = 0
    while True:
        _require_new_destination(root)
        try:
            staging.rename(root)
            return
        except PermissionError as error:
            attempt += 1
            if (
                not _WINDOWS
                or getattr(error, "winerror", None) not in {5, 32, 33}
                or attempt == _RENAME_ATTEMPTS
            ):
                raise
            sleep(_RENAME_DELAY_SECONDS)


def _require_new_destination(root: Path) -> None:
    if root.exists() or root.is_symlink():
        raise ProjectGenerationError(f"Destination already exists: {root}")


def _validate_targets(paths: tuple[Path, ...]) -> None:
    # Windows path semantics also reject drive-relative paths on POSIX hosts. Comparing
    # case-insensitively prevents projects that would collide when moved to Windows.
    seen: set[PureWindowsPath] = set()
    for path in paths:
        portable = PureWindowsPath(path.as_posix())
        if (
            not path.parts
            or portable.drive
            or portable.root
            or ".." in portable.parts
            or any(
                ord(character) < _FIRST_PRINTABLE_CHARACTER or character == ":"
                for character in path.as_posix()
            )
            or any(
                part.endswith((".", " "))
                or part.split(".", maxsplit=1)[0].upper() in _WINDOWS_DEVICES
                for part in portable.parts
            )
        ):
            message = f"Project file must have a relative contained path: {path}"
            raise ProjectGenerationError(message)
        if any(
            portable == other or portable in other.parents or other in portable.parents
            for other in seen
        ):
            raise ProjectGenerationError(f"Project file destinations overlap: {path}")
        seen.add(portable)


def validate_project_files(
    files: Mapping[Path, str],
    copies: tuple[tuple[Path, Path], ...] = (),
) -> None:
    """Check portable, nonoverlapping targets and regular copy sources without writing."""
    paths = (*files, *(target for _, target in copies))
    _validate_targets(paths)
    for source, _ in copies:
        if not source.is_file():
            message = f"Catalog source file does not exist or is not a file: {source}"
            raise ProjectGenerationError(message)


def write_project(
    root: Path,
    files: Mapping[Path, str],
    copies: tuple[tuple[Path, Path], ...] = (),
) -> tuple[Path, ...]:
    """Stage files and copies on the destination filesystem, then rename the project.

    Existing destinations are checked both before preparation and before publication.
    This is not a filesystem lock against concurrent edits, a crash-durability guarantee
    or a sandbox. Newly created parent directories may remain after an I/O failure.
    """
    _require_new_destination(root)
    validate_project_files(files, copies)
    paths = (*files, *(target for _, target in copies))
    try:
        root.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".notebook-to-kedro-", dir=root.parent) as directory:
            staging = Path(directory) / "project"
            for path, content in files.items():
                target = staging / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
            for source, path in copies:
                target = staging / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            _publish(staging, root)
    except OSError as error:
        raise ProjectGenerationError(f"Cannot publish project at {root}: {error}") from error
    return tuple(root / path for path in paths)
