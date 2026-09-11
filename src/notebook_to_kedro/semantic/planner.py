"""Deterministic task planning from notebook facts."""

from __future__ import annotations

import posixpath
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from notebook_to_kedro.ir import (
    CallFacts,
    CatalogDataset,
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
            imports=_imports(facts),
            catalog_datasets=_catalog_datasets(facts),
            blocking_diagnostic_codes=blocking_codes,
        )

    catalog_datasets = _catalog_datasets(facts)
    catalog_dataset_names = {dataset.name for dataset in catalog_datasets}
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
                cell, import_names, data_symbols, dependency_inputs_by_cell, catalog_dataset_names
            )
        )
        is not None
    )
    return ConversionPlan(
        schema_version="1.0",
        planner_version=PLANNER_VERSION,
        notebook_path=facts.notebook.path,
        task_candidates=candidates,
        imports=_imports(facts),
        catalog_datasets=catalog_datasets,
    )


def _task_candidate(
    cell: CellFacts,
    import_names: set[str],
    data_symbols: set[str],
    dependency_inputs_by_cell: dict[int, set[str]],
    catalog_dataset_names: set[str],
) -> TaskCandidate | None:
    if cell.kind is not CellKind.CODE or not cell.statements:
        return None

    outputs = tuple(
        name
        for name in cell.writes
        if name in data_symbols and name not in import_names and name not in catalog_dataset_names
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


def _imports(facts: NotebookFacts) -> tuple[str, ...]:
    return tuple(
        statement.source
        for cell in facts.cells
        for statement in cell.statements
        if statement.ast_type in {"Import", "ImportFrom"}
    )


def _catalog_datasets(facts: NotebookFacts) -> tuple[CatalogDataset, ...]:
    datasets: list[CatalogDataset] = []
    for cell in facts.cells:
        calls_by_id = {call.id: call for call in cell.calls}
        for statement in cell.statements:
            if len(statement.writes) != 1 or len(statement.call_ids) != 1:
                continue
            call = calls_by_id[statement.call_ids[0]]
            if _is_csv_loader_call(call):
                source_filepath = _source_filepath(facts.notebook.path, _csv_filepath(call))
                datasets.append(
                    CatalogDataset(
                        name=statement.writes[0],
                        type="kedro_datasets.pandas.CSVDataset",
                        filepath=f"data/01_raw/{PurePosixPath(source_filepath).name}",
                        source_filepath=source_filepath,
                    )
                )
    return tuple(datasets)


def _is_csv_loader_call(call: CallFacts) -> bool:
    return (
        call.qualified_name.endswith(".read_csv")
        and bool(call.literal_arguments)
        and isinstance(call.literal_arguments[0], str)
    )


def _csv_filepath(call: CallFacts) -> str:
    return str(call.literal_arguments[0])


def _source_filepath(notebook_path: str, filepath: str) -> str:
    source_path = PurePosixPath(filepath)
    if source_path.is_absolute():
        return source_path.as_posix()
    return posixpath.normpath((PurePosixPath(notebook_path).parent / source_path).as_posix())


def _ordered_names(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))
