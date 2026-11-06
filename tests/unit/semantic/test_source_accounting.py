"""Source accounting must expose omitted, duplicated, changed and miswired instructions."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from notebook_to_kedro import audit_conversion_source, generate_kedro_project, plan_notebook_path
from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import ProjectGenerationError
from notebook_to_kedro.ir import ConversionPlan, NotebookFacts, TaskCandidate
from notebook_to_kedro.notebook import LoadedCell, LoadedNotebook, NotebookCellKind
from notebook_to_kedro.semantic import plan_tasks
from notebook_to_kedro.semantic.source_accounting import enforce_source_accounting


def _facts(*sources: str) -> NotebookFacts:
    return analyze_notebook(
        LoadedNotebook(
            "notebooks/example.ipynb",
            4,
            5,
            "python",
            "python3",
            "a" * 64,
            tuple(
                LoadedCell(f"cell-{index:04d}", index, NotebookCellKind.CODE, source)
                for index, source in enumerate(sources)
            ),
        )
    )


def _codes(facts: NotebookFacts, plan: ConversionPlan) -> set[str]:
    return {diagnostic.code for diagnostic in audit_conversion_source(facts, plan).diagnostics}


def test_complete_accounting_is_deterministic_and_preserves_the_plan() -> None:
    facts = _facts(
        "import pandas as pd",
        'df = pd.read_csv("../data/input.csv")',
        "x = 1",
        "y = x + 1\nassert y == 2",
    )
    plan = plan_tasks(facts)
    audit = audit_conversion_source(facts, plan)
    assert audit.complete
    assert [item.disposition for item in audit.statements] == [
        "module_import",
        "catalog",
        "task",
        "task",
        "task",
    ]
    assert enforce_source_accounting(facts, plan) is plan
    assert audit.to_json() == audit_conversion_source(facts, plan).to_json()
    payload = json.loads(audit.to_json())
    assert payload["schema_version"] == "1.0"
    assert payload["notebook_sha256"] == facts.notebook.content_sha256
    assert payload["complete"] is True
    assert len(payload["plan_sha256"]) == 64
    assert len(payload["statements"]) == sum(len(cell.statements) for cell in facts.cells)


@pytest.mark.parametrize("source", ["assert x == 1", "print(x)", "x", "x.to_csv('out.csv')"])
def test_standalone_assertions_expressions_and_side_effects_are_not_silently_dropped(
    source: str,
) -> None:
    facts = _facts("x = 1", source)
    plan = plan_tasks(facts)
    audit = audit_conversion_source(facts, plan)
    assert not audit.complete
    assert audit.statements[-1].disposition == "unhandled"
    guarded = enforce_source_accounting(facts, plan)
    assert "SA002" in guarded.blocking_diagnostic_codes
    assert any("cell-0001-stmt-0000" in item.message for item in guarded.diagnostics)


@pytest.mark.parametrize("change", ["source", "syntax", "unknown_id", "duplicate", "cell", "order"])
def test_task_provenance_and_exact_source_are_cross_checked(change: str) -> None:
    facts = _facts("x = 1\ny = x + 1\nassert y == 2")
    plan = plan_tasks(facts)
    task = plan.task_candidates[0]
    tasks: tuple[TaskCandidate, ...]
    if change == "source":
        tasks = (replace(task, source="x = 1\ny = x + 1"),)
    elif change == "syntax":
        tasks = (replace(task, source="not valid python"),)
    elif change == "unknown_id":
        tasks = (replace(task, statement_ids=("unknown",)),)
    elif change == "duplicate":
        tasks = (task, replace(task, id="other", name="other"))
    elif change == "cell":
        tasks = (replace(task, source_cell_ids=("wrong-cell",)),)
    else:
        tasks = (replace(task, statement_ids=tuple(reversed(task.statement_ids))),)
    assert _codes(facts, replace(plan, task_candidates=tasks)) & {"SA002", "SA003"}


@pytest.mark.parametrize("imports", [(), ("import math",), ("not valid python",)])
def test_changed_module_imports_are_rejected(imports: tuple[str, ...]) -> None:
    facts = _facts("import pandas as pd", "x = 1")
    assert "SA005" in _codes(facts, replace(plan_tasks(facts), imports=imports))


def test_import_hoisting_and_task_ownership_cannot_duplicate_one_instruction() -> None:
    facts = _facts("import math\nx = 1")
    audit = audit_conversion_source(facts, plan_tasks(facts))
    assert not audit.complete
    assert audit.statements[0].disposition == "unhandled"


@pytest.mark.parametrize(
    "call",
    [
        'pd.read_csv("../data/input.csv", sep=";")',
        'pd.read_csv(filepath_or_buffer="../data/input.csv")',
        'pd.read_csv(path, sep=";")',
        'pd.read_csv("../data/input.csv", **options)',
        'pd.read_csv("s3://bucket/data.csv")',
        'pd.read_csv("../data/input.csv").copy()',
    ],
)
def test_catalog_relocation_does_not_discard_reader_semantics(call: str) -> None:
    facts = _facts(
        "import pandas as pd", 'path = "../data/input.csv"\noptions = {}', f"df = {call}"
    )
    audit = audit_conversion_source(facts, plan_tasks(facts))
    # Nested calls that stay in a task retain their code; a promoted loader must be exact.
    if call.endswith(".copy()"):
        assert audit.complete
        assert audit.statements[-1].disposition == "task"
    else:
        assert not audit.complete
        assert "SA004" in {item.code for item in audit.diagnostics}


@pytest.mark.parametrize("change", ["type", "path", "source", "duplicate", "mixed", "alias"])
def test_catalog_claims_are_one_to_one_and_bound_to_supported_source(change: str) -> None:
    sources = ["import pandas as pd", 'df = pd.read_csv("../data/input.csv")']
    if change == "mixed":
        sources[-1] += "\nresult = len(df)"
    elif change == "alias":
        sources.insert(1, "pd = 1")
    facts = _facts(*sources)
    plan = plan_tasks(facts)
    dataset = plan.catalog_datasets[0]
    if change == "type":
        plan = replace(plan, catalog_datasets=(replace(dataset, type="other.Dataset"),))
    elif change == "path":
        plan = replace(plan, catalog_datasets=(replace(dataset, filepath="other.csv"),))
    elif change == "source":
        plan = replace(plan, catalog_datasets=(replace(dataset, source_filepath="other.csv"),))
    elif change == "duplicate":
        plan = replace(plan, catalog_datasets=(dataset, dataset))
    assert "SA004" in _codes(facts, plan)


@pytest.mark.parametrize(
    "change", ["missing_producer", "missing_input", "order", "invented_output"]
)
def test_graph_checks_use_source_dependencies_and_symbol_versions(change: str) -> None:
    facts = _facts("x = 1", "y = x + 1")
    plan = plan_tasks(facts)
    first, second = plan.task_candidates
    tasks: tuple[TaskCandidate, ...]
    if change == "missing_producer":
        tasks = (second,)
    elif change == "missing_input":
        tasks = (first, replace(second, inputs=()))
    elif change == "order":
        tasks = (second, first)
    else:
        tasks = (first, replace(second, outputs=("invented",)))
    assert "SA006" in _codes(facts, replace(plan, task_candidates=tasks))
    assert audit_conversion_source(facts, plan).complete


def test_unknown_globals_and_blocked_syntax_cannot_be_complete() -> None:
    facts = _facts("x = external + 1")
    assert "SA006" in _codes(facts, plan_tasks(facts))
    invalid = _facts("not valid python")
    assert "SA000" in _codes(invalid, plan_tasks(invalid))
    good = _facts("x = 1")
    assert "SA001" in _codes(good, replace(plan_tasks(good), notebook_path="other.ipynb"))


def test_audit_does_not_open_files_import_user_libraries_or_execute_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = _facts("import not_installed as tool", "x = tool.operation()")
    plan = plan_tasks(facts)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("audit performed I/O")

    monkeypatch.setattr(Path, "open", forbidden)
    assert audit_conversion_source(facts, plan).complete


def test_merged_task_keeps_internal_cross_cell_dependencies() -> None:
    facts = _facts("x = 1", "y = x + 1")
    plan = plan_tasks(facts)
    first, second = plan.task_candidates
    merged = replace(
        first,
        source_cell_ids=(*first.source_cell_ids, *second.source_cell_ids),
        statement_ids=(*first.statement_ids, *second.statement_ids),
        source=first.source + "\n" + second.source,
        outputs=("x", "y"),
    )
    assert audit_conversion_source(facts, replace(plan, task_candidates=(merged,))).complete


def test_absolute_csv_and_unaliased_pandas_are_accounted_without_opening_data() -> None:
    facts = _facts("import pandas", 'df = pandas.read_csv("/tmp/source.csv")')
    assert audit_conversion_source(facts, plan_tasks(facts)).complete


def test_inconsistent_import_metadata_cannot_hide_source_instructions() -> None:
    facts = _facts("import pandas as pd", "x = 1", 'df = pd.read_csv("input.csv")')
    plan = plan_tasks(facts)
    altered_cell = replace(
        facts.cells[1], statements=(replace(facts.cells[1].statements[0], ast_type="Import"),)
    )
    altered = replace(facts, cells=(facts.cells[0], altered_cell, facts.cells[2]))
    assert not audit_conversion_source(altered, plan).complete


def test_bound_generator_accepts_fully_accounted_source(tmp_path: Path) -> None:
    facts = _facts("x = 1")
    created = generate_kedro_project(plan_tasks(facts), tmp_path / "project", source_facts=facts)
    assert all(path.is_file() for path in created)


@pytest.mark.parametrize("change", ["value", "argument", "unused", "source_cell"])
def test_parameter_substitution_cannot_change_source_values_or_bindings(change: str) -> None:
    facts = _facts(
        "import pandas as pd", 'df = pd.DataFrame({"x": [None]})', "df = df.fillna(value=0)"
    )
    plan = plan_tasks(facts)
    parameter = plan.parameters[0]
    if change == "value":
        parameter = replace(parameter, value=99)
    elif change == "argument":
        parameter = replace(parameter, function_argument="wrong")
    elif change == "source_cell":
        parameter = replace(parameter, source_cell_id="other")
    else:
        plan = replace(
            plan,
            task_candidates=tuple(replace(task, parameters=()) for task in plan.task_candidates),
        )
    assert "SA007" in _codes(facts, replace(plan, parameters=(parameter,)))
    assert audit_conversion_source(facts, plan_tasks(facts)).complete


def test_public_api_and_cli_block_omissions_before_generation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "source.ipynb"
    path.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"language_info": {"name": "python"}},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": f"source-{index}",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": source,
                    }
                    for index, source in enumerate(("x = 1", "assert x == 1"))
                ],
            }
        ),
        encoding="utf-8",
    )
    plan = plan_notebook_path(path)
    assert "SA002" in plan.blocking_diagnostic_codes
    assert main(["plan", str(path)]) == 0
    report = capsys.readouterr()
    assert "`blocked`" in report.out
    assert "SA002" in report.out
    output = tmp_path / "project"
    assert main(["generate", str(path), str(output)]) == 1
    assert not output.exists()
    facts = _facts("x = 1", "assert x == 1")
    with pytest.raises(ProjectGenerationError, match="SA002"):
        generate_kedro_project(plan_tasks(facts), output, source_facts=facts)
    assert not output.exists()
