"""Shared typed test fixtures."""

import pytest

from notebook_to_kedro.ir import (
    CallFacts,
    CellFacts,
    CellKind,
    DependencyFacts,
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
    SymbolAccess,
    SymbolFacts,
    SymbolKind,
)


@pytest.fixture
def notebook_facts() -> NotebookFacts:
    """Return a small valid document exercising every serialized fact type."""
    import_location = SourceLocation(0, 1, 0, 1, 37)
    load_location = SourceLocation(0, 2, 0, 2, 31)
    fit_location = SourceLocation(1, 1, 0, 1, 27)
    import_facts = ImportFacts(
        kind=ImportKind.FROM,
        module="sklearn.datasets",
        name="load_iris",
        alias=None,
        bound_name="load_iris",
        location=import_location,
    )
    load_call = CallFacts(
        id="cell-0000-call-0000",
        qualified_name="load_iris",
        location=load_location,
        keyword_arguments=(KeywordArgument("as_frame", "True"),),
        literal_arguments=(True,),
    )
    load_statement = StatementFacts(
        id="cell-0000-stmt-0000",
        index=0,
        ast_type="Assign",
        source="iris = load_iris(as_frame=True)",
        location=load_location,
        reads=("load_iris",),
        writes=("iris",),
        call_ids=(load_call.id,),
    )
    fit_call = CallFacts(
        id="cell-0001-call-0000",
        qualified_name="model.fit",
        receiver="model",
        method="fit",
        positional_argument_sources=("X_train", "y_train"),
        possible_mutation_targets=("model",),
        location=fit_location,
    )
    fit_statement = StatementFacts(
        id="cell-0001-stmt-0000",
        index=0,
        ast_type="Expr",
        source="model.fit(X_train, y_train)",
        location=fit_location,
        reads=("model", "X_train", "y_train"),
        call_ids=(fit_call.id,),
        conditional=False,
    )
    diagnostic = Diagnostic(
        id="diagnostic-0000",
        code="DF003",
        severity=Severity.WARNING,
        message="Method call may mutate 'model'.",
        blocking=False,
        location=fit_location,
        related_symbol="model",
        details=(DiagnosticDetail("qualified_call", "model.fit"),),
    )
    cells = (
        CellFacts(
            id="cell-0000",
            index=0,
            kind=CellKind.CODE,
            execution_count=1,
            source=("from sklearn.datasets import load_iris\niris = load_iris(as_frame=True)"),
            statements=(load_statement,),
            reads=("load_iris",),
            writes=("iris",),
            imports=(import_facts,),
            calls=(load_call,),
        ),
        CellFacts(
            id="cell-0001",
            index=1,
            kind=CellKind.CODE,
            source=fit_statement.source,
            statements=(fit_statement,),
            reads=("model", "X_train", "y_train"),
            calls=(fit_call,),
            diagnostic_codes=(diagnostic.code,),
        ),
    )
    producer = SymbolAccess(0, load_statement.id)
    consumer = SymbolAccess(1, fit_statement.id)
    return NotebookFacts(
        schema_version="1.0",
        analyzer_version="0.1.0",
        notebook=NotebookMetadata(
            path="tests/fixtures/notebooks/simple_training.ipynb",
            nbformat=4,
            nbformat_minor=5,
            language="python",
            kernel_name="python3",
            cell_count=2,
            content_sha256="a" * 64,
        ),
        cells=cells,
        symbols=(
            SymbolFacts(
                name="model",
                kind=SymbolKind.DATA,
                definitions=(producer,),
                reads=(consumer,),
            ),
        ),
        dependencies=(
            DependencyFacts(
                id="dep-0000",
                symbol="model",
                producer=producer,
                consumer=consumer,
            ),
        ),
        diagnostics=(diagnostic,),
    )
