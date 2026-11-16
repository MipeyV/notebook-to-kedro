"""Explicit application-owned artifact destinations, without runtime filesystem operations."""

from __future__ import annotations

import keyword
import re
from dataclasses import asdict, dataclass

from notebook_to_kedro.exceptions import FunctionalWorkflowError

MAX_ARTIFACT_DESTINATIONS = 8
_DEVICES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in "123456789"
}


def _name(value: object) -> bool:
    return (
        isinstance(value, str)
        and value != "parameters"
        and not keyword.iskeyword(value)
        and re.fullmatch(r"[a-z][a-z0-9_]*", value) is not None
    )


@dataclass(frozen=True, slots=True)
class ArtifactDestination:
    """One exact flat-parameter binding to a new runtime directory under artifacts/."""

    parameter: str
    key: str
    path: str

    def __post_init__(self) -> None:
        if (
            not _name(self.parameter)
            or not _name(self.key)
            or not isinstance(self.path, str)
            or re.fullmatch(r"artifacts/[a-z][a-z0-9_-]{0,63}", self.path) is None
            or self.path.rsplit("/", maxsplit=1)[-1].upper() in _DEVICES
        ):
            raise FunctionalWorkflowError(
                "Artifact destinations require public parameter/key names and artifacts/<run_name>"
            )

    def to_dict(self) -> dict[str, str]:
        """Export declarative bindings; no directory existence or execution claim."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: object) -> ArtifactDestination:
        """Reject implicit ownership, extra fields and unsupported path policies."""
        if not isinstance(data, dict) or data.keys() != {"parameter", "key", "path"}:
            raise FunctionalWorkflowError(
                "Artifact destination fields must be parameter, key and path"
            )
        return cls(data["parameter"], data["key"], data["path"])
