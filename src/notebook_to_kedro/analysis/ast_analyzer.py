"""Cell-level AST analysis without executing notebook code."""

from __future__ import annotations

import ast
import builtins
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

from notebook_to_kedro.analysis.dependencies import resolve_dependencies
from notebook_to_kedro.ir import (
    CallFacts,
    CellFacts,
    CellKind,
    Diagnostic,
    DiagnosticDetail,
    ImportFacts,
    ImportKind,
    KeywordArgument,
    NotebookFacts,
    NotebookMetadata,
    Severity,
    SourceLocation,
    StatementFacts,
)
from notebook_to_kedro.notebook import LoadedCell, LoadedNotebook, NotebookCellKind

BUILTIN_NAMES = frozenset(dir(builtins))
DYNAMIC_CALLS = frozenset({"exec", "eval", "compile", "globals", "locals"})
MUTATING_METHODS = frozenset({"fit", "fit_transform", "partial_fit"})


def analyze_notebook(notebook: LoadedNotebook) -> NotebookFacts:
    """Analyze loaded notebook cells and resolve source facts."""
    diagnostics: list[Diagnostic] = []
    analyzed_cells: list[CellFacts] = []

    for loaded_cell in notebook.cells:
        cell, cell_diagnostics = _analyze_cell(loaded_cell)
        analyzed_cells.append(cell)
        diagnostics.extend(cell_diagnostics)

    cells, symbols, dependencies, resolved_diagnostics = resolve_dependencies(
        tuple(analyzed_cells),
        tuple(diagnostics),
    )

    return NotebookFacts(
        schema_version="1.0",
        analyzer_version="0.1.0",
        notebook=NotebookMetadata(
            path=notebook.path,
            nbformat=notebook.nbformat,
            nbformat_minor=notebook.nbformat_minor,
            language=notebook.language,
            kernel_name=notebook.kernel_name,
            cell_count=notebook.cell_count,
            content_sha256=notebook.content_sha256,
        ),
        cells=cells,
        symbols=symbols,
        dependencies=dependencies,
        diagnostics=resolved_diagnostics,
    )


def _analyze_cell(cell: LoadedCell) -> tuple[CellFacts, tuple[Diagnostic, ...]]:
    if cell.kind is not NotebookCellKind.CODE:
        return (
            CellFacts(
                id=cell.id,
                index=cell.index,
                kind=_cell_kind(cell.kind),
                source=cell.source,
                execution_count=cell.execution_count,
            ),
            (),
        )

    magic_diagnostic = _magic_diagnostic(cell)
    if magic_diagnostic is not None:
        return (_empty_code_cell(cell, (magic_diagnostic.code,)), (magic_diagnostic,))

    try:
        module = ast.parse(cell.source)
    except SyntaxError as error:
        diagnostic = _syntax_diagnostic(cell, error)
        return (_empty_code_cell(cell, (diagnostic.code,)), (diagnostic,))

    statements: list[StatementFacts] = []
    imports: list[ImportFacts] = []
    calls: list[CallFacts] = []
    diagnostics: list[Diagnostic] = []
    diagnostic_codes: list[str] = []
    for statement_index, statement in enumerate(module.body):
        statement_id = f"{cell.id}-stmt-{statement_index:04d}"
        statement_calls = _calls_for_statement(cell, statement, statement_index)
        calls.extend(statement_calls)
        statement_imports = _imports_for_statement(cell.index, statement)
        imports.extend(statement_imports)
        reads = _ordered_names(_statement_reads(statement))
        writes = _ordered_names(_statement_writes(statement))
        statement_diagnostics = _diagnostics_for_statement(cell, statement, statement_index)
        diagnostics.extend(statement_diagnostics)
        diagnostic_codes.extend(diagnostic.code for diagnostic in statement_diagnostics)
        statements.append(
            StatementFacts(
                id=statement_id,
                index=statement_index,
                ast_type=type(statement).__name__,
                source=_source_segment(cell.source, statement),
                location=_location(cell.index, statement),
                reads=reads,
                writes=writes,
                call_ids=tuple(call.id for call in statement_calls),
                conditional=False,
            )
        )

    return (
        CellFacts(
            id=cell.id,
            index=cell.index,
            kind=CellKind.CODE,
            source=cell.source,
            execution_count=cell.execution_count,
            statements=tuple(statements),
            reads=_ordered_names(name for statement in statements for name in statement.reads),
            writes=_ordered_names(name for statement in statements for name in statement.writes),
            imports=tuple(imports),
            calls=tuple(calls),
            diagnostic_codes=_ordered_names(diagnostic_codes),
        ),
        tuple(diagnostics),
    )


def _empty_code_cell(cell: LoadedCell, diagnostic_codes: tuple[str, ...]) -> CellFacts:
    return CellFacts(
        id=cell.id,
        index=cell.index,
        kind=CellKind.CODE,
        source=cell.source,
        execution_count=cell.execution_count,
        diagnostic_codes=diagnostic_codes,
    )


def _magic_diagnostic(cell: LoadedCell) -> Diagnostic | None:
    for line_number, line in enumerate(cell.source.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("%", "!")):
            return Diagnostic(
                id=f"diagnostic-{cell.index:04d}-0000",
                code="PY002",
                severity=Severity.ERROR,
                message="Jupyter magic or shell escape is not supported.",
                blocking=True,
                location=SourceLocation(cell.index, line_number, line.index(stripped[0])),
            )
    return None


def _syntax_diagnostic(cell: LoadedCell, error: SyntaxError) -> Diagnostic:
    return Diagnostic(
        id=f"diagnostic-{cell.index:04d}-0000",
        code="PY001",
        severity=Severity.ERROR,
        message="Code cell contains invalid Python syntax.",
        blocking=True,
        location=SourceLocation(
            cell.index,
            error.lineno,
            error.offset - 1 if error.offset else None,
        ),
        details=(DiagnosticDetail("syntax_error", error.msg),),
    )


def _diagnostics_for_statement(
    cell: LoadedCell, statement: ast.stmt, statement_index: int
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for call_index, call in enumerate(_iter_calls(statement)):
        qualified_name = _qualified_name(call.func)
        if qualified_name in DYNAMIC_CALLS:
            diagnostics.append(
                Diagnostic(
                    id=f"diagnostic-{cell.index:04d}-{statement_index:04d}-{call_index:04d}",
                    code="PY003",
                    severity=Severity.ERROR,
                    message="Dynamic execution or namespace mutation is not supported.",
                    blocking=True,
                    location=_location(cell.index, call),
                    details=(DiagnosticDetail("qualified_call", qualified_name),),
                )
            )
            continue
        receiver, method = _method_parts(call.func)
        if receiver is not None and method in MUTATING_METHODS:
            diagnostics.append(
                Diagnostic(
                    id=f"diagnostic-{cell.index:04d}-{statement_index:04d}-{call_index:04d}",
                    code="DF003",
                    severity=Severity.WARNING,
                    message=f"Method call may mutate '{receiver}'.",
                    blocking=False,
                    location=_location(cell.index, call),
                    related_symbol=receiver,
                    details=(DiagnosticDetail("qualified_call", f"{receiver}.{method}"),),
                )
            )
    return tuple(diagnostics)


def _imports_for_statement(cell_index: int, statement: ast.stmt) -> tuple[ImportFacts, ...]:
    if isinstance(statement, ast.Import):
        return tuple(
            ImportFacts(
                kind=ImportKind.IMPORT,
                module=alias.name,
                bound_name=alias.asname or alias.name.split(".", maxsplit=1)[0],
                alias=alias.asname,
                location=_location(cell_index, statement),
            )
            for alias in statement.names
        )
    if isinstance(statement, ast.ImportFrom) and statement.module is not None:
        return tuple(
            ImportFacts(
                kind=ImportKind.FROM,
                module=statement.module,
                name=alias.name,
                bound_name=alias.asname or alias.name,
                alias=alias.asname,
                location=_location(cell_index, statement),
            )
            for alias in statement.names
        )
    return ()


def _calls_for_statement(
    cell: LoadedCell, statement: ast.stmt, statement_index: int
) -> tuple[CallFacts, ...]:
    calls: list[CallFacts] = []
    for call_index, call in enumerate(_iter_calls(statement)):
        receiver, method = _method_parts(call.func)
        calls.append(
            CallFacts(
                id=f"{cell.id}-call-{statement_index:04d}-{call_index:04d}",
                qualified_name=_qualified_name(call.func),
                receiver=receiver,
                method=method,
                positional_argument_sources=tuple(
                    _source_segment(cell.source, argument) for argument in call.args
                ),
                keyword_arguments=tuple(
                    KeywordArgument(keyword.arg, _source_segment(cell.source, keyword.value))
                    for keyword in call.keywords
                    if keyword.arg is not None
                ),
                literal_arguments=_literal_arguments(call),
                possible_mutation_targets=(receiver,)
                if receiver is not None and method in MUTATING_METHODS
                else (),
                location=_location(cell.index, call),
            )
        )
    return tuple(calls)


def _literal_arguments(call: ast.Call) -> tuple[str | int | float | bool | None, ...]:
    values: list[str | int | float | bool | None] = []
    for argument in (*call.args, *(keyword.value for keyword in call.keywords)):
        try:
            value = ast.literal_eval(argument)
        except (ValueError, TypeError):
            continue
        if value is None or isinstance(value, str | int | float | bool):
            values.append(value)
    return tuple(values)


def _statement_reads(statement: ast.stmt) -> tuple[str, ...]:
    if isinstance(statement, ast.Import | ast.ImportFrom):
        return ()
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return ()
    reads: list[str] = []
    for node in ast.walk(statement):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id not in BUILTIN_NAMES
        ):
            reads.append(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            reads.extend(_root_name(node.value))
    return tuple(reads)


def _statement_writes(statement: ast.stmt) -> tuple[str, ...]:
    if isinstance(statement, ast.Import):
        return tuple(
            alias.asname or alias.name.split(".", maxsplit=1)[0] for alias in statement.names
        )
    if isinstance(statement, ast.ImportFrom):
        return tuple(alias.asname or alias.name for alias in statement.names)
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return (statement.name,)
    return tuple(
        node.id
        for node in ast.walk(statement)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    )


def _iter_calls(statement: ast.stmt) -> Iterable[ast.Call]:
    return (node for node in ast.walk(statement) if isinstance(node, ast.Call))


def _method_parts(node: ast.expr) -> tuple[str | None, str | None]:
    if not isinstance(node, ast.Attribute):
        return (None, None)
    receiver = _source_receiver(node.value)
    if receiver is None:
        return (None, None)
    return (receiver, node.attr)


def _qualified_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _qualified_name(node.func)
    return type(node).__name__


def _source_receiver(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _qualified_name(node)
    return None


def _root_name(node: ast.expr) -> tuple[str, ...]:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute | ast.Subscript):
        return _root_name(node.value)
    return ()


def _source_segment(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def _location(cell_index: int, node: ast.AST) -> SourceLocation:
    return SourceLocation(
        cell_index=cell_index,
        start_line=getattr(node, "lineno", None),
        start_column=getattr(node, "col_offset", None),
        end_line=getattr(node, "end_lineno", None),
        end_column=getattr(node, "end_col_offset", None),
    )


def _cell_kind(kind: NotebookCellKind) -> CellKind:
    if kind is NotebookCellKind.CODE:
        return CellKind.CODE
    if kind is NotebookCellKind.MARKDOWN:
        return CellKind.MARKDOWN
    return CellKind.RAW


def _ordered_names(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))
