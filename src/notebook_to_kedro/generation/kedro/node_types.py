"""Source-bound operator type declarations; no inference, evaluation or ML imports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import ProjectGenerationError

if TYPE_CHECKING:
    from notebook_to_kedro.generation.kedro.generator import _PipelineEntry

MAX_NODE_TYPE_BYTES = 65_536
MAX_DATASET_TYPES = 256
_PAIR_LENGTH = 2
TYPE_REFERENCES = {
    "bool": ("builtins", "bool"),
    "int": ("builtins", "int"),
    "float": ("builtins", "float"),
    "str": ("builtins", "str"),
    "pandas.DataFrame": ("pandas", "DataFrame"),
    "pandas.Series": ("pandas", "Series"),
    "numpy.ndarray": ("numpy", "ndarray"),
    "sklearn.pipeline.Pipeline": ("sklearn_pipeline", "Pipeline"),
    "sklearn.base.BaseEstimator": ("sklearn_base", "BaseEstimator"),
}
_MODULES = {
    "pandas": "pandas",
    "numpy": "numpy",
    "sklearn_pipeline": "sklearn.pipeline",
    "sklearn_base": "sklearn.base",
}


@dataclass(frozen=True, slots=True)
class NotebookTypeContract:
    """Immutable declarations, independent of facts, inference and runtime validation."""

    source_sha256: str
    datasets: tuple[tuple[str, str], ...]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate direct Python construction as strictly as JSON input."""
        if (
            self.schema_version != "1.0"
            or not isinstance(self.source_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.source_sha256) is None
            or not isinstance(self.datasets, tuple)
            or not 0 < len(self.datasets) <= MAX_DATASET_TYPES
        ):
            raise ProjectGenerationError(
                "Node types require schema 1.0, source SHA-256 and datasets"
            )
        names: set[str] = set()
        for pair in self.datasets:
            if (
                not isinstance(pair, tuple)
                or len(pair) != _PAIR_LENGTH
                or not isinstance(pair[0], str)
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,255}", pair[0]) is None
                or pair[0] in names
                or not isinstance(pair[1], str)
                or pair[1] not in TYPE_REFERENCES
            ):
                raise ProjectGenerationError(
                    "Node types require unique dataset names and allowed types"
                )
            names.add(pair[0])
        object.__setattr__(self, "datasets", tuple(sorted(self.datasets)))

    def to_dict(self) -> dict[str, object]:
        """Export a detached, canonical declaration rather than execution evidence."""
        return {
            "schema_version": self.schema_version,
            "source_sha256": self.source_sha256,
            "datasets": dict(self.datasets),
        }

    @property
    def modules(self) -> tuple[str, ...]:
        """Return only fixed runtime import aliases required by the selected types."""
        return tuple(
            sorted({TYPE_REFERENCES[value][0] for _, value in self.datasets} - {"builtins"})
        )

    def imports(self, namespace: str) -> tuple[str, ...]:
        """Render fixed stdlib/ML references for the generated runtime, without importing them."""
        return tuple(
            f"import {_MODULES[module]} as {namespace}_{module}" for module in self.modules
        )

    def annotation(self, dataset: str, namespace: str) -> str | None:
        """Resolve a declared dataset type, preserving unknown types as an explicit gap."""
        value = dict(self.datasets).get(dataset)
        if value is None:
            return None
        module, name = TYPE_REFERENCES[value]
        return f"{namespace}_{module}.{name}"

    def bind(self, source_sha256: str, entries: tuple[_PipelineEntry, ...]) -> str:
        """Check current source/graph binding and render an unverified declaration manifest."""
        if source_sha256 != self.source_sha256:
            raise ProjectGenerationError("Node type source SHA-256 differs from current notebook")
        datasets = {
            dataset for entry in entries for dataset in (*entry.inputs.values(), *entry.outputs)
        }
        declared = dict(self.datasets)
        if set(declared) - datasets:
            raise ProjectGenerationError("Node types reference unknown generated datasets")
        manifest = {
            "schema_version": "1.0",
            "declaration": self.to_dict(),
            "runtime_type_validation": "not_run",
            "dataframe_schema_validation": "not_supported",
            "untyped_datasets": sorted(datasets - set(declared)),
            "nodes": [
                {
                    "task_id": entry.task.id,
                    "inputs": dict(entry.inputs),
                    "outputs": dict(zip(entry.task.outputs, entry.outputs, strict=True)),
                }
                for entry in entries
            ],
        }
        return json.dumps(manifest, sort_keys=True, indent=2) + "\n"


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectGenerationError(f"Duplicate node type field: {key}")
        result[key] = value
    return result


def load_notebook_type_contract(path: str | Path) -> NotebookTypeContract:
    """Read one bounded declaration file; reject arbitrary type expressions and imports."""
    try:
        with Path(path).open("rb") as stream:
            content = stream.read(MAX_NODE_TYPE_BYTES + 1)
        if len(content) > MAX_NODE_TYPE_BYTES:
            raise ProjectGenerationError("Node type contract exceeds 64 KiB")
        data = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
        if (
            not isinstance(data, dict)
            or set(data) != {"schema_version", "source_sha256", "datasets"}
            or not isinstance(data["datasets"], dict)
        ):
            raise ProjectGenerationError(
                "Node type contract has missing, unknown or invalid fields"
            )
        return NotebookTypeContract(
            data["source_sha256"], tuple(data["datasets"].items()), data["schema_version"]
        )
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ProjectGenerationError(f"Cannot read node type contract: {error}") from error
