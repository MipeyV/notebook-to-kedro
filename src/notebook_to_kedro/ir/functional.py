"""Source-independent inspection contracts for explicit Python functional blocks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class SourceUnit:
    """One decoded module or real notebook code cell, with retained source identity."""

    id: str
    path: str
    kind: Literal["python", "notebook"]
    document_sha256: str
    source: str
    cell_id: str | None = None

    @property
    def source_sha256(self) -> str:
        """Hash captured decoded text separately from the loader's document identity."""
        return hashlib.sha256(self.source.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class BlockSpan:
    """One-based lines and zero-based UTF-8 byte columns in a source unit."""

    unit_id: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int


@dataclass(frozen=True, slots=True)
class BlockDiagnostic:
    """Static blockers and warnings; passing analysis never establishes execution safety."""

    code: str
    severity: Literal["error", "warning"]
    message: str
    span: BlockSpan | None = None
    block_id: str | None = None


@dataclass(frozen=True, slots=True)
class BlockStatement:
    """Accounting for every parsed module-level statement, including unsupported code."""

    id: str
    kind: Literal["import", "function", "documentation", "unsupported"]
    source: str
    ast_sha256: str
    span: BlockSpan
    block_id: str | None = None


@dataclass(frozen=True, slots=True)
class FunctionalBlock:
    """Observed explicit function interface and body, without target-framework decisions."""

    id: str
    name: str
    parameters: tuple[str, ...]
    outputs: tuple[str, ...]
    source: str
    ast_sha256: str
    span: BlockSpan
    global_reads: tuple[str, ...]
    calls: tuple[str, ...]
    possible_mutation_targets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BlockDependency:
    """A module-function reference; calls are distinguished from other references."""

    caller_id: str
    callee_id: str
    kind: Literal["call", "reference"]


@dataclass(frozen=True, slots=True)
class FunctionalAnalysis:
    """Inspectable static analysis, separate from notebook facts and conversion plans."""

    sources: tuple[SourceUnit, ...]
    statements: tuple[BlockStatement, ...]
    blocks: tuple[FunctionalBlock, ...]
    dependencies: tuple[BlockDependency, ...]
    diagnostics: tuple[BlockDiagnostic, ...]
    schema_version: str = "1.0"

    @property
    def complete(self) -> bool:
        """Indicate that the supported inspection subset has no blocking diagnostics."""
        return bool(self.blocks) and not any(item.severity == "error" for item in self.diagnostics)

    @property
    def structure_sha256(self) -> str | None:
        """Fingerprint static structure, excluding origins; this is not behavioral proof."""
        if not self.complete:
            return None
        payload = {
            "schema_version": self.schema_version,
            "imports": [item.ast_sha256 for item in self.statements if item.kind == "import"],
            "blocks": [
                {
                    key: value
                    for key, value in asdict(block).items()
                    if key not in {"span", "source"}
                }
                for block in self.blocks
            ],
            "dependencies": [asdict(item) for item in self.dependencies],
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        """Export captured source and diagnostics for local inspection, without executing code."""
        payload = {
            **asdict(self),
            "sources": [
                {**asdict(unit), "source_sha256": unit.source_sha256} for unit in self.sources
            ],
            "complete": self.complete,
            "structure_sha256": self.structure_sha256,
        }
        return json.dumps(payload, sort_keys=True, indent=2) + "\n"
