"""Unit tests for cell-level AST analysis."""

from __future__ import annotations

import ast

from notebook_to_kedro.analysis import analyze_notebook, ast_analyzer
from notebook_to_kedro.ir import CellKind, ImportKind, Severity, SymbolKind
from notebook_to_kedro.notebook import LoadedCell, LoadedNotebook, NotebookCellKind

SHA256 = "a" * 64


def _loaded_notebook(*cells: LoadedCell) -> LoadedNotebook:
    return LoadedNotebook(
        path="tests/fixtures/notebooks/example.ipynb",
        nbformat=4,
        nbformat_minor=5,
        language="python",
        kernel_name="python3",
        content_sha256=SHA256,
        cells=cells,
    )


def _code_cell(source: str, index: int = 0) -> LoadedCell:
    return LoadedCell(
        id=f"cell-{index:04d}",
        index=index,
        kind=NotebookCellKind.CODE,
        source=source,
    )


def test_analyze_notebook_preserves_metadata_and_non_code_cells() -> None:
    """Markdown and raw cells are preserved without Python facts."""
    notebook = _loaded_notebook(
        LoadedCell("cell-0000", 0, NotebookCellKind.MARKDOWN, "# Heading"),
        LoadedCell("cell-0001", 1, NotebookCellKind.RAW, "raw text"),
    )

    facts = analyze_notebook(notebook)

    assert facts.notebook.path == notebook.path
    assert facts.notebook.content_sha256 == SHA256
    assert tuple(cell.kind for cell in facts.cells) == (CellKind.MARKDOWN, CellKind.RAW)
    assert all(not cell.statements for cell in facts.cells)
    assert facts.symbols == ()
    assert facts.dependencies == ()


def test_analyze_notebook_extracts_imports_assignments_reads_and_calls() -> None:
    """The analyzer records syntactic facts for supported statements."""
    notebook = _loaded_notebook(
        _code_cell(
            "\n".join(
                (
                    "import pandas as pd",
                    "from sklearn.datasets import load_iris",
                    "iris = load_iris(as_frame=True)",
                    "df = iris.frame",
                    "X, y = df[['a']], df['target']",
                )
            )
        )
    )

    facts = analyze_notebook(notebook)
    cell = facts.cells[0]

    assert cell.reads == ("load_iris", "iris", "df")
    assert cell.writes == ("pd", "load_iris", "iris", "df", "X", "y")
    assert tuple(import_.kind for import_ in cell.imports) == (ImportKind.IMPORT, ImportKind.FROM)
    assert cell.imports[0].module == "pandas"
    assert cell.imports[0].bound_name == "pd"
    assert cell.imports[1].module == "sklearn.datasets"
    assert cell.imports[1].name == "load_iris"
    assert cell.calls[0].qualified_name == "load_iris"
    assert cell.calls[0].keyword_arguments[0].name == "as_frame"
    assert cell.calls[0].literal_arguments == (True,)
    assert cell.statements[2].source == "iris = load_iris(as_frame=True)"


def test_analyze_notebook_extracts_method_calls_and_mutation_warning() -> None:
    """Known mutating method calls are recorded as warnings with mutation targets."""
    notebook = _loaded_notebook(_code_cell("model.fit(X_train, y_train)\nmodel.predict(X_test)"))

    facts = analyze_notebook(notebook)

    assert tuple(call.qualified_name for call in facts.cells[0].calls) == (
        "model.fit",
        "model.predict",
    )
    assert facts.cells[0].calls[0].receiver == "model"
    assert facts.cells[0].calls[0].method == "fit"
    assert facts.cells[0].calls[0].positional_argument_sources == ("X_train", "y_train")
    assert facts.cells[0].calls[0].possible_mutation_targets == ("model",)
    assert facts.cells[0].diagnostic_codes == ("DF003", "DF001")
    mutation_diagnostic = next(
        diagnostic for diagnostic in facts.diagnostics if diagnostic.code == "DF003"
    )
    unresolved_symbols = {
        diagnostic.related_symbol for diagnostic in facts.diagnostics if diagnostic.code == "DF001"
    }
    assert mutation_diagnostic.severity is Severity.WARNING
    assert mutation_diagnostic.related_symbol == "model"
    assert {"model", "X_train", "y_train", "X_test"} <= unresolved_symbols


def test_analyze_notebook_reports_magic_before_python_parsing() -> None:
    """Jupyter magics and shell escapes are blocking syntax-level diagnostics."""
    facts = analyze_notebook(_loaded_notebook(_code_cell("%matplotlib inline")))

    assert facts.cells[0].statements == ()
    assert facts.cells[0].diagnostic_codes == ("PY002",)
    assert facts.diagnostics[0].blocking is True
    assert facts.diagnostics[0].code == "PY002"


def test_analyze_notebook_reports_python_syntax_errors() -> None:
    """Invalid Python is reported without raising from the analyzer."""
    facts = analyze_notebook(_loaded_notebook(_code_cell("value = ")))

    assert facts.cells[0].statements == ()
    assert facts.cells[0].diagnostic_codes == ("PY001",)
    assert facts.diagnostics[0].code == "PY001"
    assert facts.diagnostics[0].details[0].key == "syntax_error"


def test_analyze_notebook_reports_dynamic_execution_calls() -> None:
    """Dynamic execution is represented as a blocking diagnostic."""
    facts = analyze_notebook(_loaded_notebook(_code_cell("exec('value = 1')")))

    assert facts.cells[0].calls[0].qualified_name == "exec"
    assert facts.cells[0].diagnostic_codes == ("PY003",)
    assert facts.diagnostics[0].code == "PY003"
    assert facts.diagnostics[0].blocking is True
    assert facts.diagnostics[0].details[0].value == "exec"


def test_analyze_notebook_builds_symbols_and_cross_cell_dependencies() -> None:
    """Reads link to the latest earlier producer across physical cell order."""
    notebook = _loaded_notebook(
        _code_cell("value = 1", index=0),
        _code_cell("other = value + missing", index=1),
    )

    facts = analyze_notebook(notebook)
    symbols = {symbol.name: symbol for symbol in facts.symbols}

    assert symbols["value"].kind is SymbolKind.DATA
    assert symbols["value"].definitions[0].cell_index == 0
    assert symbols["value"].reads[0].cell_index == 1
    assert symbols["missing"].kind is SymbolKind.UNKNOWN
    assert symbols["other"].kind is SymbolKind.DATA
    assert len(facts.dependencies) == 1
    assert facts.dependencies[0].symbol == "value"
    assert facts.dependencies[0].producer.cell_index == 0
    assert facts.dependencies[0].consumer.cell_index == 1
    assert facts.diagnostics[0].code == "DF001"
    assert facts.diagnostics[0].related_symbol == "missing"


def test_analyze_notebook_marks_import_symbols() -> None:
    """Imported bindings are categorized separately from assigned data."""
    facts = analyze_notebook(
        _loaded_notebook(_code_cell("import pathlib\npath = pathlib.Path('.')"))
    )
    symbols = {symbol.name: symbol for symbol in facts.symbols}

    assert symbols["pathlib"].kind is SymbolKind.IMPORT
    assert symbols["path"].kind is SymbolKind.DATA
    assert facts.cells[0].calls[0].qualified_name == "pathlib.Path"


def test_analyze_notebook_handles_function_and_class_definitions() -> None:
    """Definitions are visible as top-level writes."""
    facts = analyze_notebook(
        _loaded_notebook(_code_cell("def transform(df):\n    return df\n\nclass Model:\n    pass"))
    )

    assert facts.cells[0].writes == ("transform", "Model")
    assert facts.cells[0].statements[0].ast_type == "FunctionDef"
    assert facts.cells[0].statements[1].ast_type == "ClassDef"
    symbols = {symbol.name: symbol for symbol in facts.symbols}
    assert symbols["transform"].kind is SymbolKind.FUNCTION
    assert symbols["Model"].kind is SymbolKind.CLASS


def test_analyze_notebook_handles_attribute_receivers_and_nested_call_names() -> None:
    """Qualified names preserve syntactic receiver shapes where possible."""
    facts = analyze_notebook(
        _loaded_notebook(
            _code_cell(
                "\n".join(
                    (
                        "result = package.module.transform(data)",
                        "other = factory().predict(data)",
                        "again = factory()()",
                    )
                )
            )
        )
    )
    calls = facts.cells[0].calls

    assert calls[0].qualified_name == "package.module.transform"
    assert calls[0].receiver == "package.module"
    assert calls[0].method == "transform"
    assert calls[1].qualified_name == "factory.predict"
    assert calls[1].receiver is None
    assert calls[2].qualified_name == "factory"


def test_analyze_notebook_tracks_attribute_and_subscript_root_reads() -> None:
    """Attribute and subscript expressions read their top-level root names."""
    facts = analyze_notebook(_loaded_notebook(_code_cell("value = df.columns.size + table['x']")))

    assert facts.cells[0].reads == ("df", "table")


def test_analyze_notebook_keeps_only_json_primitive_literal_arguments() -> None:
    """Collection literals are ignored until the schema supports nested values."""
    facts = analyze_notebook(_loaded_notebook(_code_cell("func(1, [2], flag=False, name='x')")))

    assert facts.cells[0].calls[0].literal_arguments == (1, False, "x")


def test_analyze_notebook_uses_most_recent_definition() -> None:
    """A read depends on the most recent previous definition of a symbol."""
    notebook = _loaded_notebook(
        _code_cell("value = 1", index=0),
        _code_cell("value = 2", index=1),
        _code_cell("result = value", index=2),
    )

    facts = analyze_notebook(notebook)

    assert facts.dependencies[0].symbol == "value"
    assert facts.dependencies[0].producer.cell_index == 1
    assert facts.dependencies[0].consumer.cell_index == 2
    assert facts.diagnostics[0].code == "DF002"
    assert facts.diagnostics[0].related_symbol == "value"
    assert facts.cells[1].diagnostic_codes == ("DF002",)


def test_analyze_notebook_does_not_create_dependencies_for_import_reads() -> None:
    """Imported names satisfy reads without becoming data dependencies."""
    notebook = _loaded_notebook(
        _code_cell("import pathlib", index=0),
        _code_cell("path = pathlib.Path('.')", index=1),
    )

    facts = analyze_notebook(notebook)

    assert facts.dependencies == ()
    assert facts.diagnostics == ()


def test_analyze_notebook_does_not_create_same_cell_dependencies() -> None:
    """Same-cell reads are represented in facts but not as cross-cell dependency edges."""
    facts = analyze_notebook(_loaded_notebook(_code_cell("value = 1\nother = value")))

    assert facts.dependencies == ()
    assert facts.diagnostics == ()


def test_analyze_notebook_reports_self_assignment_without_prior_definition() -> None:
    """A write in the same statement does not satisfy that statement's read."""
    facts = analyze_notebook(_loaded_notebook(_code_cell("value = value + 1")))

    assert facts.dependencies == ()
    assert facts.diagnostics[0].code == "DF001"
    assert facts.diagnostics[0].related_symbol == "value"


def test_analyzer_helper_fallbacks_cover_ast_edge_shapes() -> None:
    """Low-level helpers keep deterministic values for uncommon AST shapes."""
    assert ast_analyzer._qualified_name(ast.Constant(value=1)) == "Constant"
    assert ast_analyzer._cell_kind(NotebookCellKind.CODE) is CellKind.CODE
