"""Deterministic task planning from notebook facts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notebook_to_kedro.ir import (
    CellFacts,
    CellKind,
    ConversionPlan,
    NotebookFacts,
    SymbolKind,
    TaskCandidate,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

PLANNER_VERSION = "0.1.0"


def plan_tasks(facts: NotebookFacts) -> ConversionPlan:
    """Propose one task candidate per analyzable code cell with data outputs."""
    blocking_codes = _blocking_diagnostic_codes(facts)
    if blocking_codes:
        return ConversionPlan(
            schema_version="1.0",
            planner_version=PLANNER_VERSION,
            notebook_path=facts.notebook.path,
            task_candidates=(),
            blocking_diagnostic_codes=blocking_codes,
        )

    import_names = {symbol.name for symbol in facts.symbols if symbol.kind is SymbolKind.IMPORT}
    data_symbols = {symbol.name for symbol in facts.symbols if symbol.kind is not SymbolKind.IMPORT}
    dependency_inputs_by_cell: dict[int, set[str]] = {}
    for dependency in facts.dependencies:
        dependency_inputs_by_cell.setdefault(dependency.consumer.cell_index, set()).add(
            dependency.symbol
        )

    candidates = tuple(
        candidate
        for cell in facts.cells
        if (
            candidate := _task_candidate(
                cell, import_names, data_symbols, dependency_inputs_by_cell
            )
        )
        is not None
    )
    return ConversionPlan(
        schema_version="1.0",
        planner_version=PLANNER_VERSION,
        notebook_path=facts.notebook.path,
        task_candidates=candidates,
    )


def _task_candidate(
    cell: CellFacts,
    import_names: set[str],
    data_symbols: set[str],
    dependency_inputs_by_cell: dict[int, set[str]],
) -> TaskCandidate | None:
    if cell.kind is not CellKind.CODE or not cell.statements:
        return None

    outputs = tuple(
        name for name in cell.writes if name in data_symbols and name not in import_names
    )
    if not outputs:
        return None

    dependency_inputs = dependency_inputs_by_cell.get(cell.index, set())
    inputs = tuple(
        name
        for name in cell.reads
        if name in dependency_inputs
        or (name not in outputs and name in data_symbols and name not in import_names)
    )
    return TaskCandidate(
        id=f"task-{cell.index:04d}",
        name=f"cell_{cell.index:04d}",
        source_cell_ids=(cell.id,),
        statement_ids=tuple(statement.id for statement in cell.statements),
        inputs=_ordered_names(inputs),
        outputs=outputs,
        source=cell.source,
        diagnostic_codes=cell.diagnostic_codes,
    )


def _blocking_diagnostic_codes(facts: NotebookFacts) -> tuple[str, ...]:
    return _ordered_names(
        diagnostic.code for diagnostic in facts.diagnostics if diagnostic.blocking
    )


def _ordered_names(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))
