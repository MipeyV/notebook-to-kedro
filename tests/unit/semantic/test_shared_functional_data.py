"""Explicit shared intermediates keep old guards, source fidelity and static publication."""

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
    GenerateRequest,
    GenerationResult,
    PlanningResult,
    PlanRequest,
    SharedDataPolicy,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_local_project_configuration,
    load_workflow_regression_contract,
    plan_functional_workflow_path,
    run_local_operation,
)
from notebook_to_kedro.exceptions import FunctionalWorkflowError
from notebook_to_kedro.generation.kedro.functional import render_functional_workflow
from notebook_to_kedro.semantic.functional_workflow import plan_functional_steps

ROOT = Path(__file__).parents[3]
EXAMPLE = ROOT / "examples/functional_shared_data"


def _config() -> FunctionalWorkflowConfiguration:
    return load_functional_workflow_configuration(EXAMPLE / "workflow.json")


@pytest.mark.parametrize(
    "values",
    [
        None,
        [],
        (),
        ("buffer",) * 101,
        ("buffer", "buffer"),
        (None,),
        ([],),
        ("bad/name",),
        ("Upper",),
        ("class",),
        ("parameters",),
        ("x" * 65,),
    ],
)
def test_shared_names_are_bounded_distinct_public_immutable_values(values: Any) -> None:
    with pytest.raises(FunctionalWorkflowError, match="Shared data"):
        SharedDataPolicy(values)


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {"schema_version": "1.0", "values": ()},
        {"schema_version": "1.0", "values": ["buffer"], "extra": True},
        {"schema_version": "2", "values": ["buffer"]},
    ],
)
def test_shared_policy_is_a_closed_versioned_subcontract(data: object) -> None:
    with pytest.raises(FunctionalWorkflowError, match="Shared data"):
        SharedDataPolicy.from_dict(data)


def test_policy_and_configuration_exports_are_fresh_and_old_output_is_unchanged() -> None:
    data = _config().to_dict()
    config = FunctionalWorkflowConfiguration.from_dict(data)
    assert config.shared_data == SharedDataPolicy(("buffer",))
    exported = config.to_dict()
    assert exported == data
    assert isinstance(exported["shared_data"], dict)
    exported["shared_data"]["values"].append("left")
    assert config.shared_data.values == ("buffer",)
    old = replace(config, shared_data=None)
    assert "shared_data" not in old.to_dict()
    with pytest.raises(FunctionalWorkflowError, match="at most once"):
        plan_functional_workflow_path(EXAMPLE / "workflow.py", old, project_root=ROOT)


@pytest.mark.parametrize("version", ["1.0", "1.1"])
def test_sharing_requires_source_order_and_does_not_change_legacy_modes(version: str) -> None:
    with pytest.raises(FunctionalWorkflowError, match="source-ordered"):
        replace(_config(), schema_version=version)


def test_direct_configuration_rejects_a_mutable_policy() -> None:
    with pytest.raises(FunctionalWorkflowError, match="immutable SharedDataPolicy"):
        replace(_config(), shared_data={"values": ["buffer"]})  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["raw_values", "gain", "report", "left", "unknown"])
def test_only_reused_intermediate_outputs_can_be_declared_shared(name: str) -> None:
    config = replace(_config(), shared_data=SharedDataPolicy((name,)))
    with pytest.raises(FunctionalWorkflowError, match="intermediate outputs consumed"):
        plan_functional_workflow_path(EXAMPLE / "workflow.py", config, project_root=ROOT)


@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
def test_plan_records_exact_shared_producer_consumers_and_source_order(suffix: str) -> None:
    plan = plan_functional_workflow_path(
        EXAMPLE / ("workflow" + suffix), _config(), project_root=ROOT
    )
    assert plan.order_after == ((plan.steps[2].id, plan.steps[1].id),)
    data = json.loads(plan.to_json())
    assert data["schema_version"] == "1.7"
    assert data["data_sharing"] == {
        "policy": "source_ordered_references",
        "execution_scope": "single_process",
        "copy_mode": "assign",
        "runtime_validation": "not_run",
        "values": [
            {
                "value": "buffer",
                "producer_step": plan.steps[0].id,
                "consumers": [
                    {"step_id": plan.steps[1].id, "argument": "buffer"},
                    {"step_id": plan.steps[2].id, "argument": "buffer"},
                ],
            }
        ],
    }
    entry = next(b for b in plan.analysis.blocks if b.name == "workflow")
    with pytest.raises(FunctionalWorkflowError, match="source order"):
        plan_functional_steps(
            entry,
            {b.name: b for b in plan.analysis.blocks},
            reusable_parameters={"gain", "bias"},
            source_order=False,
            shared_values=frozenset({"buffer"}),
        )


@pytest.mark.parametrize(
    "replacement", ["read_right(raw_values, bias)", "read_right(buffer, gain)"]
)
def test_undeclared_boundary_reuse_remains_blocked(tmp_path: Path, replacement: str) -> None:
    source = tmp_path / "workflow.py"
    text = (EXAMPLE / "workflow.py").read_text()
    if "raw_values" in replacement:
        text = text.replace("read_right(buffer, bias)", "read_right(raw_values, bias)")
        text = text.replace("combine(left, right)", "combine(buffer, right)")
    else:
        text = text.replace("read_right(buffer, bias)", replacement)
    source.write_text(text, encoding="utf-8")
    config = _config()
    if "gain" in replacement:
        config = replace(config, parameters=(("gain", (("value", 2.0),)), ("bias", 1.0)))
    with pytest.raises(FunctionalWorkflowError, match="at most once"):
        generate_functional_kedro_project(source, config, tmp_path / "project", project_root=ROOT)
    assert not (tmp_path / "project").exists()


def test_generation_keeps_original_asts_assign_storage_and_gap_declarations(tmp_path: Path) -> None:
    project = tmp_path / "project"
    generate_functional_kedro_project(
        EXAMPLE / "workflow.py",
        _config(),
        project,
        project_root=ROOT,
        regression_contract=load_workflow_regression_contract(EXAMPLE / "regression.json"),
    )
    source = (EXAMPLE / "workflow.py").read_text()
    emitted = (project / "src/generated_workflow/workflow_source.py").read_text()
    assert ast.dump(ast.parse(source)) == ast.dump(ast.parse(emitted))
    catalog = json.loads((project / "conf/base/catalog.yml").read_text())
    for name in ("buffer", "left", "right"):
        assert catalog[name] == {"type": "MemoryDataset", "copy_mode": "assign"}
    manifest = json.loads((project / "functional-workflow.json").read_text())
    assert manifest["data_sharing"]["values"][0]["value"] == "buffer"
    assert manifest["ordering_inputs"][0]["dataset"] == "left"
    report = json.loads((project / "regression-coverage.json").read_text())
    assert report["pipeline_scenarios"] == 3
    assert report["node_scenarios"]["step_0000_create_buffer"] == 1
    assert report["missing_node_expectations"] == [
        "step_0001_read_left",
        "step_0002_read_right",
        "step_0003_combine",
    ]
    assert report["execution_status"] == "not_run"


def test_forged_shared_steps_are_recomputed_before_publication() -> None:
    plan = plan_functional_workflow_path(EXAMPLE / "workflow.py", _config(), project_root=ROOT)
    forged = replace(plan.steps[2], inputs=(("buffer", "left"), ("bias", "bias")))
    with pytest.raises(FunctionalWorkflowError, match="recomputed"):
        render_functional_workflow(
            replace(plan, steps=(*plan.steps[:2], forged, plan.steps[3])),
            root=ROOT,
            package_name="forged",
        )


def test_existing_local_operations_preview_and_publish_the_selected_shared_policy(
    tmp_path: Path,
) -> None:
    config = load_local_project_configuration(EXAMPLE / "project.json")
    preview = run_local_operation(PlanRequest(config))
    assert isinstance(preview, PlanningResult)
    manifest = next(file for file in preview.files if file.path == "functional-workflow.json")
    assert json.loads(manifest.content)["data_sharing"]["policy"] == "source_ordered_references"
    generated = run_local_operation(GenerateRequest(config, tmp_path / "project"))
    assert isinstance(generated, GenerationResult)
    assert (generated.destination / manifest.path).read_text() == manifest.content
    assert generated.to_dict()["execution_status"] == "not_run"


def test_policy_composes_with_the_existing_source_package_contract(tmp_path: Path) -> None:
    package = tmp_path / "src/shared_application"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('"""Synthetic application."""\n', encoding="utf-8")
    source = package / "workflow.py"
    source.write_bytes((EXAMPLE / "workflow.py").read_bytes())
    (tmp_path / "raw.json").write_text("[1.0, 2.0, 3.0]", encoding="utf-8")
    config = replace(
        _config(),
        schema_version="1.3",
        source_package="src/shared_application",
        inputs=(("raw_values", "raw.json"),),
    )
    project = tmp_path / "project"
    generate_functional_kedro_project(source, config, project, project_root=tmp_path)
    assert (project / "src/shared_application/workflow.py").read_bytes() == source.read_bytes()
    manifest = json.loads((project / "functional-workflow.json").read_text())
    assert manifest["source_package"]["module"] == "shared_application.workflow"
    assert manifest["schema_version"] == "1.7"
    assert manifest["data_sharing"]["values"][0]["value"] == "buffer"


def test_shared_generation_does_not_import_or_execute_source(tmp_path: Path) -> None:
    source = tmp_path / "workflow.py"
    text = (EXAMPLE / "workflow.py").read_text()
    text = text.replace(
        'return {"values": raw_values, "events": []}', "return dependency.create(raw_values)"
    )
    text += "\nimport absent_shared_dependency as dependency\n"
    source.write_text(text, encoding="utf-8")
    project = tmp_path / "project"
    generate_functional_kedro_project(source, _config(), project, project_root=ROOT)
    assert "absent_shared_dependency" not in sys.modules
    emitted = (project / "src/generated_workflow/workflow_source.py").read_text()
    assert ast.dump(ast.parse(emitted)) == ast.dump(ast.parse(text))
