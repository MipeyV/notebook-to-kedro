"""Resolve cross-cell symbol facts and dependencies from analyzed cells."""

from __future__ import annotations

from collections import defaultdict

from notebook_to_kedro.ir import (
    CellFacts,
    DependencyFacts,
    Diagnostic,
    DiagnosticDetail,
    Severity,
    SourceLocation,
    SymbolAccess,
    SymbolFacts,
    SymbolKind,
)


def resolve_dependencies(
    cells: tuple[CellFacts, ...], diagnostics: tuple[Diagnostic, ...]
) -> tuple[
    tuple[CellFacts, ...],
    tuple[SymbolFacts, ...],
    tuple[DependencyFacts, ...],
    tuple[Diagnostic, ...],
]:
    """Resolve symbols, cross-cell dependencies, and dataflow diagnostics."""
    definitions, reads, symbol_kinds = _collect_symbol_accesses(cells)
    dependencies: list[DependencyFacts] = []
    extra_diagnostics: list[Diagnostic] = []
    diagnostic_codes_by_cell: dict[int, list[str]] = defaultdict(list)
    latest_data_definition: dict[str, SymbolAccess] = {}
    import_names = {import_.bound_name for cell in cells for import_ in cell.imports}

    for cell in cells:
        for statement in cell.statements:
            access = SymbolAccess(cell.index, statement.id)
            for read_name in statement.reads:
                producer = latest_data_definition.get(read_name)
                if producer is not None and producer.cell_index < access.cell_index:
                    dependencies.append(
                        DependencyFacts(
                            id=f"dep-{len(dependencies):04d}",
                            symbol=read_name,
                            producer=producer,
                            consumer=access,
                        )
                    )
                elif producer is not None:
                    continue
                elif read_name not in import_names:
                    diagnostic = _unresolved_read_diagnostic(
                        len(diagnostics) + len(extra_diagnostics),
                        read_name,
                        access,
                    )
                    extra_diagnostics.append(diagnostic)
                    diagnostic_codes_by_cell[cell.index].append(diagnostic.code)

            for write_name in statement.writes:
                if write_name in latest_data_definition and write_name not in import_names:
                    diagnostic = _redefinition_diagnostic(
                        len(diagnostics) + len(extra_diagnostics),
                        write_name,
                        access,
                    )
                    extra_diagnostics.append(diagnostic)
                    diagnostic_codes_by_cell[cell.index].append(diagnostic.code)
                if symbol_kinds.get(write_name) is not SymbolKind.IMPORT:
                    latest_data_definition[write_name] = access

    resolved_cells = _with_cell_diagnostic_codes(cells, diagnostic_codes_by_cell)
    return (
        resolved_cells,
        _build_symbols(definitions, reads, symbol_kinds),
        tuple(dependencies),
        (*diagnostics, *extra_diagnostics),
    )


def _collect_symbol_accesses(
    cells: tuple[CellFacts, ...],
) -> tuple[dict[str, list[SymbolAccess]], dict[str, list[SymbolAccess]], dict[str, SymbolKind]]:
    definitions: dict[str, list[SymbolAccess]] = defaultdict(list)
    reads: dict[str, list[SymbolAccess]] = defaultdict(list)
    symbol_kinds: dict[str, SymbolKind] = {}
    for cell in cells:
        import_names = {import_.bound_name for import_ in cell.imports}
        for statement in cell.statements:
            access = SymbolAccess(cell.index, statement.id)
            for name in statement.writes:
                definitions[name].append(access)
                symbol_kind = _symbol_kind_for_write(name, statement.ast_type, import_names)
                symbol_kinds.setdefault(name, symbol_kind)
            for name in statement.reads:
                reads[name].append(access)
    return definitions, reads, symbol_kinds


def _build_symbols(
    definitions: dict[str, list[SymbolAccess]],
    reads: dict[str, list[SymbolAccess]],
    symbol_kinds: dict[str, SymbolKind],
) -> tuple[SymbolFacts, ...]:
    names = sorted(set(definitions) | set(reads))
    return tuple(
        SymbolFacts(
            name=name,
            kind=symbol_kinds.get(name, SymbolKind.UNKNOWN),
            definitions=tuple(definitions.get(name, ())),
            reads=tuple(reads.get(name, ())),
        )
        for name in names
    )


def _symbol_kind_for_write(name: str, ast_type: str, import_names: set[str]) -> SymbolKind:
    if name in import_names:
        return SymbolKind.IMPORT
    if ast_type in {"FunctionDef", "AsyncFunctionDef"}:
        return SymbolKind.FUNCTION
    if ast_type == "ClassDef":
        return SymbolKind.CLASS
    return SymbolKind.DATA


def _unresolved_read_diagnostic(index: int, symbol: str, access: SymbolAccess) -> Diagnostic:
    return Diagnostic(
        id=f"diagnostic-{index:04d}",
        code="DF001",
        severity=Severity.WARNING,
        message=f"Name '{symbol}' is read without a known producer or binding.",
        blocking=False,
        location=SourceLocation(access.cell_index),
        related_symbol=symbol,
    )


def _redefinition_diagnostic(index: int, symbol: str, access: SymbolAccess) -> Diagnostic:
    return Diagnostic(
        id=f"diagnostic-{index:04d}",
        code="DF002",
        severity=Severity.WARNING,
        message=f"Top-level name '{symbol}' is redefined.",
        blocking=False,
        location=SourceLocation(access.cell_index),
        related_symbol=symbol,
        details=(DiagnosticDetail("statement_id", access.statement_id),),
    )


def _with_cell_diagnostic_codes(
    cells: tuple[CellFacts, ...], diagnostic_codes_by_cell: dict[int, list[str]]
) -> tuple[CellFacts, ...]:
    resolved_cells: list[CellFacts] = []
    for cell in cells:
        diagnostic_codes = _ordered_codes(
            (*cell.diagnostic_codes, *diagnostic_codes_by_cell.get(cell.index, ()))
        )
        resolved_cells.append(
            CellFacts(
                id=cell.id,
                index=cell.index,
                kind=cell.kind,
                source=cell.source,
                execution_count=cell.execution_count,
                statements=cell.statements,
                reads=cell.reads,
                writes=cell.writes,
                imports=cell.imports,
                calls=cell.calls,
                diagnostic_codes=diagnostic_codes,
            )
        )
    return tuple(resolved_cells)


def _ordered_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(codes))
