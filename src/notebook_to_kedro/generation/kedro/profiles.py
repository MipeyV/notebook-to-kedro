"""Versioned, declarative naming and single-pipeline organization for Kedro."""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
import keyword
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from notebook_to_kedro.exceptions import KedroProfileError

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan

PROFILE_SCHEMA_VERSION = "1.0"
MAX_PROFILE_BYTES = 65_536
_FIELDS = frozenset(
    {"schema_version", "profile_id", "profile_version", "pipeline_name", "node_name_prefix"}
)
_REQUIRED_FIELDS = frozenset({"schema_version", "profile_id", "profile_version"})


@dataclass(frozen=True, slots=True)
class KedroArchitectureProfile:
    """Immutable conventions; no executable templates or business-logic transformations."""

    profile_id: str
    profile_version: str
    pipeline_name: str = "notebook_pipeline"
    node_name_prefix: str = ""
    schema_version: str = PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate direct API construction as strictly as loaded configuration."""
        values = (
            self.schema_version,
            self.profile_id,
            self.profile_version,
            self.pipeline_name,
            self.node_name_prefix,
        )
        if any(not isinstance(value, str) for value in values):
            raise KedroProfileError("Kedro profile fields must be strings")
        if self.schema_version != PROFILE_SCHEMA_VERSION:
            raise KedroProfileError(f"Unsupported Kedro profile schema: {self.schema_version}")
        if re.fullmatch(r"[a-z][a-z0-9_.-]{0,127}", self.profile_id) is None:
            raise KedroProfileError(
                "profile_id must be a lowercase dotted or hyphenated identifier"
            )
        if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.profile_version) is None:
            raise KedroProfileError(
                "profile_version must have three numeric components, e.g. 1.0.0"
            )
        if (
            re.fullmatch(r"[a-z][a-z0-9_]*", self.pipeline_name) is None
            or keyword.iskeyword(self.pipeline_name)
            or re.fullmatch(r"con|prn|aux|nul|com[1-9]|lpt[1-9]", self.pipeline_name) is not None
        ):
            raise KedroProfileError("pipeline_name must be a public lowercase Python identifier")
        if (
            self.node_name_prefix
            and re.fullmatch(r"[a-z][a-z0-9_]*_", self.node_name_prefix) is None
        ):
            raise KedroProfileError(
                "node_name_prefix must be empty or a lowercase prefix ending in _"
            )

    def to_dict(self) -> dict[str, str]:
        """Return every normalized field, including default conventions."""
        return asdict(self)

    def to_json(self) -> str:
        """Return canonical JSON used for configuration identity."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @property
    def sha256(self) -> str:
        """Hash normalized configuration; this is not authenticated provenance."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, data: object) -> KedroArchitectureProfile:
        """Reject unknown fields and missing identity/schema declarations."""
        if not isinstance(data, dict) or not _REQUIRED_FIELDS <= data.keys() <= _FIELDS:
            raise KedroProfileError(
                "Kedro profile requires schema_version/profile_id/profile_version; "
                "unknown fields are forbidden"
            )
        values = cast("dict[str, str]", data)
        return cls(
            profile_id=values["profile_id"],
            profile_version=values["profile_version"],
            schema_version=values["schema_version"],
            pipeline_name=values.get("pipeline_name", "notebook_pipeline"),
            node_name_prefix=values.get("node_name_prefix", ""),
        )


DEFAULT_KEDRO_PROFILE = KedroArchitectureProfile("notebook-to-kedro.default", "1.0.0")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise KedroProfileError(f"Duplicate Kedro profile field: {key}")
        result[key] = value
    return result


def load_kedro_profile(path: str | Path) -> KedroArchitectureProfile:
    """Load a bounded UTF-8 JSON profile without importing code or contacting a provider."""
    try:
        with Path(path).open("rb") as source:
            raw = source.read(MAX_PROFILE_BYTES + 1)
        if len(raw) > MAX_PROFILE_BYTES:
            raise KedroProfileError("Kedro profile exceeds the 64 KiB size limit")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise KedroProfileError(f"Cannot read Kedro profile {path}: {error}") from error
    return KedroArchitectureProfile.from_dict(data)


def resolve_node_names(plan: ConversionPlan, profile: KedroArchitectureProfile) -> dict[str, str]:
    """Map stable task IDs to generated function/node names, without modifying the plan."""
    names = {task.id: f"{profile.node_name_prefix}{task.name}" for task in plan.task_candidates}
    normalized = tuple(unicodedata.normalize("NFKC", name) for name in names.values())
    if len(names) != len(plan.task_candidates) or len(set(normalized)) != len(normalized):
        raise KedroProfileError(
            "Profile requires unique task IDs and distinct generated Python names"
        )
    if any(
        not name.isidentifier() or keyword.iskeyword(name) or name.startswith("_")
        for name in normalized
    ):
        raise KedroProfileError("Profile produced an invalid public Python node name")
    bindings = set(dir(builtins))
    try:
        for source in plan.imports:
            statements = ast.parse(source).body
            if len(statements) != 1 or not isinstance(statements[0], (ast.Import, ast.ImportFrom)):
                raise KedroProfileError("Profile compatibility requires explicit import statements")
            statement = statements[0]
            if isinstance(statement, ast.ImportFrom) and (
                statement.level or any(alias.name == "*" for alias in statement.names)
            ):
                raise KedroProfileError("Profiles do not support relative or wildcard imports")
            bindings.update(
                unicodedata.normalize(
                    "NFKC",
                    alias.asname
                    or (
                        alias.name.split(".")[0]
                        if isinstance(statement, ast.Import)
                        else alias.name
                    ),
                )
                for alias in statement.names
            )
    except SyntaxError as error:
        raise KedroProfileError(f"Cannot check profile import compatibility: {error}") from error
    collisions = sorted(set(normalized) & bindings)
    if collisions:
        message = f"Generated node names shadow imports or builtins: {', '.join(collisions)}"
        raise KedroProfileError(message)
    return names
