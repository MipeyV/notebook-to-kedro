"""Bounded raw-file hashing without importing application code or decoding data."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import FunctionalWorkflowError
from notebook_to_kedro.ir.file_inputs import FileReferenceInventory, ReferencedFile

if TYPE_CHECKING:
    from notebook_to_kedro.semantic.file_inputs import FileReferenceInput

MAX_REFERENCE_BYTES = 256 * 1024 * 1024
_CHUNK_BYTES = 64 * 1024
_REPARSE_POINT = 0x400


def _regular_file(root: Path, relative: str) -> Path:
    current = root
    for component in Path(relative).parts:
        current /= component
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            raise FunctionalWorkflowError("File references cannot traverse links or reparse points")
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise FunctionalWorkflowError("File references require regular files and directories")
    if not current.is_file() or not current.resolve().is_relative_to(root):
        raise FunctionalWorkflowError("Referenced inputs must be contained regular files")
    return current


def capture_file_references(
    root: Path,
    definitions: tuple[tuple[str, FileReferenceInput], ...],
) -> tuple[FileReferenceInventory, ...]:
    """Hash complete bundles within 256 MiB in total; never load domain objects."""
    root = root.resolve()
    inventories: list[FileReferenceInventory] = []
    total = 0
    try:
        for argument, definition in definitions:
            files: list[ReferencedFile] = []
            for relative in (definition.path, *definition.sidecars):
                path = _regular_file(root, relative)
                digest = hashlib.sha256()
                size = 0
                with path.open("rb") as stream:
                    while content := stream.read(
                        min(_CHUNK_BYTES, MAX_REFERENCE_BYTES - total + 1)
                    ):
                        total += len(content)
                        size += len(content)
                        if total > MAX_REFERENCE_BYTES:
                            raise FunctionalWorkflowError("File references exceed 256 MiB in total")
                        digest.update(content)
                files.append(ReferencedFile(relative, digest.hexdigest(), size))
            inventories.append(FileReferenceInventory(argument, tuple(files)))
    except OSError as error:
        raise FunctionalWorkflowError(f"Cannot capture file reference: {error}") from error
    return tuple(inventories)
