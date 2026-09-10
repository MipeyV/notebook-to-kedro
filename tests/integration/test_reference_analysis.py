"""Integration tests for loading and statically analyzing the reference notebook."""

from pathlib import Path

from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.ir import CellKind
from notebook_to_kedro.notebook import load_notebook

REFERENCE_NOTEBOOK = Path(__file__).parents[1] / "fixtures" / "notebooks" / "simple_training.ipynb"


def test_reference_notebook_static_analysis_extracts_reviewed_facts() -> None:
    """The reference notebook can be loaded and analyzed without execution."""
    loaded_notebook = load_notebook(REFERENCE_NOTEBOOK)
    facts = analyze_notebook(loaded_notebook)
    code_cells = [cell for cell in facts.cells if cell.kind is CellKind.CODE]
    symbols = {symbol.name: symbol for symbol in facts.symbols}

    assert len(facts.cells) == 12
    assert len(code_cells) == 7
    dependency_symbols = {dependency.symbol for dependency in facts.dependencies}
    assert facts.notebook.path == "tests/fixtures/notebooks/simple_training.ipynb"
    assert {"load_iris", "train_test_split", "RandomForestClassifier"} <= symbols.keys()
    assert {"df", "X", "y", "X_train", "model", "predictions", "accuracy"} <= symbols.keys()
    assert {
        "df",
        "X",
        "y",
        "X_train",
        "y_train",
        "model",
        "X_test",
        "predictions",
    } <= dependency_symbols
    assert "DF003" in {diagnostic.code for diagnostic in facts.diagnostics}
    assert any(call.qualified_name == "model.fit" for cell in code_cells for call in cell.calls)
