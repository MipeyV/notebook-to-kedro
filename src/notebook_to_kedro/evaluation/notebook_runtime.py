"""Offline runtime controls for draft complete-notebook execution evidence."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from notebook_to_kedro.evaluation.behavioral_artifacts import _is_sha256

_PACKAGES = (
    "notebook-to-kedro",
    "nbformat",
    "kedro",
    "kedro-datasets",
    "numpy",
    "pandas",
    "scikit-learn",
    "scipy",
    "omegaconf",
)
_MAX_IDENTITY_BYTES = 16_777_216


@dataclass(frozen=True, slots=True)
class NotebookRuntimeIdentity:
    """Selected installed versions and local code/lock identities, not an attestation."""

    python_version: str
    implementation: str
    platform: str
    machine: str
    packages: tuple[tuple[str, str | None], ...]
    lock_sha256: str | None
    package_sha256: str

    def __post_init__(self) -> None:
        for value in (self.python_version, self.implementation, self.platform, self.machine):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("runtime identifiers must be non-empty strings")
        if tuple(name for name, _version in self.packages) != _PACKAGES:
            raise ValueError("runtime package inventory mismatch")
        for _name, version in self.packages:
            if version is not None and (not isinstance(version, str) or not version.strip()):
                raise ValueError("runtime package versions must be non-empty strings or null")
        for digest in (self.lock_sha256, self.package_sha256):
            if digest is not None and (not isinstance(digest, str) or not _is_sha256(digest)):
                raise ValueError("runtime digest must be a lowercase SHA256")
        if self.package_sha256 is None:
            raise ValueError("runtime package digest is required")

    @property
    def replayable(self) -> bool:
        """Unknown lock or selected installed versions cannot certify compatibility."""
        return self.lock_sha256 is not None and all(
            version is not None for _, version in self.packages
        )


def _bounded_bytes(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(_MAX_IDENTITY_BYTES + 1)
    if len(data) > _MAX_IDENTITY_BYTES:
        raise ValueError("runtime identity file exceeds byte limit")
    return data


def _package_digest(directory: Path) -> str:
    files = sorted(directory.rglob("*.py"))
    if not files:
        raise ValueError("runtime package sources are unavailable")
    digest = hashlib.sha256()
    size = 0
    for path in files:
        data = _bounded_bytes(path)
        size += len(data)
        if size > _MAX_IDENTITY_BYTES:
            raise ValueError("runtime package sources exceed byte limit")
        name = path.relative_to(directory).as_posix().encode("utf-8")
        digest.update(len(name).to_bytes(8, "big") + name + len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def collect_notebook_runtime_identity(project_root: str | Path) -> NotebookRuntimeIdentity:
    """Record local identities without importing optional libraries or contacting a service."""
    versions = []
    for name in _PACKAGES:
        try:
            version: str | None = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            version = None
        versions.append((name, version))
    lock = Path(project_root) / "uv.lock"
    return NotebookRuntimeIdentity(
        platform.python_version(),
        platform.python_implementation(),
        sys.platform,
        platform.machine(),
        tuple(versions),
        hashlib.sha256(_bounded_bytes(lock)).hexdigest() if lock.is_file() else None,
        _package_digest(Path(__file__).resolve().parents[1]),
    )


def require_notebook_runtime_compatibility(
    before: NotebookRuntimeIdentity,
    after: NotebookRuntimeIdentity,
    current: NotebookRuntimeIdentity,
) -> None:
    """Refuse unknown identities, observed drift or changed replay controls."""
    if not all(identity.replayable for identity in (before, after, current)):
        raise ValueError("runtime compatibility requires known lock and package versions")
    if before != after or before != current:
        raise ValueError("notebook runtime compatibility mismatch")
