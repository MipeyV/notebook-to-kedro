"""Application preparation preserves project layout and separates proposed orchestration."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    ApplicationProject,
    WorkflowPreparationDefinition,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_preparation_definition,
    plan_functional_workflow_path,
    prepare_functional_workflow,
    render_workflow_preparation,
)
from notebook_to_kedro.analysis.application_project import capture_application_project
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import FunctionalWorkflowError, ProjectGenerationError
from notebook_to_kedro.generation import workflow_preparation as preparation

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_distribution"


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, WorkflowPreparationDefinition]:
    shutil.copytree(EXAMPLE, tmp_path / "app")
    definition = replace(
        load_workflow_preparation_definition(EXAMPLE / "preparation.json"),
        source_package="app/src/distribution_ml",
        application_project=ApplicationProject(
            "app/pyproject.toml", ("application.lock", "input.json")
        ),
    )
    return tmp_path / "app/src/distribution_ml/workflow.py", definition


def test_schema_roundtrip_and_direct_values_require_explicit_application_selection() -> None:
    definition = load_workflow_preparation_definition(EXAMPLE / "preparation.json")
    assert WorkflowPreparationDefinition.from_dict(definition.to_dict()) == definition
    values: Any = definition.to_dict()
    values["application_project"]["files"].append("changed")
    assert definition == load_workflow_preparation_definition(EXAMPLE / "preparation.json")
    with pytest.raises(FunctionalWorkflowError, match="requires application_project"):
        replace(definition, application_project=None)
    with pytest.raises(FunctionalWorkflowError, match=r"requires schema 1\.1"):
        replace(definition, schema_version="1.0")
    for change in (None, {}, {"pyproject": "pyproject.toml", "files": ()}):
        values = definition.to_dict()
        values["application_project"] = change
        with pytest.raises(FunctionalWorkflowError):
            WorkflowPreparationDefinition.from_dict(values)
    values = definition.to_dict()
    values.pop("application_project")
    with pytest.raises(FunctionalWorkflowError, match="Invalid preparation fields"):
        WorkflowPreparationDefinition.from_dict(values)


@pytest.mark.parametrize("layout", ["src", "lib"])
def test_preparation_preserves_original_layout_metadata_bytes_and_proposal_provenance(
    workspace: tuple[Path, WorkflowPreparationDefinition],
    tmp_path: Path,
    layout: str,
) -> None:
    source, definition = workspace
    if layout == "lib":
        # Both paths are fixed descendants of this test's workspace.
        assert source.parent.parent.resolve().is_relative_to(tmp_path.resolve())
        shutil.move(str(tmp_path / "app/src"), str(tmp_path / "app/lib"))
        source = tmp_path / "app/lib/distribution_ml/workflow.py"
        metadata = tmp_path / "app/pyproject.toml"
        metadata.write_text(metadata.read_text().replace('"src', '"lib'))
        definition = replace(definition, source_package="app/lib/distribution_ml")
    before = set(tmp_path.rglob("*"))
    files, copies = render_workflow_preparation(source, definition, project_root=tmp_path)
    assert set(tmp_path.rglob("*")) == before
    report = json.loads(files[Path("workflow-preparation.json")])
    assert report["schema_version"] == "1.1"
    assert report["status"] == "unreviewed_proposal"
    assert report["execution_status"] == "not_run"
    assert report["persistent_io_status"] == report["artifact_policy_status"] == "not_defined"
    assert report["application_distribution"]["build_status"] == "not_run"
    assert report["prepared_application"] == {
        "pyproject": "pyproject.toml",
        "source_package": f"{layout}/distribution_ml",
        "adapter": f"{layout}/distribution_ml/workflow_adapter.py",
    }
    assert "prepared_workflow" not in {block["name"] for block in report["source_facts"]["blocks"]}
    assert "prepared_workflow" in {
        block["name"] for block in report["proposal"]["analysis"]["blocks"]
    }
    assert report["proposal"]["adapter"] == report["prepared_application"]["adapter"]
    output = tmp_path / "prepared"
    prepare_functional_workflow(source, definition, output, project_root=tmp_path)
    for original, target in copies:
        assert (output / target).read_bytes() == original.read_bytes()
    assert (output / "pyproject.toml").read_bytes() == (
        tmp_path / "app/pyproject.toml"
    ).read_bytes()
    assert not (source.parent / "workflow_adapter.py").exists()
    assert "schema 1.7" in (output / "REVIEW.md").read_text()
    assert len(report["application_distribution_sha256"]) == 64
    for item in report["application_distribution"]["files"]:
        assert hashlib.sha256((output / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    with pytest.raises(ProjectGenerationError, match="already exists"):
        prepare_functional_workflow(source, definition, output, project_root=tmp_path)


def test_project_file_selection_overlapping_package_files_is_copied_once(
    workspace: tuple[Path, WorkflowPreparationDefinition],
    tmp_path: Path,
) -> None:
    source, definition = workspace
    definition = replace(
        definition,
        application_project=ApplicationProject(
            "app/pyproject.toml", ("src/distribution_ml/resource.txt",)
        ),
    )
    _, copies = render_workflow_preparation(source, definition, project_root=tmp_path)
    targets = [target for _, target in copies]
    assert targets.count(Path("src/distribution_ml/resource.txt")) == 1


@pytest.mark.parametrize(
    "relative",
    ["src/distribution_ml/workflow_adapter.py", "REVIEW.md", "workflow-preparation.json"],
)
def test_existing_selected_targets_colliding_with_preparation_outputs_block_publication(
    workspace: tuple[Path, WorkflowPreparationDefinition],
    tmp_path: Path,
    relative: str,
) -> None:
    source, definition = workspace
    (tmp_path / "app" / relative).write_text('"""Existing content."""\n')
    definition = replace(
        definition, application_project=ApplicationProject("app/pyproject.toml", (relative,))
    )
    with pytest.raises(ProjectGenerationError, match="overlap"):
        prepare_functional_workflow(
            source, definition, tmp_path / "prepared", project_root=tmp_path
        )
    assert not (tmp_path / "prepared").exists()


def test_changed_project_files_block_before_publication(
    workspace: tuple[Path, WorkflowPreparationDefinition],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, definition = workspace
    calls = 0

    def capture(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        result = capture_application_project(*args, **kwargs)
        calls += 1
        if calls == 2:
            result = replace(result, version="9.9.9")
        return result

    monkeypatch.setattr(preparation, "capture_application_project", capture)
    with pytest.raises(FunctionalWorkflowError, match="application differs from the captured"):
        prepare_functional_workflow(
            source, definition, tmp_path / "prepared", project_root=tmp_path
        )
    assert not (tmp_path / "prepared").exists()


def test_missing_additional_file_blocks_the_complete_prepared_project(
    workspace: tuple[Path, WorkflowPreparationDefinition],
    tmp_path: Path,
) -> None:
    source, definition = workspace
    (tmp_path / "app/application.lock").unlink()
    with pytest.raises(FunctionalWorkflowError, match="Cannot capture file reference"):
        prepare_functional_workflow(
            source, definition, tmp_path / "prepared", project_root=tmp_path
        )
    assert not (tmp_path / "prepared").exists()


def test_prepared_application_can_be_planned_and_generated_through_normal_entrypoints(
    workspace: tuple[Path, WorkflowPreparationDefinition],
    tmp_path: Path,
) -> None:
    source, definition = workspace
    prepared = tmp_path / "prepared"
    prepare_functional_workflow(source, definition, prepared, project_root=tmp_path)
    config = replace(
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
        entrypoint=definition.entrypoint,
        source_package="src/distribution_ml",
        inputs=(("raw", "input.json"),),
        application_project=ApplicationProject("pyproject.toml", ("application.lock",)),
    )
    plan = plan_functional_workflow_path(
        prepared / "src/distribution_ml/workflow_adapter.py", config, project_root=prepared
    )
    assert len(plan.steps) == 1
    output = tmp_path / "kedro"
    generate_functional_kedro_project(
        prepared / "src/distribution_ml/workflow_adapter.py", config, output, project_root=prepared
    )
    assert (output / "application/src/distribution_ml/workflow_adapter.py").is_file()
    assert (output / "application/pyproject.toml").read_bytes() == (
        tmp_path / "app/pyproject.toml"
    ).read_bytes()


def test_cli_preview_and_publication_include_application_evidence(
    workspace: tuple[Path, WorkflowPreparationDefinition],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, definition = workspace
    definition_path = tmp_path / "definition.json"
    definition_path.write_text(json.dumps(definition.to_dict()), encoding="utf-8")
    arguments = [
        "prepare-workflow",
        str(source),
        str(definition_path),
        "--project-root",
        str(tmp_path),
    ]
    assert main(arguments) == 0
    preview = json.loads(capsys.readouterr().out)
    assert (
        preview["manifest"]["application_distribution"]["name"] == "synthetic-distribution-example"
    )
    assert not (tmp_path / "prepared").exists()
    assert main([*arguments, "--output-dir", str(tmp_path / "prepared")]) == 0
    assert (tmp_path / "prepared/pyproject.toml").is_file()
