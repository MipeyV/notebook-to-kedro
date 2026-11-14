"""Explicit source-order mode admits joins without relaxing source or aliasing guards."""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    FunctionalWorkflowConfiguration,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    plan_functional_workflow_path,
)
from notebook_to_kedro.exceptions import FunctionalWorkflowError
from notebook_to_kedro.generation.kedro.functional import render_functional_workflow

ROOT = Path(__file__).parents[3]
EXAMPLE = ROOT / "examples/functional_join"


def test_source_order_is_explicit_and_old_schemas_keep_the_linear_guard() -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    assert config.schema_version == "1.2"
    assert config.parameter_values()["candidate"] == {"name": "synthetic", "phase": "validation"}
    plan = plan_functional_workflow_path(EXAMPLE / "workflow.py", config)
    assert plan.order_after == ((plan.steps[1].id, plan.steps[0].id),)
    snapshot = json.loads(plan.to_json())
    assert snapshot["schema_version"] == "1.1"
    assert snapshot["ordering"] == {
        "policy": "source_order",
        "after": [{"step_id": plan.steps[1].id, "after_step_id": plan.steps[0].id}],
    }
    for version in ("1.0", "1.1"):
        data = config.to_dict()
        data["schema_version"] = version
        data["parameters"] = {"candidate": "scalar"}
        old = FunctionalWorkflowConfiguration.from_dict(data)
        with pytest.raises(FunctionalWorkflowError, match="preceding result"):
            plan_functional_workflow_path(EXAMPLE / "workflow.py", old)


def test_paired_ordered_sources_keep_origins_and_original_instruction_asts(tmp_path: Path) -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    script = plan_functional_workflow_path(EXAMPLE / "workflow.py", config, project_root=ROOT)
    notebook = plan_functional_workflow_path(EXAMPLE / "workflow.ipynb", config, project_root=ROOT)
    assert script.analysis.structure_sha256 == notebook.analysis.structure_sha256
    assert script.order_after == notebook.order_after
    assert script.steps[1].span.unit_id != notebook.steps[1].span.unit_id
    destination = tmp_path / "project"
    generate_functional_kedro_project(
        EXAMPLE / "workflow.py", config, destination, project_root=ROOT
    )
    original = (EXAMPLE / "workflow.py").read_text()
    generated = (destination / "src/generated_workflow/workflow_source.py").read_text()
    assert ast.dump(ast.parse(original)) == ast.dump(ast.parse(generated))
    manifest = json.loads((destination / "functional-workflow.json").read_text())
    assert manifest["ordering_inputs"] == [
        {
            "step_id": script.steps[1].id,
            "after_step_id": script.steps[0].id,
            "dataset": "observations",
            "argument": "_ntk_after",
            "forwarded_to_function": False,
        }
    ]
    assert len(manifest["statement_destinations"]) == len(script.analysis.statements)
    assert manifest["steps"][1]["inputs"] == [["raw_specification", "raw_specification"]]
    assert manifest["steps"][1]["source"] == "specification = load_specification(raw_specification)"


def test_linear_workflow_needs_no_extra_ordering_adapter() -> None:
    example = ROOT / "examples/functional_workflow"
    config = load_functional_workflow_configuration(example / "workflow.json")
    old = plan_functional_workflow_path(example / "workflow.py", config, project_root=ROOT)
    ordered = plan_functional_workflow_path(
        example / "workflow.py", replace(config, schema_version="1.2"), project_root=ROOT
    )
    assert old.order_after == ordered.order_after == ()
    old_files, _ = render_functional_workflow(old, root=ROOT, package_name="linear")
    new_files, _ = render_functional_workflow(ordered, root=ROOT, package_name="linear")
    for name in ("nodes.py", "pipeline.py"):
        path = Path(f"src/linear/pipelines/notebook_pipeline/{name}")
        assert old_files[path] == new_files[path]
        assert "_AfterPrevious" not in new_files[path]


@pytest.mark.parametrize(
    "replacement",
    [
        "total = evaluate(observations, observations, candidate)",
        "total = evaluate(raw_values, specification, candidate)",
        "specification = load_specification(observations)\n"
        "    total = evaluate(observations, specification, candidate)",
        "earlier = evaluate(observations, specification, candidate)\n"
        "    total = load_values(candidate)",
    ],
)
def test_ordered_mode_still_rejects_duplicate_or_reused_data_and_mappings(
    tmp_path: Path, replacement: str
) -> None:
    text = (EXAMPLE / "workflow.py").read_text()
    if replacement.startswith("specification ="):
        text = text.replace(
            "specification = load_specification(raw_specification)\n"
            "    total = evaluate(observations, specification, candidate)",
            replacement,
        )
    else:
        text = text.replace("total = evaluate(observations, specification, candidate)", replacement)
    source = tmp_path / "workflow.py"
    source.write_text(text, encoding="utf-8")
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    with pytest.raises(FunctionalWorkflowError, match="at most once"):
        generate_functional_kedro_project(source, config, tmp_path / "project", project_root=ROOT)
    assert not (tmp_path / "project").exists()


def test_ordered_facts_and_steps_are_recomputed_before_rendering() -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    plan = plan_functional_workflow_path(EXAMPLE / "workflow.py", config, project_root=ROOT)
    changed = replace(plan.steps[1], source="specification = load_specification(observations)")
    with pytest.raises(FunctionalWorkflowError, match="recomputed"):
        render_functional_workflow(
            replace(plan, steps=(plan.steps[0], changed, plan.steps[2])),
            root=ROOT,
            package_name="changed",
        )


@pytest.mark.parametrize("value", [[], {"nested": {}}, {"bad": float("nan")}])
def test_schema_1_2_keeps_parameter_validation(value: Any) -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json").to_dict()
    config["parameters"] = {"candidate": value}
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(config)


def test_ordered_generation_does_not_import_dependencies_or_execute_return_calls(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "executed"
    source = tmp_path / "workflow.py"
    source.write_text(
        "import absent_ordering_dependency as dependency\n"
        f"def first(x):\n    return dependency.transform(open({str(marker)!r}, 'w'), x)\n"
        "def second(y):\n    return y\n"
        "def join(a, b):\n    return a\n"
        "def workflow(x, y):\n    a = first(x)\n    b = second(y)\n"
        "    total = join(a, b)\n    return total\n",
        encoding="utf-8",
    )
    config = FunctionalWorkflowConfiguration.from_dict(
        {
            "schema_version": "1.2",
            "entrypoint": "workflow",
            "inputs": {},
            "parameters": {"x": 1, "y": 2},
            "outputs": {"total": "data/08_reporting/total.json"},
        }
    )
    generate_functional_kedro_project(source, config, tmp_path / "project", project_root=tmp_path)
    assert not marker.exists()
    assert "absent_ordering_dependency" not in sys.modules
    assert (
        "_AfterPrevious"
        in (
            tmp_path / "project/src/generated_workflow/pipelines/notebook_pipeline/pipeline.py"
        ).read_text()
    )


def test_unused_results_still_order_every_original_call(tmp_path: Path) -> None:
    source = tmp_path / "workflow.py"
    source.write_text(
        "def f(x):\n    return x\n"
        "def workflow(x, y):\n    a = f(x)\n    b = f(y)\n    total = f(x)\n    return total\n",
        encoding="utf-8",
    )
    config = FunctionalWorkflowConfiguration.from_dict(
        {
            "schema_version": "1.2",
            "entrypoint": "workflow",
            "inputs": {},
            "parameters": {"x": 1, "y": 2},
            "outputs": {"total": "data/08_reporting/total.json"},
        }
    )
    plan = plan_functional_workflow_path(source, config)
    assert plan.order_after == (
        (plan.steps[1].id, plan.steps[0].id),
        (plan.steps[2].id, plan.steps[1].id),
    )
    files, _ = render_functional_workflow(plan, root=tmp_path, package_name="unused")
    pipeline = files[Path("src/unused/pipelines/notebook_pipeline/pipeline.py")]
    assert pipeline.count("func=_AfterPrevious(") == 2
