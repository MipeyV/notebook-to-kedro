"""Derived cell views keep source facts intact while assigning each instruction once."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from notebook_to_kedro.ir import CellFacts, NotebookFacts


def task_cells(
    facts: NotebookFacts, catalog_ids: frozenset[str], catalog_names: tuple[str, ...]
) -> tuple[tuple[CellFacts, ...], dict[str, tuple[str, ...]]]:
    """Separate shared imports/catalog instructions from unchanged business statements.

    The high-level audit independently validates promotion order, reader semantics and graph
    eligibility. These views alone are proposals, never altered analysis evidence.
    """
    cells = []
    relocated_inputs = {}
    for cell in facts.cells:
        retained = tuple(
            statement
            for statement in cell.statements
            if statement.ast_type not in {"Import", "ImportFrom"}
            and statement.id not in catalog_ids
        )
        if len(retained) == len(cell.statements):
            cells.append(cell)
            continue
        calls = {call_id for statement in retained for call_id in statement.call_ids}
        cells.append(
            replace(
                cell,
                source="\n".join(statement.source for statement in retained),
                statements=retained,
                reads=tuple(
                    dict.fromkeys(name for statement in retained for name in statement.reads)
                ),
                writes=tuple(
                    dict.fromkeys(name for statement in retained for name in statement.writes)
                ),
                imports=(),
                calls=tuple(call for call in cell.calls if call.id in calls),
            )
        )
        if retained:
            # Force the promoted boundary read even when its first task overwrites/ignores it.
            relocated_inputs[cell.id] = catalog_names
    return tuple(cells), relocated_inputs
