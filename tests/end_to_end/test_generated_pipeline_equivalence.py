"""End-to-end equivalence tests for generated Kedro pipelines."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, cast

import nbformat
import pytest
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner
from nbclient import NotebookClient
from nbformat import NotebookNode

from notebook_to_kedro import generate_kedro_project, plan_notebook_path

if TYPE_CHECKING:
    from collections.abc import Callable

    from kedro.pipeline import Pipeline

REFERENCE_NOTEBOOK = Path(__file__).parents[1] / "fixtures" / "notebooks" / "simple_training.ipynb"


@pytest.mark.end_to_end
def test_generated_kedro_pipeline_matches_reference_notebook_accuracy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generated Kedro pipeline reproduces the reference notebook accuracy."""
    notebook_accuracy = _reference_notebook_accuracy()
    output_path = tmp_path / "generated"

    generate_kedro_project(
        plan_notebook_path(REFERENCE_NOTEBOOK),
        output_path,
        package_name="generated_reference",
    )
    monkeypatch.syspath_prepend(str(output_path / "src"))

    pipeline = _generated_pipeline("generated_reference.pipelines.notebook_pipeline")
    catalog = DataCatalog({name: MemoryDataset() for name in pipeline.datasets()})

    SequentialRunner().run(pipeline, catalog)

    assert catalog.load("accuracy") == pytest.approx(notebook_accuracy)


def _reference_notebook_accuracy() -> float:
    notebook = cast(
        "NotebookNode",
        nbformat.read(REFERENCE_NOTEBOOK, as_version=4),  # type: ignore[no-untyped-call]
    )
    executed = NotebookClient(
        notebook,
        timeout=60,
        kernel_name="python3",
        allow_errors=False,
    ).execute(cwd=str(REFERENCE_NOTEBOOK.parent))
    last_code_cell = next(cell for cell in reversed(executed.cells) if cell.cell_type == "code")
    result = next(
        output["data"]["text/plain"]
        for output in reversed(last_code_cell.outputs)
        if output.output_type == "execute_result"
    )
    return float(result)


def _generated_pipeline(module_name: str) -> Pipeline:
    pipeline_module = importlib.import_module(module_name)
    create_pipeline = cast("Callable[[], Pipeline]", pipeline_module.create_pipeline)
    return create_pipeline()
