"""Preserve structured helper bodies without inferring their paths or orchestration."""

from __future__ import annotations

import ast
import sys
import textwrap
from pathlib import Path

import pytest

from notebook_to_kedro import (
    FunctionalWorkflowConfiguration,
    analyze_functional_blocks_path,
    generate_functional_kedro_project,
    plan_functional_workflow_path,
)
from notebook_to_kedro.analysis.functional import analyze_functional_blocks
from notebook_to_kedro.exceptions import FunctionalWorkflowError
from notebook_to_kedro.ir.functional import FunctionalAnalysis, SourceUnit


def test_committed_script_and_notebook_have_identical_function_structure() -> None:
    root = Path(__file__).parents[3] / "examples/functional_control_flow"
    script = analyze_functional_blocks_path(root / "workflow.py")
    notebook = analyze_functional_blocks_path(root / "workflow.ipynb")
    assert script.complete
    assert notebook.complete
    assert script.structure_sha256 == notebook.structure_sha256
    assert {d.code for d in script.diagnostics} >= {"BL104"}


def _analysis(body: str) -> FunctionalAnalysis:
    source = "def f(x):\n" + textwrap.indent(textwrap.dedent(body).strip(), "    ") + "\n"
    unit = SourceUnit("module", "source.py", "python", "a" * 64, source)
    return analyze_functional_blocks((unit,))


@pytest.mark.parametrize(
    "body",
    [
        "if x:\n    y = 1\nelse:\n    y = 2\nreturn y",
        "if x:\n    raise ValueError('bad')\nelse:\n    y = 2\nreturn y",
        "if x:\n    y = 1\nelse:\n    raise ValueError('bad')\nreturn y",
        "if x:\n    raise ValueError('left')\nelse:\n    raise ValueError('right')\nreturn x",
        "y = []\nfor value in x:\n    if value is None:\n        continue\n"
        "    y.append(value)\nreturn y",
        "y = []\nfor left, right in x:\n    y.append(left+right)\nreturn y",
        "n = 0\nwhile n < x:\n    n += 1\nreturn n",
        "y = 0\nfor value in x:\n    if value > 0:\n        break\n    y += value\n"
        "else:\n    y += 1\nreturn y",
        "y = 0\nwhile y < x:\n    y += 1\n    if y == 2:\n        break\n"
        "else:\n    y += 1\nreturn y",
        "if x:\n    pass\nreturn x",
        "y = []\nfor value in x:\n    if value is None:\n        continue\n"
        "    item = value\n    y.append(item)\nreturn y",
        "if x:\n    raise ValueError('stop')\n    result = local\n    local = 0\nreturn x",
        "y = []\nfor value in x:\n    raise ValueError(value)\nelse:\n    y.append(0)\nreturn y",
        "y = 0\nif x:\n    if x > 0:\n        y = 1\n    else:\n        y = 2\nreturn y",
    ],
)
def test_structured_bodies_keep_original_ast_and_return_facts(body: str) -> None:
    analysis = _analysis(body)
    assert analysis.complete, analysis.to_json()
    assert analysis.schema_version == "1.1"
    assert analysis.blocks[0].ast_sha256
    assert "BL104" in {d.code for d in analysis.diagnostics}
    assert not any(d.code == "BL006" for d in analysis.diagnostics)
    source = ast.parse(analysis.sources[0].source).body[0]
    assert ast.dump(ast.parse(analysis.blocks[0].source).body[0]) == ast.dump(source)


@pytest.mark.parametrize(
    "body",
    [
        "if x:\n    y = 1\nreturn y",
        "if x:\n    y: int\nelse:\n    y = 2\nreturn y",
        "if y:\n    y = x\nreturn x",
        "for y in x:\n    pass\nreturn y",
        "for value in x:\n    y = value\nreturn y",
        "for value in x:\n    pass\nelse:\n    y = value\nreturn x",
        "while y < x:\n    y = 0\nreturn x",
        "while x:\n    if x > 0:\n        y = 1\n    y += 1\nreturn x",
        "if x:\n    y += 1\nreturn x",
        "for value in values:\n    values = x\nreturn x",
        "for value in x:\n    y += value\nreturn x",
        "for value in x:\n    pass\nelse:\n    y = 1\nreturn y",
        "while x:\n    y: int\n    y += 1\nreturn x",
    ],
)
def test_potentially_unbound_names_do_not_become_complete_facts(body: str) -> None:
    analysis = _analysis(body)
    assert not analysis.complete
    assert "BL006" in {d.code for d in analysis.diagnostics}
    assert analysis.structure_sha256 is None


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("if x:\n    try:\n        pass\n    finally:\n        pass\nreturn x", "BL004"),
        ("for value in x:\n    with value:\n        pass\nreturn x", "BL004"),
        ("if x:\n    def nested():\n        return x\nreturn x", "BL004"),
        ("for value in x:\n    yield value\nreturn x", "BL004"),
        ("if x:\n    y = [v for v in x]\nreturn x", "BL004"),
        ("if x:\n    eval(x)\nreturn x", "BL004"),
        ("for value in x:\n    x[0] = value\nreturn x", "BL004"),
        ("if x:\n    x.value = 1\nreturn x", "BL004"),
        ("for callback in x:\n    callback()\nreturn x", "BL008"),
        ("if x:\n    return x\nreturn x", "BL003"),
        ("if x:\n    import math\nreturn x", "BL004"),
    ],
)
def test_nested_unsupported_constructs_still_block(body: str, code: str) -> None:
    analysis = _analysis(body)
    assert not analysis.complete
    assert code in {d.code for d in analysis.diagnostics}


def test_analysis_does_not_execute_control_flow_or_import_dependencies(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    source = (
        "import absent_control_dependency as dependency\n"
        "def f(x):\n    result = []\n    for value in x:\n"
        f"        dependency.run(open({str(marker)!r}, 'w'))\n"
        "        result.append(value)\n    return result\n"
    )
    analysis = analyze_functional_blocks(
        (SourceUnit("module", "source.py", "python", "a" * 64, source),)
    )
    assert analysis.complete
    assert not marker.exists()
    assert "absent_control_dependency" not in sys.modules
    assert {"dependency.run", "open", "result.append"} <= set(analysis.blocks[0].calls)


@pytest.mark.parametrize(
    "statement",
    [
        "if x:\n        total = helper(x)\n    else:\n        total = helper(x)",
        "total = helper(x)\n    for value in x:\n        total = helper(value)",
        "total = helper(x)\n    while total:\n        total = helper(total)",
    ],
)
def test_body_acceptance_does_not_enable_dynamic_entrypoint_graphs(
    tmp_path: Path, statement: str
) -> None:
    source = tmp_path / "workflow.py"
    source.write_text(
        "def helper(x):\n    return x\n\ndef workflow(x):\n    "
        + statement
        + "\n    return total\n",
        encoding="utf-8",
    )
    config = FunctionalWorkflowConfiguration.from_dict(
        {
            "schema_version": "1.2",
            "entrypoint": "workflow",
            "inputs": {"x": "input.json"},
            "parameters": {},
            "outputs": {"total": "data/08_reporting/total.json"},
        }
    )
    with pytest.raises(FunctionalWorkflowError, match="direct module-function"):
        plan_functional_workflow_path(source, config, project_root=tmp_path)
    destination = tmp_path / "out"
    with pytest.raises(FunctionalWorkflowError, match="direct module-function"):
        generate_functional_kedro_project(source, config, destination, project_root=tmp_path)
    assert not destination.exists()
