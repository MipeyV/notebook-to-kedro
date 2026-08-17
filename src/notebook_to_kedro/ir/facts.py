"""Immutable intermediate representation for deterministic notebook facts."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from string import hexdigits
from typing import TypeAlias

JsonPrimitive: TypeAlias = str | int | float | bool | None
SHA256_HEX_LENGTH = 64


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        message = f"{field_name} must not be empty"
        raise ValueError(message)


def _require_unique(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        message = f"{field_name} must contain unique values"
        raise ValueError(message)


class Severity(StrEnum):
    """Diagnostic severity."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class CellKind(StrEnum):
    """Supported Jupyter cell kinds."""

    CODE = "code"
    MARKDOWN = "markdown"
    RAW = "raw"


class ImportKind(StrEnum):
    """Python import statement forms."""

    IMPORT = "import"
    FROM = "from"


class SymbolKind(StrEnum):
    """Syntactic category of a bound or referenced symbol."""

    DATA = "data"
    IMPORT = "import"
    FUNCTION = "function"
    CLASS = "class"
    PARAMETER = "parameter"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Location within a notebook code cell."""

    cell_index: int
    start_line: int | None = None
    start_column: int | None = None
    end_line: int | None = None
    end_column: int | None = None

    def __post_init__(self) -> None:
        if self.cell_index < 0:
            msg = "cell_index must be greater than or equal to zero"
            raise ValueError(msg)

        line_values = (self.start_line, self.end_line)
        if any(value is not None and value < 1 for value in line_values):
            msg = "line numbers must be greater than or equal to one"
            raise ValueError(msg)

        column_values = (self.start_column, self.end_column)
        if any(value is not None and value < 0 for value in column_values):
            msg = "column numbers must be greater than or equal to zero"
            raise ValueError(msg)

        start_is_complete = self.start_line is not None and self.start_column is not None
        end_is_complete = self.end_line is not None and self.end_column is not None
        if (self.start_line is None) != (self.start_column is None):
            msg = "start_line and start_column must be provided together"
            raise ValueError(msg)
        if (self.end_line is None) != (self.end_column is None):
            msg = "end_line and end_column must be provided together"
            raise ValueError(msg)
        if end_is_complete and not start_is_complete:
            msg = "an end position requires a start position"
            raise ValueError(msg)
        if start_is_complete and end_is_complete:
            start = (self.start_line, self.start_column)
            end = (self.end_line, self.end_column)
            if end < start:
                msg = "end position must not precede start position"
                raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DiagnosticDetail:
    """Immutable structured context attached to a diagnostic."""

    key: str
    value: JsonPrimitive

    def __post_init__(self) -> None:
        _require_non_empty(self.key, "key")


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Machine-readable and human-readable analysis finding."""

    id: str
    code: str
    severity: Severity
    message: str
    blocking: bool
    location: SourceLocation | None = None
    related_symbol: str | None = None
    details: tuple[DiagnosticDetail, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "id")
        _require_non_empty(self.code, "code")
        _require_non_empty(self.message, "message")
        detail_keys = tuple(detail.key for detail in self.details)
        _require_unique(detail_keys, "diagnostic detail keys")


@dataclass(frozen=True, slots=True)
class KeywordArgument:
    """Source expression supplied for a keyword call argument."""

    name: str
    source: str

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "name")
        _require_non_empty(self.source, "source")


@dataclass(frozen=True, slots=True)
class ImportFacts:
    """Facts extracted from one imported binding."""

    kind: ImportKind
    module: str
    bound_name: str
    location: SourceLocation
    name: str | None = None
    alias: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.module, "module")
        _require_non_empty(self.bound_name, "bound_name")
        if self.kind is ImportKind.FROM and not self.name:
            msg = "a from import requires an imported name"
            raise ValueError(msg)
        if self.kind is ImportKind.IMPORT and self.name is not None:
            msg = "a regular import must not define an imported name"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class CallFacts:
    """Syntactic facts extracted from one function or method call."""

    id: str
    qualified_name: str
    location: SourceLocation
    receiver: str | None = None
    method: str | None = None
    positional_argument_sources: tuple[str, ...] = ()
    keyword_arguments: tuple[KeywordArgument, ...] = ()
    literal_arguments: tuple[JsonPrimitive, ...] = ()
    possible_mutation_targets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "id")
        _require_non_empty(self.qualified_name, "qualified_name")
        if (self.receiver is None) != (self.method is None):
            msg = "receiver and method must either both be set or both be absent"
            raise ValueError(msg)
        keyword_names = tuple(argument.name for argument in self.keyword_arguments)
        _require_unique(keyword_names, "keyword argument names")
        _require_unique(self.possible_mutation_targets, "possible mutation targets")


@dataclass(frozen=True, slots=True)
class StatementFacts:
    """Facts associated with a top-level Python statement."""

    id: str
    index: int
    ast_type: str
    source: str
    location: SourceLocation
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    call_ids: tuple[str, ...] = ()
    conditional: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "id")
        _require_non_empty(self.ast_type, "ast_type")
        _require_non_empty(self.source, "source")
        if self.index < 0:
            msg = "statement index must be greater than or equal to zero"
            raise ValueError(msg)
        _require_unique(self.reads, "statement reads")
        _require_unique(self.writes, "statement writes")
        _require_unique(self.call_ids, "statement call IDs")


@dataclass(frozen=True, slots=True)
class CellFacts:
    """Facts and source preserved for one notebook cell."""

    id: str
    index: int
    kind: CellKind
    source: str
    execution_count: int | None = None
    statements: tuple[StatementFacts, ...] = ()
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    imports: tuple[ImportFacts, ...] = ()
    calls: tuple[CallFacts, ...] = ()
    diagnostic_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "id")
        if self.index < 0:
            msg = "cell index must be greater than or equal to zero"
            raise ValueError(msg)
        if self.execution_count is not None and self.execution_count < 0:
            msg = "execution_count must be greater than or equal to zero"
            raise ValueError(msg)
        if self.kind is not CellKind.CODE and (
            self.statements or self.reads or self.writes or self.imports or self.calls
        ):
            msg = "non-code cells must not contain Python analysis facts"
            raise ValueError(msg)
        _require_unique(tuple(statement.id for statement in self.statements), "statement IDs")
        _require_unique(tuple(call.id for call in self.calls), "call IDs")
        _require_unique(self.reads, "cell reads")
        _require_unique(self.writes, "cell writes")
        _require_unique(self.diagnostic_codes, "cell diagnostic codes")

        if any(statement.location.cell_index != self.index for statement in self.statements):
            msg = "statement locations must reference their containing cell"
            raise ValueError(msg)
        if any(call.location.cell_index != self.index for call in self.calls):
            msg = "call locations must reference their containing cell"
            raise ValueError(msg)
        if any(import_.location.cell_index != self.index for import_ in self.imports):
            msg = "import locations must reference their containing cell"
            raise ValueError(msg)

        known_call_ids = {call.id for call in self.calls}
        referenced_call_ids = {
            call_id for statement in self.statements for call_id in statement.call_ids
        }
        if not referenced_call_ids <= known_call_ids:
            msg = "statements must reference calls declared by their containing cell"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class SymbolAccess:
    """Reference from a symbol to a source statement."""

    cell_index: int
    statement_id: str

    def __post_init__(self) -> None:
        if self.cell_index < 0:
            msg = "cell_index must be greater than or equal to zero"
            raise ValueError(msg)
        _require_non_empty(self.statement_id, "statement_id")


@dataclass(frozen=True, slots=True)
class SymbolFacts:
    """Definitions and reads recorded for one Python name."""

    name: str
    kind: SymbolKind
    definitions: tuple[SymbolAccess, ...] = ()
    reads: tuple[SymbolAccess, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "name")
        if self.kind is not SymbolKind.UNKNOWN and not self.definitions:
            msg = "known symbols require at least one definition"
            raise ValueError(msg)
        if self.kind is SymbolKind.UNKNOWN and self.definitions:
            msg = "unknown symbols must not contain definitions"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DependencyFacts:
    """Resolved cross-cell name-flow edge."""

    id: str
    symbol: str
    producer: SymbolAccess
    consumer: SymbolAccess
    resolution: str = "most_recent_definition"

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "id")
        _require_non_empty(self.symbol, "symbol")
        _require_non_empty(self.resolution, "resolution")
        if self.producer.cell_index >= self.consumer.cell_index:
            msg = "a dependency producer must precede its consumer cell"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class NotebookMetadata:
    """Portable identity and format metadata for the source notebook."""

    path: str
    nbformat: int
    nbformat_minor: int
    language: str
    kernel_name: str | None
    cell_count: int
    content_sha256: str

    def __post_init__(self) -> None:
        _require_non_empty(self.path, "path")
        _require_non_empty(self.language, "language")
        if PurePosixPath(self.path).is_absolute():
            msg = "notebook path must be relative"
            raise ValueError(msg)
        if "\\" in self.path:
            msg = "notebook path must use POSIX separators"
            raise ValueError(msg)
        if self.nbformat < 1 or self.nbformat_minor < 0:
            msg = "notebook format versions must be non-negative and use a positive major version"
            raise ValueError(msg)
        if self.cell_count < 0:
            msg = "cell_count must be greater than or equal to zero"
            raise ValueError(msg)
        if len(self.content_sha256) != SHA256_HEX_LENGTH or any(
            character not in hexdigits for character in self.content_sha256
        ):
            msg = "content_sha256 must be a 64-character hexadecimal digest"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class NotebookFacts:
    """Canonical deterministic facts extracted from one notebook."""

    schema_version: str
    analyzer_version: str
    notebook: NotebookMetadata
    cells: tuple[CellFacts, ...]
    symbols: tuple[SymbolFacts, ...] = ()
    dependencies: tuple[DependencyFacts, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.schema_version, "schema_version")
        _require_non_empty(self.analyzer_version, "analyzer_version")
        if self.notebook.cell_count != len(self.cells):
            msg = "notebook cell_count must match the number of cells"
            raise ValueError(msg)

        expected_indexes = tuple(range(len(self.cells)))
        actual_indexes = tuple(cell.index for cell in self.cells)
        if actual_indexes != expected_indexes:
            msg = "cells must be ordered and indexed contiguously from zero"
            raise ValueError(msg)

        _require_unique(tuple(cell.id for cell in self.cells), "cell IDs")
        _require_unique(tuple(symbol.name for symbol in self.symbols), "symbol names")
        _require_unique(tuple(dependency.id for dependency in self.dependencies), "dependency IDs")
        _require_unique(tuple(diagnostic.id for diagnostic in self.diagnostics), "diagnostic IDs")

        known_statement_ids = {statement.id for cell in self.cells for statement in cell.statements}
        referenced_statement_ids = {
            access.statement_id
            for symbol in self.symbols
            for access in (*symbol.definitions, *symbol.reads)
        }
        referenced_statement_ids.update(
            access.statement_id
            for dependency in self.dependencies
            for access in (dependency.producer, dependency.consumer)
        )
        if not referenced_statement_ids <= known_statement_ids:
            msg = "symbol and dependency accesses must reference declared statements"
            raise ValueError(msg)

        known_diagnostic_codes = {diagnostic.code for diagnostic in self.diagnostics}
        referenced_diagnostic_codes = {
            code for cell in self.cells for code in cell.diagnostic_codes
        }
        if not referenced_diagnostic_codes <= known_diagnostic_codes:
            msg = "cells must reference declared diagnostic codes"
            raise ValueError(msg)
