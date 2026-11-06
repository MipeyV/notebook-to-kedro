"""Freeze the initial audit envelope without treating serialized evidence as approval."""

import json

from notebook_to_kedro import audit_conversion_source
from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.notebook import LoadedCell, LoadedNotebook, NotebookCellKind
from notebook_to_kedro.semantic import plan_tasks


def test_source_accounting_schema_1_envelope_and_record_fields() -> None:
    facts = analyze_notebook(
        LoadedNotebook(
            "source.ipynb",
            4,
            5,
            "python",
            "python3",
            "a" * 64,
            (LoadedCell("cell-0000", 0, NotebookCellKind.CODE, "x = 1"),),
        )
    )
    result = json.loads(audit_conversion_source(facts, plan_tasks(facts)).to_json())
    assert set(result) == {
        "schema_version",
        "notebook_path",
        "notebook_sha256",
        "plan_sha256",
        "statements",
        "diagnostics",
        "complete",
    }
    assert result["schema_version"] == "1.0"
    assert result["complete"] is True
    assert result["diagnostics"] == []
    assert set(result["statements"][0]) == {
        "statement_id",
        "source_cell_id",
        "disposition",
        "destinations",
        "reason",
    }
    assert result["statements"][0]["disposition"] == "task"
    assert result["statements"][0]["destinations"] == ["task-0000"]
