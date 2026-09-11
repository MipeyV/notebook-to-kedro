"""End-to-end equivalence tests for generated Kedro pipelines."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

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

    from notebook_to_kedro.ir import ConversionPlan

REFERENCE_NOTEBOOK = Path(__file__).parents[1] / "fixtures" / "notebooks" / "simple_training.ipynb"
FILE_BACKED_NOTEBOOK = (
    Path(__file__).parents[1] / "fixtures" / "notebooks" / "file_backed_training.ipynb"
)
SCALED_NOTEBOOK = Path(__file__).parents[1] / "fixtures" / "notebooks" / "scaled_training.ipynb"
PANDAS_PREPROCESSING_NOTEBOOK = (
    Path(__file__).parents[1] / "fixtures" / "notebooks" / "pandas_preprocessing_training.ipynb"
)


@pytest.mark.end_to_end
def test_generated_kedro_pipeline_matches_reference_notebook_accuracy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generated Kedro pipeline reproduces the reference notebook accuracy."""
    notebook_accuracy = _reference_notebook_accuracy()
    output_path = tmp_path / "generated"

    plan = plan_notebook_path(REFERENCE_NOTEBOOK)
    generate_kedro_project(plan, output_path, package_name="generated_reference")
    monkeypatch.syspath_prepend(str(output_path / "src"))

    pipeline = _generated_pipeline("generated_reference.pipelines.notebook_pipeline")
    catalog = _memory_catalog(pipeline, plan)

    SequentialRunner().run(pipeline, catalog)

    assert catalog.load("accuracy") == pytest.approx(notebook_accuracy)


@pytest.mark.end_to_end
def test_generated_kedro_pipeline_matches_file_backed_notebook_accuracy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A generated Kedro pipeline can consume catalog-backed tabular input."""
    notebook_accuracy = _reference_notebook_accuracy(FILE_BACKED_NOTEBOOK)
    output_path = tmp_path / "generated"

    plan = plan_notebook_path(FILE_BACKED_NOTEBOOK)
    generate_kedro_project(plan, output_path, package_name="generated_file_backed")
    generated_csv = output_path / "data" / "01_raw" / "binary_classification.csv"
    assert generated_csv.exists()
    monkeypatch.syspath_prepend(str(output_path / "src"))

    pipeline = _generated_pipeline("generated_file_backed.pipelines.notebook_pipeline")
    catalog = _memory_catalog(pipeline, plan)
    pandas = importlib.import_module("pandas")
    read_csv = cast("Any", pandas).read_csv
    catalog.save("df", read_csv(generated_csv))

    SequentialRunner().run(pipeline, catalog)

    assert catalog.load("accuracy") == pytest.approx(notebook_accuracy)


@pytest.mark.end_to_end
def test_generated_kedro_pipeline_matches_scaled_notebook_accuracy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A generated Kedro pipeline reproduces a notebook with sklearn scaling."""
    notebook_accuracy = _reference_notebook_accuracy(SCALED_NOTEBOOK)
    output_path = tmp_path / "generated"

    plan = plan_notebook_path(SCALED_NOTEBOOK)
    generate_kedro_project(plan, output_path, package_name="generated_scaled")
    monkeypatch.syspath_prepend(str(output_path / "src"))

    pipeline = _generated_pipeline("generated_scaled.pipelines.notebook_pipeline")
    catalog = _memory_catalog(pipeline, plan)

    SequentialRunner().run(pipeline, catalog)

    assert catalog.load("accuracy") == pytest.approx(notebook_accuracy)


@pytest.mark.end_to_end
def test_generated_kedro_pipeline_matches_pandas_preprocessing_notebook_accuracy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A generated Kedro pipeline reproduces a notebook with pandas preprocessing."""
    notebook_accuracy = _reference_notebook_accuracy(PANDAS_PREPROCESSING_NOTEBOOK)
    output_path = tmp_path / "generated"

    plan = plan_notebook_path(PANDAS_PREPROCESSING_NOTEBOOK)
    generate_kedro_project(plan, output_path, package_name="generated_pandas_preprocessing")
    monkeypatch.syspath_prepend(str(output_path / "src"))

    pipeline = _generated_pipeline("generated_pandas_preprocessing.pipelines.notebook_pipeline")
    catalog = _memory_catalog(pipeline, plan)

    SequentialRunner().run(pipeline, catalog)

    assert catalog.load("accuracy") == pytest.approx(notebook_accuracy)


def _reference_notebook_accuracy(notebook_path: Path = REFERENCE_NOTEBOOK) -> float:
    notebook = cast(
        "NotebookNode",
        nbformat.read(notebook_path, as_version=4),  # type: ignore[no-untyped-call]
    )
    executed = NotebookClient(
        notebook,
        timeout=60,
        kernel_name="python3",
        allow_errors=False,
    ).execute(cwd=str(notebook_path.parent))
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


def _memory_catalog(pipeline: Pipeline, plan: ConversionPlan) -> DataCatalog:
    catalog = DataCatalog({name: MemoryDataset() for name in pipeline.datasets()})
    for parameter in plan.parameters:
        catalog.save(f"params:{parameter.name}", parameter.value)
    return catalog
