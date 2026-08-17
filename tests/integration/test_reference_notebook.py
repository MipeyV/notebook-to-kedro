"""Execution tests for the known-good reference notebook."""

from pathlib import Path
from typing import cast

import nbformat
import pytest
from nbclient import NotebookClient
from nbformat import NotebookNode

REFERENCE_NOTEBOOK = Path(__file__).parents[1] / "fixtures" / "notebooks" / "simple_training.ipynb"


def _read_reference_notebook() -> NotebookNode:
    return cast(
        "NotebookNode",
        nbformat.read(REFERENCE_NOTEBOOK, as_version=4),  # type: ignore[no-untyped-call]
    )


def _execute_reference_notebook() -> NotebookNode:
    notebook = _read_reference_notebook()
    return NotebookClient(
        notebook,
        timeout=60,
        kernel_name="python3",
        allow_errors=False,
    ).execute(cwd=str(REFERENCE_NOTEBOOK.parent))


@pytest.mark.integration
def test_reference_notebook_executes_with_expected_accuracy() -> None:
    """The reference workflow remains executable and deterministic."""
    executed = _execute_reference_notebook()
    last_code_cell = next(cell for cell in reversed(executed.cells) if cell.cell_type == "code")
    result = next(
        output["data"]["text/plain"]
        for output in reversed(last_code_cell.outputs)
        if output.output_type == "execute_result"
    )

    assert float(result) == pytest.approx(0.9)


def test_reference_notebook_is_stored_without_execution_outputs() -> None:
    """Generated notebook state is not committed as part of the fixture."""
    notebook = _read_reference_notebook()
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]

    assert code_cells
    assert all(cell.execution_count is None for cell in code_cells)
    assert all(cell.outputs == [] for cell in code_cells)
