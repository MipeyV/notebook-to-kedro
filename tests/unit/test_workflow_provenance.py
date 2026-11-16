"""Source Git and published bytes remain distinct from runtime metadata and consent."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from notebook_to_kedro import (
    ApplicationProject,
    FileReferenceInput,
    capture_workflow_provenance,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_preparation_definition,
    prepare_functional_workflow,
)
from notebook_to_kedro import workflow_provenance as provenance
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import ProjectGenerationError, WorkflowProvenanceError
from notebook_to_kedro.generation.kedro.inventory import file_identity

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_distribution"


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-C",
            str(root),
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    root = tmp_path / "source"
    shutil.copytree(EXAMPLE, root)
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "Source fixture")
    config = replace(
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
        source_package="src/distribution_ml",
        inputs=(("raw", "input.json"),),
        application_project=ApplicationProject("pyproject.toml", ("application.lock",)),
    )
    source = root / "src/distribution_ml/workflow.py"
    project = tmp_path / "project"
    generate_functional_kedro_project(
        source, config, project, project_root=root, package_name="provenance_case"
    )
    runtime = {
        "python": "3.12",
        "implementation": "CPython",
        "executable": sys.executable,
        "distributions": [
            {"name": "synthetic-distribution-example", "version": "1.2.3"},
            {"name": "provenance-case", "version": "0.1.0"},
        ],
    }
    monkeypatch.setattr(provenance, "_runtime_metadata", lambda *_: runtime)
    return SimpleNamespace(
        root=root,
        source=source,
        project=project,
        config=config,
        runtime=runtime,
        output=tmp_path / "report",
    )


@pytest.fixture
def prepared_workspace(workspace: SimpleNamespace) -> SimpleNamespace:
    definition = replace(
        load_workflow_preparation_definition(EXAMPLE / "preparation.json"),
        source_package="src/distribution_ml",
        application_project=ApplicationProject(
            "pyproject.toml", ("application.lock", "input.json")
        ),
    )
    prepared = workspace.root.parent / "prepared"
    prepare_functional_workflow(workspace.source, definition, prepared, project_root=workspace.root)
    config = replace(
        workspace.config,
        entrypoint=definition.entrypoint,
        application_project=ApplicationProject(
            "pyproject.toml", ("application.lock", "workflow-preparation.json", "REVIEW.md")
        ),
    )
    workspace.project = workspace.root.parent / "prepared-project"
    generate_functional_kedro_project(
        prepared / "src/distribution_ml/workflow_adapter.py",
        config,
        workspace.project,
        project_root=prepared,
        package_name="provenance_case",
    )
    return workspace


def _capture(workspace: SimpleNamespace) -> Any:
    paths = capture_workflow_provenance(
        workspace.source,
        workspace.config,
        workspace.project,
        workspace.output,
        project_root=workspace.root,
        python_executable=sys.executable,
    )
    assert paths == (workspace.output / "workflow-provenance.json",)
    return json.loads(paths[0].read_text())


def _refresh(project: Path, relative: str) -> None:
    path = project / "generation-inventory.json"
    data = json.loads(path.read_text())
    data["files"][relative].update(file_identity(project / relative))
    path.write_text(json.dumps(data))


def test_source_commit_is_bound_independently_of_execution_repository(
    workspace: SimpleNamespace, tmp_path: Path
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "commit", "--allow-empty", "-qm", "Containing workspace")
    report = _capture(workspace)
    assert report["source"]["git"]["commit"] == _git(workspace.root, "rev-parse", "HEAD")
    assert report["source"]["git"]["working_tree"] == "clean"
    assert report["execution_directory_git"]["commit"] == _git(tmp_path, "rev-parse", "HEAD")
    assert report["source"]["git"]["commit"] != report["execution_directory_git"]["commit"]
    assert report["source"]["lineage"] == "original_package"
    assert report["generation"]["validation"] == "listed_files_match"
    assert {
        key: value for key, value in report["environment"].items() if key != "selected_projects"
    } == workspace.runtime
    assert report["environment"]["selected_projects"][0] == {
        "name": "synthetic-distribution-example",
        "declared_version": "1.2.3",
        "installed_version": "1.2.3",
    }
    assert report["benchmark_execution"] == "not_run"
    assert report["review_status"] == "not_established"
    inventory = json.loads((workspace.project / "generation-inventory.json").read_text())
    assert "generation-inventory.json" not in inventory["files"]
    assert len(inventory["files"]) > 10
    for relative, expected in inventory["files"].items():
        assert file_identity(workspace.project / relative) == {
            key: expected[key] for key in ("sha256", "size_bytes")
        }


def test_dirty_context_and_no_overwrite(workspace: SimpleNamespace) -> None:
    (workspace.root / "untracked.txt").write_text("untracked")
    assert _capture(workspace)["source"]["git"]["working_tree"] == "dirty"
    with pytest.raises(WorkflowProvenanceError, match="already exists"):
        _capture(workspace)


def test_report_can_live_outside_the_package_in_source_project(workspace: SimpleNamespace) -> None:
    workspace.output = workspace.root / "reports/provenance"
    assert _capture(workspace)["source"]["git"]["commit"]


@pytest.mark.parametrize("location", ["package", "project", "parent"])
def test_report_cannot_overlap_protected_files(workspace: SimpleNamespace, location: str) -> None:
    workspace.output = {
        "package": workspace.root / "src/distribution_ml/report",
        "project": workspace.project / "report",
        "parent": workspace.root.parent,
    }[location]
    with pytest.raises(WorkflowProvenanceError, match="overlaps"):
        _capture(workspace)


def test_application_selection_is_required(workspace: SimpleNamespace) -> None:
    workspace.config = replace(workspace.config, schema_version="1.6", application_project=None)
    with pytest.raises(WorkflowProvenanceError, match="explicit application"):
        _capture(workspace)


@pytest.mark.parametrize(
    "relative",
    [
        "application/src/distribution_ml/domain.py",
        "src/provenance_case/pipeline_registry.py",
        "conf/base/parameters.yml",
        "data/01_raw/raw.json",
    ],
)
def test_published_file_drift_blocks_publication(workspace: SimpleNamespace, relative: str) -> None:
    path = workspace.project / relative
    path.write_text(path.read_text() + "\n")
    with pytest.raises(WorkflowProvenanceError, match="differs from its published identity"):
        _capture(workspace)
    assert not workspace.output.exists()


@pytest.mark.parametrize(
    "relative", ["src/distribution_ml/resource.txt", "README.md", "input.json"]
)
def test_source_drift_cannot_be_relabelled(workspace: SimpleNamespace, relative: str) -> None:
    path = workspace.root / relative
    path.write_text(path.read_text() + "changed")
    with pytest.raises(WorkflowProvenanceError, match="copy differs from the selected source"):
        _capture(workspace)
    assert not workspace.output.exists()


@pytest.mark.parametrize("change", ["git", "package", "metadata", "input", "generated"])
def test_mutation_during_observation_blocks_publication(
    workspace: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    def runtime(*_: Any) -> Any:
        if change == "git":
            _git(workspace.root, "commit", "--allow-empty", "-qm", "Changed")
        else:
            path = {
                "package": workspace.root / "src/distribution_ml/resource.txt",
                "metadata": workspace.root / "README.md",
                "input": workspace.root / "input.json",
                "generated": workspace.project / "README.md",
            }[change]
            path.write_text(path.read_text() + "\n")
        return workspace.runtime

    monkeypatch.setattr(provenance, "_runtime_metadata", runtime)
    with pytest.raises(WorkflowProvenanceError):
        _capture(workspace)
    assert not workspace.output.exists()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"schema_version": "2.0", "scope": "published_files", "files": {}},
        {"schema_version": "1.0", "scope": "other", "files": {}},
        {"schema_version": "1.0", "scope": "published_files", "files": []},
    ],
)
def test_inventory_envelope_is_strict(workspace: SimpleNamespace, payload: object) -> None:
    (workspace.project / "generation-inventory.json").write_text(json.dumps(payload))
    with pytest.raises(WorkflowProvenanceError):
        _capture(workspace)


@pytest.mark.parametrize(
    "identity",
    [
        None,
        {},
        {"sha256": 1, "size_bytes": 0, "kind": "copied"},
        {"sha256": "bad", "size_bytes": 0, "kind": "copied"},
        {"sha256": "0" * 64, "size_bytes": True, "kind": "copied"},
        {"sha256": "0" * 64, "size_bytes": -1, "kind": "copied"},
        {"sha256": "0" * 64, "size_bytes": 0, "kind": []},
    ],
)
def test_inventory_identities_are_strict(workspace: SimpleNamespace, identity: object) -> None:
    path = workspace.project / "generation-inventory.json"
    data = json.loads(path.read_text())
    data["files"]["README.md"] = identity
    path.write_text(json.dumps(data))
    with pytest.raises(WorkflowProvenanceError, match="Invalid generated-file identity"):
        _capture(workspace)


def test_json_evidence_is_bounded(
    workspace: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(provenance, "MAX_PROVENANCE_JSON_BYTES", 1)
    with pytest.raises(WorkflowProvenanceError, match="exceeds"):
        _capture(workspace)


def test_preparation_is_recomputed_against_source(prepared_workspace: SimpleNamespace) -> None:
    assert _capture(prepared_workspace)["source"]["lineage"] == "recomputed_preparation_proposal"


@pytest.mark.parametrize("change", ["source_module", "adapter", "review"])
def test_tampered_preparation_cannot_approve_an_adapter(
    prepared_workspace: SimpleNamespace, change: str
) -> None:
    workspace = prepared_workspace
    relative = {
        "source_module": "functional-workflow.json",
        "adapter": "application/src/distribution_ml/workflow_adapter.py",
        "review": "application/workflow-preparation.json",
    }[change]
    path = workspace.project / relative
    if change == "adapter":
        path.write_text(path.read_text() + "\n# changed\n")
    else:
        data = json.loads(path.read_text())
        data["source_module" if change == "source_module" else "status"] = "changed"
        path.write_text(json.dumps(data))
    _refresh(workspace.project, relative)
    with pytest.raises(WorkflowProvenanceError, match="Prepared"):
        _capture(workspace)


def test_original_module_cannot_be_relabelled(workspace: SimpleNamespace) -> None:
    relative = "functional-workflow.json"
    path = workspace.project / relative
    data = json.loads(path.read_text())
    data["source_module"] = "application/src/distribution_ml/other.py"
    path.write_text(json.dumps(data))
    _refresh(workspace.project, relative)
    with pytest.raises(WorkflowProvenanceError, match="source module differs"):
        _capture(workspace)


def test_git_failure_blocks_publication(
    workspace: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*_: Any) -> Any:
        raise FileNotFoundError("unavailable")

    monkeypatch.setattr(provenance, "_git_context", unavailable)
    with pytest.raises(WorkflowProvenanceError, match="Cannot capture"):
        _capture(workspace)


def test_git_context_cannot_be_redirected_by_inherited_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setenv("GIT_DIR", "unrelated")

    def run(command: list[str], **kwargs: Any) -> Any:
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="a" * 40 if "rev-parse" in command else b"")

    monkeypatch.setattr(subprocess, "run", run)
    assert provenance._git_context(tmp_path)["commit"] == "a" * 40
    assert "GIT_DIR" not in calls[0][1]["env"]
    assert str(tmp_path) in calls[0][0]
    assert "core.fsmonitor=false" in calls[0][0]
    monkeypatch.setattr(
        subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout="invalid")
    )
    with pytest.raises(WorkflowProvenanceError, match="invalid source commit"):
        provenance._git_context(tmp_path)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"python": "", "implementation": "CPython", "executable": "python", "distributions": []},
        {
            "python": "3.12",
            "implementation": "CPython",
            "executable": "python",
            "distributions": {},
        },
        {
            "python": "3.12",
            "implementation": "CPython",
            "executable": "python",
            "distributions": [None],
        },
        {
            "python": "3.12",
            "implementation": "CPython",
            "executable": "python",
            "distributions": [{"name": "app", "version": 1}],
        },
    ],
)
def test_runtime_metadata_is_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: object
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps(payload)),
    )
    with pytest.raises(WorkflowProvenanceError, match="invalid distribution metadata"):
        provenance._runtime_metadata(Path(sys.executable), tmp_path)


def test_real_metadata_probe_uses_an_isolated_interpreter(tmp_path: Path) -> None:
    metadata = provenance._runtime_metadata(Path(sys.executable), tmp_path)
    assert metadata["python"]
    assert any(item["name"] == "nbformat" for item in metadata["distributions"])


def test_selected_project_metadata_must_be_available(workspace: SimpleNamespace) -> None:
    workspace.runtime["distributions"] = []
    with pytest.raises(WorkflowProvenanceError, match="installed distribution"):
        _capture(workspace)


def test_declared_and_installed_version_text_are_preserved(workspace: SimpleNamespace) -> None:
    metadata = workspace.root / "pyproject.toml"
    metadata.write_text(metadata.read_text().replace('version = "1.2.3"', 'version = "v1.2.3"'))
    workspace.project = workspace.root.parent / "normalized-project"
    generate_functional_kedro_project(
        workspace.source,
        workspace.config,
        workspace.project,
        project_root=workspace.root,
        package_name="provenance_case",
    )
    selected = _capture(workspace)["environment"]["selected_projects"]
    assert selected[0]["declared_version"] == "v1.2.3"
    assert selected[0]["installed_version"] == "1.2.3"


def test_execution_git_can_be_unavailable(
    workspace: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = provenance._git_context

    def context(path: Path) -> dict[str, object]:
        if path == workspace.project:
            raise subprocess.CalledProcessError(128, "git")
        return original(path)

    monkeypatch.setattr(provenance, "_git_context", context)
    assert _capture(workspace)["execution_directory_git"] == {"status": "unavailable"}


def test_cli_publishes_a_new_bundle(
    workspace: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    config = workspace.root.parent / "source-config.json"
    config.write_text(json.dumps(workspace.config.to_dict()))
    arguments = [
        "capture-workflow-provenance",
        str(workspace.source),
        str(config),
        str(workspace.project),
        str(workspace.output),
        "--project-root",
        str(workspace.root),
        "--python",
        sys.executable,
    ]
    assert main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "captured"
    assert main(arguments) == 1
    assert "already exists" in capsys.readouterr().err


def test_file_reference_bundles_are_bound_to_raw_source_identities(
    workspace: SimpleNamespace,
) -> None:
    (workspace.root / "input.metadata.json").write_text('{"schema": "fixture"}')
    workspace.config = replace(
        workspace.config,
        inputs=(),
        file_inputs=(("raw", FileReferenceInput("input.json", ("input.metadata.json",))),),
    )
    workspace.project = workspace.root.parent / "file-project"
    generate_functional_kedro_project(
        workspace.source,
        workspace.config,
        workspace.project,
        project_root=workspace.root,
        package_name="provenance_case",
    )
    report = _capture(workspace)
    copies = report["source"]["copies"]
    assert copies["data/01_raw/raw/input.json"] == file_identity(workspace.root / "input.json")
    assert copies["data/01_raw/raw/input.metadata.json"] == file_identity(
        workspace.root / "input.metadata.json"
    )


@pytest.mark.parametrize("change", ["steps_type", "steps_count", "binding"])
def test_preparation_call_bindings_remain_explicit(
    prepared_workspace: SimpleNamespace, change: str
) -> None:
    workspace = prepared_workspace
    relative = "application/workflow-preparation.json"
    path = workspace.project / relative
    data = json.loads(path.read_text())
    if change == "binding":
        data["proposal"]["steps"][0]["inputs"][0][1] = "changed"
    else:
        data["proposal"]["steps"] = {} if change == "steps_type" else []
    path.write_text(json.dumps(data))
    _refresh(workspace.project, relative)
    with pytest.raises(WorkflowProvenanceError, match="Prepared"):
        _capture(workspace)


@pytest.mark.parametrize("content", ["project = 1", '[project]\nname = "app"\nversion = 1'])
def test_invalid_generated_distribution_identity_is_rejected(
    workspace: SimpleNamespace, content: str
) -> None:
    (workspace.project / "pyproject.toml").write_text(content)
    _refresh(workspace.project, "pyproject.toml")
    with pytest.raises(WorkflowProvenanceError, match="static distribution identity"):
        _capture(workspace)


def test_inventory_paths_cannot_escape_the_generated_project(workspace: SimpleNamespace) -> None:
    path = workspace.project / "generation-inventory.json"
    data = json.loads(path.read_text())
    data["files"]["../outside"] = data["files"]["README.md"]
    path.write_text(json.dumps(data))
    with pytest.raises(WorkflowProvenanceError, match="relative contained path"):
        _capture(workspace)


def test_inventory_cannot_omit_an_original_source_copy(workspace: SimpleNamespace) -> None:
    path = workspace.project / "generation-inventory.json"
    data = json.loads(path.read_text())
    data["files"].pop("application/src/distribution_ml/domain.py")
    path.write_text(json.dumps(data))
    with pytest.raises(WorkflowProvenanceError, match="copy differs"):
        _capture(workspace)


def test_existing_destination_link_is_preserved(
    workspace: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == workspace.output or original(path))
    with pytest.raises(WorkflowProvenanceError, match="already exists"):
        _capture(workspace)
    assert not workspace.output.exists()


def test_missing_json_input_keeps_the_public_generation_error(workspace: SimpleNamespace) -> None:
    (workspace.root / "input.json").unlink()
    target = workspace.root.parent / "missing-input-project"
    with pytest.raises(ProjectGenerationError, match="Cannot capture publication inventory"):
        generate_functional_kedro_project(
            workspace.source,
            workspace.config,
            target,
            project_root=workspace.root,
            package_name="provenance_case",
        )
    assert not target.exists()


def test_requested_interpreter_retains_its_virtual_environment_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "environment/bin/python"
    original = Path.resolve
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda path, *args, **kwargs: (
            Path(sys.executable) if path == selected else original(path, *args, **kwargs)
        ),
    )

    def run(command: list[str], **_kwargs: Any) -> Any:
        assert command[0] == str(selected.absolute())
        return SimpleNamespace(
            stdout=json.dumps(
                {
                    "python": "3.12",
                    "implementation": "CPython",
                    "executable": command[0],
                    "distributions": [],
                }
            )
        )

    monkeypatch.setattr(subprocess, "run", run)
    assert provenance._runtime_metadata(selected, tmp_path)["executable"] == str(
        selected.absolute()
    )
