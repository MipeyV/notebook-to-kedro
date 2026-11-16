"""Explicit bindings and generated adapters remain separate from source and runtime evidence."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    ArtifactDestination,
    FunctionalWorkflowConfiguration,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
    plan_functional_workflow_path,
)
from notebook_to_kedro.exceptions import FunctionalWorkflowError, WorkflowRegressionError
from notebook_to_kedro.generation.kedro import artifacts as artifact_renderer
from notebook_to_kedro.generation.kedro.artifacts import render_artifact_policy
from notebook_to_kedro.generation.kedro.functional import render_functional_workflow
from notebook_to_kedro.generation.kedro.profiles import DEFAULT_KEDRO_PROFILE

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_artifacts"
SOURCE = EXAMPLE / "src/artifact_ml/workflow.py"


def _config() -> FunctionalWorkflowConfiguration:
    return load_functional_workflow_configuration(EXAMPLE / "workflow.json")


def test_explicit_binding_exports_fresh_values_and_derives_the_actual_owner() -> None:
    config = _config()
    data: Any = config.to_dict()
    assert FunctionalWorkflowConfiguration.from_dict(data) == config
    data["artifact_destinations"]["run"]["path"] = "changed"
    assert config == _config()
    plan = plan_functional_workflow_path(SOURCE, config, project_root=ROOT)
    payload = json.loads(plan.to_json())
    assert payload["schema_version"] == "1.5"
    assert payload["result_boundary"]["artifact_policy"] == "declared"
    assert payload["artifact_policy"]["runtime_validation"] == "not_run"
    assert payload["artifact_policy"]["reservation"] == "not_performed"
    assert plan.artifact_bindings()[0]["owner_step"] == plan.steps[1].id
    assert len(plan.order_after) == 1


@pytest.mark.parametrize(
    ("parameter", "key", "path"),
    [
        ("bad.name", "output", "artifacts/run"),
        ("candidate", "_hidden", "artifacts/run"),
        ("candidate", "class", "artifacts/run"),
        ("candidate", "output", None),
        ("candidate", "output", "/tmp/run"),
        ("candidate", "output", "artifacts/../run"),
        ("candidate", "output", "artifacts/nested/run"),
        ("candidate", "output", "data/run"),
        ("candidate", "output", "artifacts/Run"),
        ("candidate", "output", "artifacts/"),
        ("candidate", "output", "artifacts/con"),
    ],
)
def test_destination_grammar_is_narrow_and_explicit(parameter: str, key: str, path: Any) -> None:
    with pytest.raises(FunctionalWorkflowError):
        ArtifactDestination(parameter, key, path)


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"parameter": "candidate", "key": "output"},
        {"parameter": "candidate", "key": "output", "path": "artifacts/run", "overwrite": True},
    ],
)
def test_destination_fields_never_imply_overwrite_or_ownership(data: object) -> None:
    with pytest.raises(FunctionalWorkflowError):
        ArtifactDestination.from_dict(data)


def test_invalid_config_bindings_are_rejected_before_source_analysis() -> None:
    config = _config()
    with pytest.raises(FunctionalWorkflowError, match=r"schema 1\.6"):
        replace(config, schema_version="1.5")
    for parameters in (
        (("candidate", "scalar"),),
        (("candidate", (("output", "artifacts/different"),)),),
        (),
    ):
        with pytest.raises(FunctionalWorkflowError, match="flat-parameter bindings"):
            replace(config, parameters=parameters)
    with pytest.raises(FunctionalWorkflowError, match="eight immutable"):
        replace(
            config,
            artifact_destinations=tuple(
                (f"run_{i}", ArtifactDestination("candidate", "output", "artifacts/example_run"))
                for i in range(9)
            ),
        )
    with pytest.raises(FunctionalWorkflowError, match="eight immutable"):
        replace(config, artifact_destinations=(("run", "not a declaration"),))  # type: ignore[arg-type]
    duplicate = (config.artifact_destinations[0], ("other", config.artifact_destinations[0][1]))
    with pytest.raises(FunctionalWorkflowError, match="unique"):
        replace(config, artifact_destinations=duplicate)
    data: Any = config.to_dict()
    data["artifact_destinations"] = []
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(data)
    data.pop("artifact_destinations")
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(data)


def test_empty_policy_retains_ordinary_generation_and_legacy_serialization() -> None:
    config = replace(_config(), artifact_destinations=())
    plan = plan_functional_workflow_path(SOURCE, config, project_root=ROOT)
    assert json.loads(plan.to_json())["artifact_policy"]["mode"] == "not_declared"
    files, _ = render_functional_workflow(plan, root=ROOT, package_name="empty_policy")
    assert Path("artifact-policy.json") not in files
    assert (
        "_ArtifactChecked"
        not in files[Path("src/empty_policy/pipelines/notebook_pipeline/pipeline.py")]
    )
    for version in ("1.3", "1.4", "1.5"):
        original = load_functional_workflow_configuration(
            ROOT / "examples/functional_package/workflow.json"
        )
        original = replace(original, schema_version=version)
        assert "artifact_destinations" not in original.to_dict()


def test_an_unused_artifact_parameter_cannot_claim_an_owner(tmp_path: Path) -> None:
    shutil.copytree(EXAMPLE, tmp_path / "example")
    source = tmp_path / "example/src/artifact_ml/workflow.py"
    text = (
        source.read_text()
        .replace(
            "def workflow(values: list[float], candidate: dict)",
            "def workflow(values: list[float], candidate: dict, other: dict)",
        )
        .replace("receipt = write_run(candidate)", "receipt = write_run(other)")
    )
    source.write_text(text)
    config = replace(
        _config(),
        source_package="example/src/artifact_ml",
        inputs=(("values", "example/input.json"),),
        parameters=(*_config().parameters, ("other", _config().parameters[0][1])),
    )
    with pytest.raises(FunctionalWorkflowError, match="exactly one workflow call"):
        generate_functional_kedro_project(source, config, tmp_path / "out", project_root=tmp_path)
    assert not (tmp_path / "out").exists()


def test_policy_is_a_checked_generated_adapter_not_a_rewritten_source_function(
    tmp_path: Path,
) -> None:
    output = tmp_path / "project"
    paths = generate_functional_kedro_project(SOURCE, _config(), output, project_root=ROOT)
    assert (output / "src/artifact_ml/workflow.py").read_bytes() == SOURCE.read_bytes()
    assert not (output / "artifacts").exists()
    marker = output / "artifact-policy.json"
    manifest = json.loads((output / "functional-workflow.json").read_text())
    assert hashlib.sha256(marker.read_bytes()).hexdigest() == manifest["artifact_policy_sha256"]
    pipeline = (
        output / "src/generated_workflow/pipelines/notebook_pipeline/pipeline.py"
    ).read_text()
    assert "_ArtifactChecked(_AfterPrevious(nodes.step_0001_write_run)" in pipeline
    assert (
        "_ArtifactChecked"
        not in (output / "src/generated_workflow/pipelines/notebook_pipeline/nodes.py").read_text()
    )
    gaps = json.loads((output / "regression-coverage.json").read_text())
    assert gaps["missing_artifact_expectations"] == ["run"]
    assert not any(path.name == "test_workflow_regressions.py" for path in paths)


@pytest.mark.parametrize(
    "change", ["name_missing", "dynamic_name", "function_missing", "duplicate"]
)
def test_pipeline_adapter_refuses_missing_or_ambiguous_generated_owners(change: str) -> None:
    plan = plan_functional_workflow_path(SOURCE, _config(), project_root=ROOT)
    files, _ = render_functional_workflow(plan, root=ROOT, package_name="checked")
    path = Path("src/checked/pipelines/notebook_pipeline/pipeline.py")
    tree = ast.parse(files[path])
    owner = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "node"
        and any(
            keyword.arg == "name"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "step_0001_write_run"
            for keyword in node.keywords
        )
    )
    if change == "duplicate":
        collection = next(
            node for node in ast.walk(tree) if isinstance(node, ast.List) and owner in node.elts
        )
        collection.elts.append(owner)
    elif change == "dynamic_name":
        next(keyword for keyword in owner.keywords if keyword.arg == "name").value = ast.Name(
            "dynamic", ast.Load()
        )
    else:
        key = "name" if change == "name_missing" else "func"
        owner.keywords = [keyword for keyword in owner.keywords if keyword.arg != key]
    files[path] = ast.unparse(ast.fix_missing_locations(tree))
    with pytest.raises(FunctionalWorkflowError, match="owner"):
        render_artifact_policy(plan, DEFAULT_KEDRO_PROFILE, "checked", files)


def test_json_regression_contract_cannot_approve_runtime_artifact_effects(tmp_path: Path) -> None:
    with pytest.raises(WorkflowRegressionError, match="artifact expectations"):
        generate_functional_kedro_project(
            SOURCE,
            _config(),
            tmp_path / "out",
            project_root=ROOT,
            regression_contract=load_workflow_regression_contract(
                ROOT / "examples/functional_package/regression.json"
            ),
        )
    assert not (tmp_path / "out").exists()


def test_generation_does_not_validate_or_copy_original_runtime_artifacts(tmp_path: Path) -> None:
    shutil.copytree(EXAMPLE, tmp_path / "example")
    owned = tmp_path / "artifacts/example_run"
    owned.mkdir(parents=True)
    (owned / "keep.txt").write_text("original runtime bytes")
    config = replace(
        _config(),
        source_package="example/src/artifact_ml",
        inputs=(("values", "example/input.json"),),
    )
    output = tmp_path / "new_project"
    generate_functional_kedro_project(
        tmp_path / "example/src/artifact_ml/workflow.py", config, output, project_root=tmp_path
    )
    assert (owned / "keep.txt").read_text() == "original runtime bytes"
    assert not (output / "artifacts").exists()


def test_policy_size_limit_blocks_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(artifact_renderer, "MAX_ARTIFACT_POLICY_BYTES", 1)
    with pytest.raises(FunctionalWorkflowError, match="exceeds 64 KiB"):
        generate_functional_kedro_project(SOURCE, _config(), tmp_path / "out", project_root=ROOT)
    assert not (tmp_path / "out").exists()
