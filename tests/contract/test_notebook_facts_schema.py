"""Contract tests for the public NotebookFacts interchange schema."""

from typing import cast

from notebook_to_kedro.ir import NotebookFacts


def test_notebook_facts_top_level_contract(notebook_facts: NotebookFacts) -> None:
    """The serialized document exposes exactly the versioned top-level fields."""
    payload = notebook_facts.to_dict()

    assert set(payload) == {
        "schema_version",
        "analyzer_version",
        "notebook",
        "cells",
        "symbols",
        "dependencies",
        "diagnostics",
    }
    assert payload["schema_version"] == "1.0"


def test_notebook_metadata_contract_uses_portable_identity(
    notebook_facts: NotebookFacts,
) -> None:
    """Metadata contains a relative POSIX path and source-content digest."""
    metadata = cast("dict[str, object]", notebook_facts.to_dict()["notebook"])

    assert metadata == {
        "path": "tests/fixtures/notebooks/simple_training.ipynb",
        "nbformat": 4,
        "nbformat_minor": 5,
        "language": "python",
        "kernel_name": "python3",
        "cell_count": 2,
        "content_sha256": "a" * 64,
    }


def test_nested_contract_uses_documented_field_names(notebook_facts: NotebookFacts) -> None:
    """Calls, statements, symbols, dependencies, and diagnostics keep stable keys."""
    payload = notebook_facts.to_dict()
    cells = cast("list[dict[str, object]]", payload["cells"])
    calls = cast("list[dict[str, object]]", cells[0]["calls"])
    statements = cast("list[dict[str, object]]", cells[0]["statements"])
    symbols = cast("list[dict[str, object]]", payload["symbols"])
    dependencies = cast("list[dict[str, object]]", payload["dependencies"])
    diagnostics = cast("list[dict[str, object]]", payload["diagnostics"])

    assert "keyword_argument_sources" in calls[0]
    assert "calls" in statements[0]
    assert set(symbols[0]) == {"name", "kind", "definitions", "reads"}
    assert set(dependencies[0]) == {
        "id",
        "symbol",
        "producer",
        "consumer",
        "resolution",
    }
    assert set(diagnostics[0]) == {
        "id",
        "code",
        "severity",
        "message",
        "blocking",
        "location",
        "related_symbol",
        "details",
    }
