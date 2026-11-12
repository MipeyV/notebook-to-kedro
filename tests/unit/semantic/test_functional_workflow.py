"""Explicit configuration, complete source accounting and linear workflow boundaries."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    FunctionalWorkflowConfiguration,
    analyze_functional_blocks_path,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    plan_functional_workflow_path,
)
from notebook_to_kedro.analysis.functional import analyze_functional_blocks
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import FunctionalWorkflowError, ProjectGenerationError
from notebook_to_kedro.ir.functional import FunctionalAnalysis, SourceUnit
from notebook_to_kedro.semantic.functional_config import MAX_CONFIGURATION_BYTES
from notebook_to_kedro.semantic.functional_workflow import plan_functional_workflow

ROOT = Path(__file__).parents[3]
EXAMPLE = ROOT / "examples/functional_workflow"


def _configuration(**changes: Any) -> FunctionalWorkflowConfiguration:
    data = {
        "schema_version": "1.0",
        "entrypoint": "workflow",
        "inputs": {"x": "input.json"},
        "parameters": {"scale": 2},
        "outputs": {"total": "data/08_reporting/total.json"},
        **changes,
    }
    return FunctionalWorkflowConfiguration.from_dict(data)


def _analyze(body: str, *, extra: str = "", signature: str = "x, scale") -> FunctionalAnalysis:
    source = (
        "def f(x):\n    y = x\n    return y\n"
        "def g(x, y):\n    z = x\n    return z\n" + extra + f"\ndef workflow({signature}):\n" + body
    )
    return analyze_functional_blocks(
        (SourceUnit("module", "workflow.py", "python", "a" * 64, source),)
    )


def test_pair_wiring_and_snapshot_have_real_positions() -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    script = plan_functional_workflow_path(EXAMPLE / "workflow.py", config, project_root=ROOT)
    notebook = plan_functional_workflow_path(EXAMPLE / "workflow.ipynb", config, project_root=ROOT)
    assert script.analysis.structure_sha256 == notebook.analysis.structure_sha256
    assert [(step.function, step.inputs, step.output) for step in script.steps] == [
        ("prepare_values", (("values", "values"), ("scale", "scale")), "prepared"),
        ("summarize", (("prepared", "prepared"),), "total"),
    ]
    assert notebook.steps[0].span.unit_id == "cell-0004"
    assert notebook.steps[0].span.start_line == 3
    assert script.steps[0].span.start_line > notebook.steps[0].span.start_line
    payload = json.loads(script.to_json())
    assert payload["configuration"] == config.to_dict()
    assert payload["analysis"]["sources"][0]["kind"] == "python"


def test_keyword_calls_and_repeated_scalar_parameters() -> None:
    result = plan_functional_workflow(
        _analyze("    total = g(y=scale, x=scale)\n    return total"), _configuration()
    )
    assert result.steps[0].inputs == (("y", "scale"), ("x", "scale"))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("    total = x + scale\n    return total", "direct module-function"),
        ("    total = abs(x)\n    return total", "direct module-function"),
        ("    total: int = f(x)\n    return total", "direct module-function"),
        ("    a = total = f(x)\n    return total", "direct module-function"),
        ("    total, other = f(x)\n    return total", "direct module-function"),
        ("    _a = f(x)\n    total = f(_a)\n    return total", "public ASCII"),
        ("    parameters = f(x)\n    total = f(parameters)\n    return total", "public ASCII"),
        ("    été = f(x)\n    total = f(été)\n    return total", "public ASCII"),
        ("    total = f(x + scale)\n    return total", "named values"),
        ("    total = f(*x)\n    return total", "named values"),
        ("    total = f(**x)\n    return total", "named values"),
        ("    total = f(x=1)\n    return total", "named values"),
        ("    total = f()\n    return total", "match the called"),
        ("    total = f(x, scale)\n    return total", "match the called"),
        ("    total = f(x, x=scale)\n    return total", "match the called"),
        ("    total = f(other=x)\n    return total", "match the called"),
        ("    total = f(g)\n    return total", "bound values"),
        ("    x = f(x)\n    total = f(x)\n    return total", "single-assignment"),
        ("    total = g(x, x)\n    return total", "at most once"),
        ("    a = f(x)\n    total = g(a, x)\n    return total", "at most once"),
        ("    a = f(x)\n    total = f(scale)\n    return total", "preceding result"),
        ("    total = f(x)\n    a = f(total)\n    return total", "final call result"),
        ("    return total", "complete, recomputed"),
    ],
)
def test_unsupported_wiring_blocks_conversion(body: str, message: str) -> None:
    with pytest.raises(FunctionalWorkflowError, match=message):
        plan_functional_workflow(_analyze(body), _configuration())


def test_empty_entrypoint_and_stale_analysis_are_rejected() -> None:
    analysis = _analyze("    return x")
    with pytest.raises(FunctionalWorkflowError, match="final call result"):
        plan_functional_workflow(
            analysis, _configuration(outputs={"x": "data/08_reporting/x.json"})
        )
    with pytest.raises(FunctionalWorkflowError, match="recomputed"):
        plan_functional_workflow(replace(analysis, statements=()), _configuration())


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"entrypoint": "missing"}, "not found"),
        ({"parameters": {}}, "cover the entrypoint"),
        ({"outputs": {"other": "data/08_reporting/other.json"}}, "single named return"),
    ],
)
def test_configuration_must_match_source(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(FunctionalWorkflowError, match=message):
        plan_functional_workflow(
            _analyze("    total = f(x)\n    return total"), _configuration(**changes)
        )


def test_module_identity_is_not_silently_changed() -> None:
    analysis = _analyze(
        "    total = identity(x)\n    return total", extra="def identity(x):\n    return __name__\n"
    )
    with pytest.raises(FunctionalWorkflowError, match="Module-identity"):
        plan_functional_workflow(analysis, _configuration())


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "2"},
        {"entrypoint": 1},
        {"entrypoint": "_private"},
        {"entrypoint": "class"},
        {"inputs": {"Bad": "file.json"}},
        {"inputs": {"parameters": "file.json"}},
        {"inputs": {"x": ""}},
        {"inputs": {"x": 1}},
        {"inputs": {"scale": "input.json"}},
        {"outputs": {}},
        {"outputs": {"total": 1}},
        {"outputs": {"total": "../escape.json"}},
        {"parameters": {"scale": []}},
        {"parameters": {"scale": {}}},
        {"parameters": {"scale": float("nan")}},
        {"parameters": {"scale": float("inf")}},
    ],
)
def test_configuration_rejects_invalid_boundaries(changes: dict[str, Any]) -> None:
    with pytest.raises(FunctionalWorkflowError):
        _configuration(**changes)


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"extra": 1},
        {
            "schema_version": "1.0",
            "entrypoint": "workflow",
            "inputs": [],
            "parameters": {},
            "outputs": {},
        },
    ],
)
def test_configuration_requires_exact_schema(data: object) -> None:
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(data)


def test_direct_configuration_is_immutable_and_validated() -> None:
    with pytest.raises(FunctionalWorkflowError, match="immutable pairs"):
        replace(_configuration(), inputs=(["x", "a"],))  # type: ignore[arg-type]
    with pytest.raises(FunctionalWorkflowError, match="immutable pairs"):
        replace(_configuration(), inputs=(("x",),))  # type: ignore[arg-type]
    with pytest.raises(FunctionalWorkflowError, match="immutable pairs"):
        replace(_configuration(), inputs=[])  # type: ignore[arg-type]
    with pytest.raises(FunctionalWorkflowError, match="repeat"):
        replace(_configuration(), inputs=(("x", "a"), ("x", "b")))
    for value in (None, True, "text", 1.5):
        assert _configuration(parameters={"scale": value}).parameters == (("scale", value),)


@pytest.mark.parametrize(
    "content",
    [
        b"{",
        b"\xff",
        b" " * (MAX_CONFIGURATION_BYTES + 1),
        b'{"entrypoint": "a", "entrypoint": "b"}',
    ],
    ids=["syntax", "encoding", "size", "duplicate"],
)
def test_invalid_configuration_files(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(content)
    with pytest.raises(FunctionalWorkflowError):
        load_functional_workflow_configuration(path)


def test_missing_configuration_file(tmp_path: Path) -> None:
    with pytest.raises(FunctionalWorkflowError, match="Cannot read"):
        load_functional_workflow_configuration(tmp_path / "missing.json")


def test_generation_blocks_bad_inputs_before_publication(tmp_path: Path) -> None:
    configuration = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    destination = tmp_path / "project"
    for path in (str(ROOT.parent / "external.json"), "input.csv"):
        with pytest.raises(FunctionalWorkflowError, match="contained"):
            generate_functional_kedro_project(
                EXAMPLE / "workflow.py",
                replace(configuration, inputs=(("values", path),)),
                destination,
                project_root=ROOT,
            )
        assert not destination.exists()
    with pytest.raises(ProjectGenerationError, match="source file"):
        generate_functional_kedro_project(
            EXAMPLE / "workflow.py",
            replace(configuration, inputs=(("values", "missing.json"),)),
            destination,
            project_root=ROOT,
        )
    assert not destination.exists()


def test_cli_plan_generate_and_profile(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = [
        str(EXAMPLE / "workflow.py"),
        str(EXAMPLE / "workflow.json"),
        "--project-root",
        str(ROOT),
    ]
    assert main(["plan-workflow", *args]) == 0
    assert len(json.loads(capsys.readouterr().out)["steps"]) == 2
    destination = tmp_path / "project"
    assert main(["generate-workflow", *args, str(destination)]) == 0
    assert "Created functional" in capsys.readouterr().out
    assert main(["generate-workflow", *args, str(destination)]) == 1
    assert "already exists" in capsys.readouterr().err
    assert (
        main(
            [
                "generate-workflow",
                *args,
                str(tmp_path / "profile"),
                "--architecture-profile",
                str(ROOT / "examples/kedro_profiles/team_training.json"),
            ]
        )
        == 0
    )
    assert "Created functional" in capsys.readouterr().out


def test_generation_keeps_source_ast_and_has_no_fake_python_cells(tmp_path: Path) -> None:
    configuration = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    destination = tmp_path / "project"
    generate_functional_kedro_project(
        EXAMPLE / "workflow.py", configuration, destination, project_root=ROOT
    )
    generated = destination / "src/generated_workflow/workflow_source.py"
    assert ast.dump(ast.parse(generated.read_text(encoding="utf-8"))) == ast.dump(
        ast.parse((EXAMPLE / "workflow.py").read_text(encoding="utf-8"))
    )
    manifest = json.loads((destination / "functional-workflow.json").read_text())
    assert {row["statement_id"] for row in manifest["statement_destinations"]} == {
        row["id"] for row in manifest["analysis"]["statements"]
    }
    assert manifest["analysis"]["sources"][0]["cell_id"] is None
    assert analyze_functional_blocks_path(EXAMPLE / "workflow.py").complete


def test_incompatible_cell_compilation_context_blocks_publication(tmp_path: Path) -> None:
    source = tmp_path / "workflow.ipynb"
    sources = [
        "def f(x):\n    return x\ndef workflow(x, scale):\n    total = f(x)\n    return total",
        "from __future__ import annotations",
    ]
    source.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"language_info": {"name": "python"}},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": f"cell-{index}",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": cell,
                    }
                    for index, cell in enumerate(sources)
                ],
            }
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "project"
    with pytest.raises(FunctionalWorkflowError, match="Cannot relocate"):
        generate_functional_kedro_project(
            source, _configuration(), destination, project_root=tmp_path
        )
    assert not destination.exists()
