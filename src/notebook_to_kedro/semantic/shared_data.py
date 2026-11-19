"""Explicit bounded opt-in to source-ordered shared intermediate references."""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass

from notebook_to_kedro.exceptions import FunctionalWorkflowError

MAX_SHARED_VALUES = 100


@dataclass(frozen=True, slots=True)
class SharedDataPolicy:
    """Named intermediate datasets shared by reference within one ordered process."""

    values: tuple[str, ...]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate immutable declarations without inferring source effects or purity."""
        if (
            self.schema_version != "1.0"
            or not isinstance(self.values, tuple)
            or not 1 <= len(self.values) <= MAX_SHARED_VALUES
            or any(
                not isinstance(name, str)
                or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) is None
                or keyword.iskeyword(name)
                or name == "parameters"
                for name in self.values
            )
            or len(set(self.values)) != len(self.values)
        ):
            raise FunctionalWorkflowError(
                "Shared data requires schema 1.0 and 1 to 100 distinct public value names "
                "stored as an immutable tuple, each within 64 characters"
            )

    def to_dict(self) -> dict[str, object]:
        """Return fresh declarative JSON; no runtime identity evidence is implied."""
        return {"schema_version": self.schema_version, "values": list(self.values)}

    @classmethod
    def from_dict(cls, data: object) -> SharedDataPolicy:
        """Decode a closed versioned policy independently of workflow schema versions."""
        if (
            not isinstance(data, dict)
            or set(data) != {"schema_version", "values"}
            or not isinstance(data["values"], list)
        ):
            raise FunctionalWorkflowError("Shared data requires schema_version and a values list")
        return cls(tuple(data["values"]), data["schema_version"])
