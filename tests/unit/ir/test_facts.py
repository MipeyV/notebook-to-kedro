"""Unit tests for immutable notebook facts models."""

from dataclasses import FrozenInstanceError

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

SHA256 = "a" * 64


def _statement(
    cell_index: int, statement_index: int, *, reads: tuple[str, ...] = ()
) -> StatementFacts:
    return StatementFacts(
        id=f"cell-{cell_index:04d}-stmt-{statement_index:04d}",
        index=statement_index,
        ast_type="Assign",
        source="value = source",
        location=SourceLocation(cell_index, 1, 0, 1, 14),
        reads=reads,
        writes=("value",),
    )


def _metadata(cell_count: int) -> NotebookMetadata:
    return NotebookMetadata(
        path="tests/fixtures/notebooks/example.ipynb",
        nbformat=4,
        nbformat_minor=5,
        language="python",
        kernel_name="python3",
        cell_count=cell_count,
        content_sha256=SHA256,
    )


def test_source_location_is_immutable() -> None:
    """Facts cannot be modified after construction."""
    location = SourceLocation(0, 1, 0, 1, 4)

    with pytest.raises(FrozenInstanceError):
        location.cell_index = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"cell_index": -1}, "cell_index"),
        ({"cell_index": 0, "start_line": 0, "start_column": 0}, "line numbers"),
        ({"cell_index": 0, "start_line": 1, "start_column": -1}, "column numbers"),
        ({"cell_index": 0, "start_line": 1}, "provided together"),
        ({"cell_index": 0, "end_line": 1}, "provided together"),
        ({"cell_index": 0, "end_line": 1, "end_column": 0}, "requires a start"),
        (
            {
                "cell_index": 0,
                "start_line": 2,
                "start_column": 0,
                "end_line": 1,
                "end_column": 0,
            },
            "must not precede",
        ),
    ],
)
def test_source_location_rejects_invalid_positions(kwargs: dict[str, int], message: str) -> None:
    """Invalid AST-style source positions fail at the model boundary."""
    with pytest.raises(ValueError, match=message):
        SourceLocation(**kwargs)


def test_non_code_cell_rejects_python_facts() -> None:
    """Markdown and raw cells cannot accidentally carry AST facts."""
    with pytest.raises(ValueError, match="non-code cells"):
        CellFacts(
            id="cell-0000",
            index=0,
            kind=CellKind.MARKDOWN,
            source="# Heading",
            reads=("value",),
        )


def test_statement_must_reference_call_from_same_cell() -> None:
    """Statement-to-call references remain internally consistent."""
    statement = StatementFacts(
        id="cell-0000-stmt-0000",
        index=0,
        ast_type="Expr",
        source="model.fit(X, y)",
        location=SourceLocation(0, 1, 0, 1, 15),
        reads=("model", "X", "y"),
        call_ids=("missing-call",),
    )
    call = CallFacts(
        id="cell-0000-call-0000",
        qualified_name="model.fit",
        receiver="model",
        method="fit",
        location=SourceLocation(0, 1, 0, 1, 15),
    )

    with pytest.raises(ValueError, match="calls declared"):
        CellFacts(
            id="cell-0000",
            index=0,
            kind=CellKind.CODE,
            source="model.fit(X, y)",
            statements=(statement,),
            calls=(call,),
        )


def test_dependency_requires_an_earlier_producer() -> None:
    """Cross-cell dependencies cannot point backwards or to the same cell."""
    access = SymbolAccess(cell_index=1, statement_id="cell-0001-stmt-0000")

    with pytest.raises(ValueError, match="must precede"):
        DependencyFacts(
            id="dep-0000",
            symbol="value",
            producer=access,
            consumer=access,
        )


def test_notebook_facts_validate_cross_references() -> None:
    """A valid document links symbols, dependencies, and diagnostics to cells."""
    producer_statement = _statement(0, 0)
    consumer_statement = _statement(1, 0, reads=("value",))
    diagnostic = Diagnostic(
        id="diagnostic-0000",
        code="DF003",
        severity=Severity.WARNING,
        message="Method call may mutate 'value'.",
        blocking=False,
        location=SourceLocation(1, 1, 0, 1, 14),
        related_symbol="value",
    )
    cells = (
        CellFacts(
            id="cell-0000",
            index=0,
            kind=CellKind.CODE,
            source=producer_statement.source,
            statements=(producer_statement,),
            writes=("value",),
        ),
        CellFacts(
            id="cell-0001",
            index=1,
            kind=CellKind.CODE,
            source=consumer_statement.source,
            statements=(consumer_statement,),
            reads=("value",),
            diagnostic_codes=("DF003",),
        ),
    )
    producer = SymbolAccess(0, producer_statement.id)
    consumer = SymbolAccess(1, consumer_statement.id)

    facts = NotebookFacts(
        schema_version="1.0",
        analyzer_version="0.1.0",
        notebook=_metadata(cell_count=2),
        cells=cells,
        symbols=(
            SymbolFacts(
                name="value",
                kind=SymbolKind.DATA,
                definitions=(producer,),
                reads=(consumer,),
            ),
        ),
        dependencies=(
            DependencyFacts(
                id="dep-0000",
                symbol="value",
                producer=producer,
                consumer=consumer,
            ),
        ),
        diagnostics=(diagnostic,),
    )

    assert facts.notebook.cell_count == len(facts.cells)


def test_notebook_metadata_rejects_absolute_or_windows_paths() -> None:
    """Serialized notebook paths remain relative and portable."""
    with pytest.raises(ValueError, match="relative"):
        NotebookMetadata("/tmp/model.ipynb", 4, 5, "python", "python3", 0, SHA256)

    with pytest.raises(ValueError, match="POSIX"):
        NotebookMetadata("tests\\model.ipynb", 4, 5, "python", "python3", 0, SHA256)


def test_notebook_facts_require_contiguous_cell_indexes() -> None:
    """Physical source order is encoded by contiguous cell indexes."""
    cell = CellFacts(id="cell-0001", index=1, kind=CellKind.CODE, source="")

    with pytest.raises(ValueError, match="contiguously"):
        NotebookFacts("1.0", "0.1.0", _metadata(cell_count=1), (cell,))


@pytest.mark.parametrize("field", ["id", "code", "message"])
def test_diagnostic_requires_public_identity_fields(field: str) -> None:
    """Diagnostics reject empty identifiers, codes, and messages."""
    values = {
        "id": "diagnostic-0000",
        "code": "DF001",
        "severity": Severity.WARNING,
        "message": "Unresolved name.",
        "blocking": False,
    }
    values[field] = ""

    with pytest.raises(ValueError, match=field):
        Diagnostic(**values)  # type: ignore[arg-type]


def test_diagnostic_details_require_unique_non_empty_keys() -> None:
    """Structured diagnostic context behaves like an immutable mapping."""
    with pytest.raises(ValueError, match="key"):
        DiagnosticDetail("", "value")

    detail = DiagnosticDetail("symbol", "value")
    with pytest.raises(ValueError, match="unique"):
        Diagnostic(
            "diagnostic-0000",
            "DF001",
            Severity.WARNING,
            "Unresolved name.",
            blocking=False,
            details=(detail, detail),
        )


@pytest.mark.parametrize(("name", "source"), [("", "value"), ("key", "")])
def test_keyword_arguments_require_name_and_source(name: str, source: str) -> None:
    """Keyword argument facts preserve two non-empty source fields."""
    with pytest.raises(ValueError, match="must not be empty"):
        KeywordArgument(name, source)


def test_import_facts_validate_import_form() -> None:
    """Regular and from-import records cannot be confused."""
    location = SourceLocation(0, 1, 0, 1, 10)

    with pytest.raises(ValueError, match="module"):
        ImportFacts(ImportKind.IMPORT, "", "alias", location)
    with pytest.raises(ValueError, match="bound_name"):
        ImportFacts(ImportKind.IMPORT, "package", "", location)
    with pytest.raises(ValueError, match="requires an imported name"):
        ImportFacts(ImportKind.FROM, "package", "value", location)
    with pytest.raises(ValueError, match="must not define"):
        ImportFacts(ImportKind.IMPORT, "package", "value", location, name="member")


def test_call_facts_validate_identity_and_method_shape() -> None:
    """Calls have a stable identity and consistent receiver/method fields."""
    location = SourceLocation(0, 1, 0, 1, 10)

    with pytest.raises(ValueError, match="id"):
        CallFacts("", "func", location)
    with pytest.raises(ValueError, match="qualified_name"):
        CallFacts("call-0", "", location)
    with pytest.raises(ValueError, match="receiver and method"):
        CallFacts("call-0", "model.fit", location, receiver="model")

    keyword = KeywordArgument("axis", "1")
    with pytest.raises(ValueError, match="keyword argument"):
        CallFacts("call-0", "func", location, keyword_arguments=(keyword, keyword))
    with pytest.raises(ValueError, match="mutation"):
        CallFacts(
            "call-0",
            "func",
            location,
            possible_mutation_targets=("model", "model"),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "", "id"),
        ("ast_type", "", "ast_type"),
        ("source", "", "source"),
        ("index", -1, "statement index"),
    ],
)
def test_statement_facts_validate_required_fields(field: str, value: object, message: str) -> None:
    """Statements reject missing identity, source, and invalid positions."""
    values = {
        "id": "cell-0000-stmt-0000",
        "index": 0,
        "ast_type": "Assign",
        "source": "value = 1",
        "location": SourceLocation(0),
    }
    values[field] = value

    with pytest.raises(ValueError, match=message):
        StatementFacts(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field",
    ["reads", "writes", "call_ids"],
)
def test_statement_facts_reject_duplicate_summaries(field: str) -> None:
    """Statement summary collections retain unique source-ordered values."""
    values = {
        "id": "cell-0000-stmt-0000",
        "index": 0,
        "ast_type": "Assign",
        "source": "value = 1",
        "location": SourceLocation(0),
        field: ("duplicate", "duplicate"),
    }

    with pytest.raises(ValueError, match="unique"):
        StatementFacts(**values)  # type: ignore[arg-type]


def test_cell_facts_validate_identity_execution_and_summaries() -> None:
    """Cell-level summaries preserve a valid unique source order."""
    with pytest.raises(ValueError, match="id"):
        CellFacts("", 0, CellKind.CODE, "")
    with pytest.raises(ValueError, match="cell index"):
        CellFacts("cell-0000", -1, CellKind.CODE, "")
    with pytest.raises(ValueError, match="execution_count"):
        CellFacts("cell-0000", 0, CellKind.CODE, "", execution_count=-1)

    for field in ("reads", "writes", "diagnostic_codes"):
        values = {
            "id": "cell-0000",
            "index": 0,
            "kind": CellKind.CODE,
            "source": "",
            field: ("duplicate", "duplicate"),
        }
        with pytest.raises(ValueError, match="unique"):
            CellFacts(**values)  # type: ignore[arg-type]


def test_cell_facts_validate_nested_identifiers_and_locations() -> None:
    """Nested cell records must be unique and belong to the same cell."""
    statement = _statement(0, 0)
    call = CallFacts("call-0", "func", SourceLocation(0))
    import_ = ImportFacts(ImportKind.IMPORT, "package", "package", SourceLocation(0))

    with pytest.raises(ValueError, match="statement IDs"):
        CellFacts(
            "cell-0000",
            0,
            CellKind.CODE,
            statement.source,
            statements=(statement, statement),
        )
    with pytest.raises(ValueError, match="call IDs"):
        CellFacts("cell-0000", 0, CellKind.CODE, "func()", calls=(call, call))

    wrong_statement = _statement(1, 0)
    wrong_call = CallFacts("call-1", "func", SourceLocation(1))
    wrong_import = ImportFacts(ImportKind.IMPORT, "package", "package", SourceLocation(1))
    for field, value, message in (
        ("statements", (wrong_statement,), "statement locations"),
        ("calls", (wrong_call,), "call locations"),
        ("imports", (wrong_import,), "import locations"),
    ):
        values = {
            "id": "cell-0000",
            "index": 0,
            "kind": CellKind.CODE,
            "source": "value",
            field: value,
        }
        with pytest.raises(ValueError, match=message):
            CellFacts(**values)  # type: ignore[arg-type]

    assert import_.bound_name == "package"


def test_symbol_models_validate_access_and_binding_category() -> None:
    """Known and unresolved symbols cannot carry contradictory definitions."""
    with pytest.raises(ValueError, match="cell_index"):
        SymbolAccess(-1, "statement")
    with pytest.raises(ValueError, match="statement_id"):
        SymbolAccess(0, "")
    with pytest.raises(ValueError, match="name"):
        SymbolFacts("", SymbolKind.UNKNOWN)
    with pytest.raises(ValueError, match="known symbols"):
        SymbolFacts("value", SymbolKind.DATA)
    with pytest.raises(ValueError, match="unknown symbols"):
        SymbolFacts("value", SymbolKind.UNKNOWN, definitions=(SymbolAccess(0, "statement"),))


def test_dependency_facts_require_identity_fields() -> None:
    """Dependencies expose non-empty stable IDs, symbols, and resolution modes."""
    producer = SymbolAccess(0, "producer")
    consumer = SymbolAccess(1, "consumer")

    for field in ("id", "symbol", "resolution"):
        values = {
            "id": "dep-0000",
            "symbol": "value",
            "producer": producer,
            "consumer": consumer,
            "resolution": "most_recent_definition",
        }
        values[field] = ""
        with pytest.raises(ValueError, match=field):
            DependencyFacts(**values)  # type: ignore[arg-type]


def test_notebook_metadata_validates_required_values() -> None:
    """Notebook metadata rejects malformed portable identity values."""
    valid = {
        "path": "notebooks/model.ipynb",
        "nbformat": 4,
        "nbformat_minor": 5,
        "language": "python",
        "kernel_name": "python3",
        "cell_count": 0,
        "content_sha256": SHA256,
    }
    cases = (
        ("path", "", "path"),
        ("language", "", "language"),
        ("nbformat", 0, "format versions"),
        ("nbformat_minor", -1, "format versions"),
        ("cell_count", -1, "cell_count"),
        ("content_sha256", "invalid", "content_sha256"),
    )

    for field, value, message in cases:
        values = valid | {field: value}
        with pytest.raises(ValueError, match=message):
            NotebookMetadata(**values)  # type: ignore[arg-type]


def test_notebook_facts_validate_document_identity_and_collections() -> None:
    """Top-level identifiers and collection members remain stable and unique."""
    cell = CellFacts("cell-0000", 0, CellKind.CODE, "")
    metadata = _metadata(1)

    with pytest.raises(ValueError, match="schema_version"):
        NotebookFacts("", "0.1.0", metadata, (cell,))
    with pytest.raises(ValueError, match="analyzer_version"):
        NotebookFacts("1.0", "", metadata, (cell,))
    with pytest.raises(ValueError, match="cell_count"):
        NotebookFacts("1.0", "0.1.0", _metadata(2), (cell,))

    duplicate_cells = (cell, CellFacts("cell-0000", 1, CellKind.CODE, ""))
    with pytest.raises(ValueError, match="cell IDs"):
        NotebookFacts("1.0", "0.1.0", _metadata(2), duplicate_cells)


def test_notebook_facts_validate_unique_symbols_dependencies_and_diagnostics() -> None:
    """Top-level fact collections use unique public identifiers."""
    statement_zero = _statement(0, 0)
    statement_one = _statement(1, 0)
    cells = (
        CellFacts("cell-0000", 0, CellKind.CODE, "value = 1", statements=(statement_zero,)),
        CellFacts("cell-0001", 1, CellKind.CODE, "other = value", statements=(statement_one,)),
    )
    producer = SymbolAccess(0, statement_zero.id)
    consumer = SymbolAccess(1, statement_one.id)
    symbol = SymbolFacts("value", SymbolKind.DATA, (producer,), (consumer,))
    dependency = DependencyFacts("dep-0000", "value", producer, consumer)
    diagnostic = Diagnostic("diag-0", "DF001", Severity.WARNING, "Warning.", blocking=False)

    cases = (
        {"symbols": (symbol, symbol)},
        {"dependencies": (dependency, dependency)},
        {"diagnostics": (diagnostic, diagnostic)},
    )
    for overrides in cases:
        with pytest.raises(ValueError, match="unique"):
            NotebookFacts("1.0", "0.1.0", _metadata(2), cells, **overrides)


def test_notebook_facts_reject_unknown_statement_and_diagnostic_references() -> None:
    """Cross-references cannot point outside the canonical document."""
    statement = _statement(0, 0)
    base_cell = CellFacts("cell-0000", 0, CellKind.CODE, statement.source, statements=(statement,))
    unknown_access = SymbolAccess(0, "missing-statement")
    symbol = SymbolFacts("value", SymbolKind.DATA, definitions=(unknown_access,))

    with pytest.raises(ValueError, match="declared statements"):
        NotebookFacts("1.0", "0.1.0", _metadata(1), (base_cell,), symbols=(symbol,))

    diagnostic_cell = CellFacts(
        "cell-0000",
        0,
        CellKind.CODE,
        statement.source,
        statements=(statement,),
        diagnostic_codes=("DF999",),
    )
    with pytest.raises(ValueError, match="diagnostic codes"):
        NotebookFacts("1.0", "0.1.0", _metadata(1), (diagnostic_cell,))
