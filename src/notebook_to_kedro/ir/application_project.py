"""Captured static application metadata and selected project-file identities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from notebook_to_kedro.ir.file_inputs import ReferencedFile


@dataclass(frozen=True, slots=True)
class ApplicationDistribution:
    """Source declarations used to stage an independently installable application project."""

    pyproject: str
    package_root: str
    name: str
    version: str
    requires_python: str | None
    dependencies: tuple[str, ...]
    optional_dependencies: tuple[tuple[str, tuple[str, ...]], ...]
    scripts: tuple[tuple[str, str], ...]
    project_fields: tuple[str, ...]
    files: tuple[ReferencedFile, ...]

    def to_dict(self) -> dict[str, object]:
        """Export declared metadata with capture/build/resolution status."""
        return {
            "schema_version": "1.0",
            **asdict(self),
            "metadata_status": "static_declarations_captured",
            "build_status": "not_run",
            "dependency_resolution": "not_run",
        }

    @property
    def sha256(self) -> str:
        """Bind the captured project files and static declarations."""
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
