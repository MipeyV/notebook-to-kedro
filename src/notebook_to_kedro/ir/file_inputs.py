"""Captured byte identities for declared file-reference bundles."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ReferencedFile:
    """One contained regular input file, hashed without a domain reader."""

    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class FileReferenceInventory:
    """Primary file first, followed by explicitly declared sibling sidecars."""

    argument: str
    files: tuple[ReferencedFile, ...]

    def to_dict(self) -> dict[str, object]:
        """Export byte observations, separately from application-level validation."""
        return {
            **asdict(self),
            "validation_status": "hashed_not_loaded",
            "domain_status": "not_verified",
        }
