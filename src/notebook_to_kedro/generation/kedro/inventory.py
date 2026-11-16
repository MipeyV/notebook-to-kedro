"""Byte identities of the files published by application-aware workflow generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import ProjectGenerationError

if TYPE_CHECKING:
    from collections.abc import Mapping

GENERATION_INVENTORY = Path("generation-inventory.json")


def file_identity(path: Path) -> dict[str, str | int]:
    """Hash a regular file's bytes using bounded reads."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while content := stream.read(65536):
            digest.update(content)
            size += len(content)
    return {"sha256": digest.hexdigest(), "size_bytes": size}


def render_generation_inventory(
    files: Mapping[Path, str], copies: tuple[tuple[Path, Path], ...]
) -> str:
    """Describe generated/copied files before publication, excluding this inventory itself."""
    entries = {}
    for path, content in files.items():
        data = content.encode("utf-8")
        entries[path.as_posix()] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "kind": "generated",
        }
    try:
        entries.update(
            {
                target.as_posix(): {**file_identity(source), "kind": "copied"}
                for source, target in copies
            }
        )
    except OSError as error:
        raise ProjectGenerationError(f"Cannot capture publication inventory: {error}") from error
    return (
        json.dumps(
            {"schema_version": "1.0", "scope": "published_files", "files": entries},
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
