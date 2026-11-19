"""Mixed-cell ownership stays exact, ordered, bounded and independent of execution."""

from __future__ import annotations

import ast
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from notebook_to_kedro import (
    GenerateRequest,
    GenerationResult,
    PlanningResult,
    PlanRequest,
    analyze_notebook_path,
    audit_conversion_source,
    generate_kedro_project,
    load_local_project_configuration,
    plan_notebook_path,
    run_local_operation,
)
from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import ProjectGenerationError
from notebook_to_kedro.notebook import LoadedCell, LoadedNotebook, NotebookCellKind
from notebook_to_kedro.semantic import plan_tasks
from notebook_to_kedro.semantic.source_accounting import enforce_source_accounting

if TYPE_CHECKING:
    from notebook_to_kedro.ir import NotebookFacts

ROOT = Path(__file__).parents[3]
EXAMPLE = ROOT / "examples/procedural_notebook"


def _write_notebook(path: Path, source: str) -> None:
    data = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"language_info": {"name": "python"}},
        "cells": [
            {
                "cell_type": "code",
                "id": "mixed-source",
                "source": source,
                "execution_count": None,
                "metadata": {},
                "outputs": [],
            }
        ],
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def _facts(*sources: str) -> NotebookFacts:
    return analyze_notebook(
        LoadedNotebook(
            "notebooks/mixed.ipynb",
            4,
            5,
            "python",
            "python3",
            "a" * 64,
            tuple(
                LoadedCell(f"cell-{i:04d}", i, NotebookCellKind.CODE, source)
                for i, source in enumerate(sources)
            ),
        )
    )


def test_mixed_imports_are_owned_once_without_mutating_source_facts() -> None:
    facts = _facts("import math\nx = math.sqrt(4)", "result = x + 1")
    before = facts.to_json()
    plan = plan_tasks(facts)
    assert plan.imports == ("import math",)
    assert plan.task_candidates[0].source == "x = math.sqrt(4)"
    assert plan.task_candidates[0].statement_ids == ("cell-0000-stmt-0001",)
    assert plan.task_candidates[1].inputs == ("x",)
    audit = audit_conversion_source(facts, plan)
    assert audit.complete
    assert [row.disposition for row in audit.statements] == ["module_import", "task", "task"]
    assert facts.to_json() == before


@pytest.mark.parametrize("rewrite", ["df = df.dropna()", "df = 5"])
def test_csv_boundary_is_an_input_even_when_rewritten_or_ignored(rewrite: str) -> None:
    facts = _facts(f'import pandas as pd\ndf = pd.read_csv("input.csv")\n{rewrite}')
    plan = plan_tasks(facts)
    assert plan.task_candidates[0].inputs == ("df",)
    assert plan.task_candidates[0].outputs == ("df",)
    assert plan.task_candidates[0].source == rewrite
    assert plan.task_candidates[0].statement_ids == ("cell-0000-stmt-0002",)
    assert audit_conversion_source(facts, plan).complete


@pytest.mark.parametrize(
    "sources",
    [
        ('import pandas as pd\ndf = pd.read_csv("input.csv")\nimport math\nresult = len(df)',),
        ("x = 1\nimport math\nresult = x + 1",),
        ('import pandas as pd\nx = 1\ndf = pd.read_csv("input.csv")\nresult = len(df) + x',),
        (
            'import pandas as pd\na = pd.read_csv("a.csv")\nb = pd.read_csv("b.csv")\n'
            "result = len(a) + len(b)",
        ),
        ("import math\nx = 1", "result = 2"),
        ('import pandas as pd\ndf = pd.read_csv("input.csv")\nx = len(df)', "result = x + len(df)"),
        ('import pandas as pd\ndf = pd.read_csv("input.csv").copy()\nresult = len(df)',),
        ('import pandas as pd\npath = "input.csv"\ndf = pd.read_csv(path)',),
    ],
    ids=[
        "import-after-reader",
        "late-import",
        "late-reader",
        "two-readers",
        "independent-cells",
        "reader-reload",
        "nested-reader",
        "dynamic-reader",
    ],
)
def test_unsafe_mixed_promotion_is_blocked(sources: tuple[str, ...]) -> None:
    facts = _facts(*sources)
    plan = plan_tasks(facts)
    audit = audit_conversion_source(facts, plan)
    assert not audit.complete
    assert "SA008" in {issue.code for issue in audit.diagnostics}
    assert "SA008" in enforce_source_accounting(facts, plan).blocking_diagnostic_codes


def test_mixed_cells_do_not_relax_exact_reader_options_or_parameter_bindings() -> None:
    facts = _facts('import pandas as pd\ndf = pd.read_csv("input.csv", sep=";")\nresult = len(df)')
    plan = plan_tasks(facts)
    assert "SA004" in {issue.code for issue in audit_conversion_source(facts, plan).diagnostics}
    facts = _facts(
        "from sklearn.ensemble import RandomForestClassifier\n"
        "a = RandomForestClassifier(random_state=42)\n"
        "b = RandomForestClassifier(random_state=7)"
    )
    assert not audit_conversion_source(facts, plan_tasks(facts)).complete


def test_reordered_business_tasks_remain_blocked_after_a_mixed_preamble() -> None:
    facts = _facts("import math\nx = 1", "y = x + 1")
    plan = plan_tasks(facts)
    changed = replace(plan, task_candidates=tuple(reversed(plan.task_candidates)))
    assert "SA008" in {issue.code for issue in audit_conversion_source(facts, changed).diagnostics}


def test_an_injected_plan_cannot_drop_an_ignored_csv_boundary_read() -> None:
    facts = _facts('import pandas as pd\ndf = pd.read_csv("input.csv")\ndf = 5')
    plan = plan_tasks(facts)
    changed = replace(plan, task_candidates=(replace(plan.task_candidates[0], inputs=()),))
    assert "SA008" in {issue.code for issue in audit_conversion_source(facts, changed).diagnostics}


def test_committed_notebook_has_no_functions_and_complete_original_instruction_ownership() -> None:
    source = EXAMPLE / "workflow.ipynb"
    facts = analyze_notebook_path(source, project_root=ROOT)
    plan = plan_notebook_path(source, project_root=ROOT)
    assert not plan.blocking_diagnostic_codes
    assert len(plan.task_candidates) == 4
    assert all(
        not isinstance(node, ast.FunctionDef)
        for cell in facts.cells
        if cell.kind.value == "code"
        for node in ast.walk(ast.parse(cell.source))
    )
    audit = audit_conversion_source(facts, plan)
    assert audit.complete
    assert len(audit.statements) == sum(len(cell.statements) for cell in facts.cells)
    assert {row.disposition for row in audit.statements} == {"module_import", "catalog", "task"}
    assert plan.task_candidates[0].inputs == ("df",)
    assert plan.task_candidates[0].outputs == ("df", "X", "y")
    assert len(plan.parameters) == 5


def test_existing_cli_and_local_operations_publish_the_same_procedural_plan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    example = workspace / "examples/procedural_notebook"
    shutil.copytree(EXAMPLE, example)
    config = load_local_project_configuration(example / "project.json")
    preview = run_local_operation(PlanRequest(config))
    assert isinstance(preview, PlanningResult)
    generated = run_local_operation(GenerateRequest(config, workspace / "project"))
    assert isinstance(generated, GenerationResult)
    assert generated.to_dict()["execution_status"] == "not_run"
    assert all(
        (generated.destination / file.path).read_text(encoding="utf-8") == file.content
        for file in preview.files
    )
    assert (generated.destination / "data/01_raw/training.csv").read_bytes() == (
        example / "data/training.csv"
    ).read_bytes()
    assert main(["plan", str(example / "workflow.ipynb"), "--project-root", str(workspace)]) == 0
    assert "SA008" not in capsys.readouterr().out


def test_generation_is_static_and_blocked_mixed_plans_never_publish(tmp_path: Path) -> None:
    source = tmp_path / "workflow.ipynb"
    _write_notebook(source, "x = 1\nimport absent_mixed_dependency\ny = x + 1")
    plan = plan_notebook_path(source, project_root=tmp_path)
    assert "SA008" in plan.blocking_diagnostic_codes
    with pytest.raises(ProjectGenerationError, match="SA008"):
        generate_kedro_project(plan, tmp_path / "project")
    assert not (tmp_path / "project").exists()


def test_import_preamble_can_be_planned_without_importing_application_dependencies(
    tmp_path: Path,
) -> None:
    source = tmp_path / "workflow.ipynb"
    _write_notebook(source, "import absent_mixed_dependency as app\nvalue = app.read()")
    facts = analyze_notebook_path(source, project_root=tmp_path)
    plan = plan_notebook_path(source, project_root=tmp_path)
    assert audit_conversion_source(facts, plan).complete
    files = generate_kedro_project(plan, tmp_path / "project", source_facts=facts)
    assert any(file.name == "nodes.py" for file in files)
