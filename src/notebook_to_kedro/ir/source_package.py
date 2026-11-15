"""Immutable inventory of an explicitly selected local source package."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class PackageFile:
    """One raw file to retain under the original package name."""

    path: str
    sha256: str
    size_bytes: int
    module: str | None
    ast_sha256: str | None


@dataclass(frozen=True, slots=True)
class PackageImport:
    """Syntactic module reference; imported symbols and runtime availability are unverified."""

    source: str
    line: int
    module: str
    local: bool


@dataclass(frozen=True, slots=True)
class SourcePackage:
    """Captured package inventory, not execution or dependency-installation evidence."""

    root: str
    name: str
    source_file: str
    module: str
    files: tuple[PackageFile, ...]
    imports: tuple[PackageImport, ...]
    excluded_caches: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Export inventory facts without reading source files or importing code."""
        return {
            "schema_version": "1.0",
            **asdict(self),
            "validation_status": "compiled_not_executed",
            "dependency_status": "not_inferred",
            "distribution_metadata_status": "not_reconstructed",
        }

    @property
    def sha256(self) -> str:
        """Identify the captured inventory, without authenticating its provenance."""
        data = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
