"""Application declarations stay immutable, source-bound and statically captured."""

from __future__ import annotations

import hashlib
import json
import shutil
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    ApplicationProject,
    FunctionalWorkflowConfiguration,
    GenerateRequest,
    PlanRequest,
    generate_functional_kedro_project,
    generate_project,
    load_functional_workflow_configuration,
    load_local_project_configuration,
    plan_functional_workflow_path,
    plan_project,
)
from notebook_to_kedro.analysis import application_project as capture
from notebook_to_kedro.analysis.file_inputs import capture_file_references
from notebook_to_kedro.exceptions import FunctionalWorkflowError, ProjectGenerationError
from notebook_to_kedro.generation.kedro.functional import render_functional_workflow
from notebook_to_kedro.semantic.functional_workflow import plan_functional_workflow

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_distribution"
SOURCE = EXAMPLE / "src/distribution_ml/workflow.py"


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, FunctionalWorkflowConfiguration]:
    shutil.copytree(EXAMPLE, tmp_path / "example")
    config = replace(
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
        source_package="example/src/distribution_ml",
        inputs=(("raw", "example/input.json"),),
        application_project=ApplicationProject("example/pyproject.toml", ("application.lock",)),
    )
    return tmp_path / "example/src/distribution_ml/workflow.py", config


def test_capture_exports_static_declarations_and_fresh_json() -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    assert FunctionalWorkflowConfiguration.from_dict(config.to_dict()) == config
    data: Any = config.to_dict()
    data["application_project"]["files"].append("changed")
    assert config.application_project == ApplicationProject(
        "examples/functional_distribution/pyproject.toml", ("application.lock",)
    )
    plan = plan_functional_workflow_path(SOURCE, config, project_root=ROOT)
    distribution = plan.application_distribution
    assert distribution is not None
    assert distribution.name == "synthetic-distribution-example"
    assert distribution.version == "1.2.3"
    assert distribution.requires_python == ">=3.11,<3.14"
    assert distribution.dependencies == ("nbformat>=5.10,<6",)
    assert distribution.optional_dependencies == (("test", ("pytest>=9,<10",)),)
    assert distribution.scripts == (("distribution-example", "distribution_ml.cli:main"),)
    assert distribution.package_root == "src/distribution_ml"
    assert distribution.project_fields == tuple(
        sorted(tomllib.loads((EXAMPLE / "pyproject.toml").read_text())["project"])
    )
    assert [item.path for item in distribution.files] == [
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "application.lock",
    ]
    for item in distribution.files:
        assert item.sha256 == hashlib.sha256((EXAMPLE / item.path).read_bytes()).hexdigest()
    payload = json.loads(plan.to_json())
    assert payload["schema_version"] == "1.6"
    assert payload["application_distribution_sha256"] == distribution.sha256
    assert payload["application_distribution"]["build_status"] == "not_run"
    assert payload["application_distribution"]["dependency_resolution"] == "not_run"
    assert payload["artifact_policy"]["mode"] == "not_declared"
    assert payload["result_boundary"]["mode"] == "json"


@pytest.mark.parametrize(
    "path", [None, "", "../pyproject.toml", "/pyproject.toml", "project.toml", "a\\pyproject.toml"]
)
def test_application_selection_requires_a_contained_pyproject(path: Any) -> None:
    with pytest.raises(FunctionalWorkflowError):
        ApplicationProject(path)


@pytest.mark.parametrize(
    "files", [["README.md"], ("../outside",), ("README.md", "README.md"), (None,)]
)
def test_additional_files_require_unique_immutable_relative_paths(files: Any) -> None:
    with pytest.raises(FunctionalWorkflowError):
        ApplicationProject("pyproject.toml", files)


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"pyproject": "pyproject.toml", "files": ()},
        {"pyproject": "pyproject.toml", "files": [], "guess": True},
    ],
)
def test_selection_json_requires_exact_fields(data: object) -> None:
    with pytest.raises(FunctionalWorkflowError):
        ApplicationProject.from_dict(data)


def test_schema_17_requires_explicit_application_selection_and_inherits_memory_mode(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
) -> None:
    _, config = workspace
    with pytest.raises(FunctionalWorkflowError, match="immutable application_project"):
        replace(config, application_project=None)
    with pytest.raises(FunctionalWorkflowError, match=r"schema 1\.7"):
        replace(config, schema_version="1.6")
    data = config.to_dict()
    data.pop("application_project")
    with pytest.raises(FunctionalWorkflowError, match="Required workflow fields"):
        FunctionalWorkflowConfiguration.from_dict(data)
    assert replace(config, outputs=(("result", "memory"),)).memory_output


def test_generation_copies_raw_build_inputs_and_keeps_distributions_separate(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
) -> None:
    source, config = workspace
    marker = tmp_path / "application_was_imported"
    (source.parent / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    )
    output = tmp_path / "output"
    generate_functional_kedro_project(
        source, config, output, project_root=tmp_path, package_name="generated_case"
    )
    for relative in (
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "application.lock",
        "src/distribution_ml/workflow.py",
        "src/distribution_ml/resource.txt",
    ):
        assert (output / "application" / relative).read_bytes() == (
            tmp_path / "example" / relative
        ).read_bytes()
    generated = tomllib.loads((output / "pyproject.toml").read_text())
    assert generated["project"]["dependencies"][0] == "synthetic-distribution-example==1.2.3"
    assert generated["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src/generated_case"
    ]
    assert not (output / "src/distribution_ml").exists()
    manifest = json.loads((output / "functional-workflow.json").read_text())
    assert manifest["source_module"] == "application/src/distribution_ml/workflow.py"
    assert {item["destination"] for item in manifest["statement_destinations"]} == {
        manifest["source_module"]
    }
    assert "pip install -e ./application -e ." in (output / "README.md").read_text()
    assert not marker.exists()
    with pytest.raises(ProjectGenerationError, match="already exists"):
        generate_functional_kedro_project(source, config, output, project_root=tmp_path)


@pytest.mark.parametrize("relative", ["pyproject.toml", "README.md", "application.lock"])
def test_project_file_drift_is_rejected_before_rendering(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
    relative: str,
) -> None:
    source, config = workspace
    plan = plan_functional_workflow_path(source, config, project_root=tmp_path)
    path = tmp_path / "example" / relative
    path.write_text(path.read_text() + "\n# changed\n")
    with pytest.raises(FunctionalWorkflowError, match="differs from the captured"):
        render_functional_workflow(plan, root=tmp_path, package_name="blocked")


def test_metadata_cannot_be_missing_forged_or_attached_to_older_configuration(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
) -> None:
    source, config = workspace
    plan = plan_functional_workflow_path(source, config, project_root=tmp_path)
    distribution = plan.application_distribution
    assert distribution is not None
    for forged in (
        None,
        replace(distribution, pyproject="other/pyproject.toml"),
        replace(distribution, package_root="other"),
    ):
        with pytest.raises(FunctionalWorkflowError, match="matching application"):
            plan_functional_workflow(
                plan.analysis,
                config,
                source_package=plan.source_package,
                application_distribution=forged,
            )
    with pytest.raises(FunctionalWorkflowError, match="requires application_project"):
        plan_functional_workflow(
            plan.analysis,
            replace(config, schema_version="1.6", application_project=None),
            source_package=plan.source_package,
            application_distribution=distribution,
        )
    with pytest.raises(FunctionalWorkflowError, match="differs from the captured"):
        render_functional_workflow(
            replace(plan, application_distribution=replace(distribution, version="9.9.9")),
            root=tmp_path,
            package_name="blocked",
        )


@pytest.mark.parametrize(
    "name", ["synthetic_distribution_example", "synthetic__distribution.example"]
)
@pytest.mark.parametrize(
    "generated_name", ["synthetic_distribution_example", "synthetic__distribution_example"]
)
def test_normalized_distribution_collisions_block_publication(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
    name: str,
    generated_name: str,
) -> None:
    source, config = workspace
    metadata = tmp_path / "example/pyproject.toml"
    metadata.write_text(metadata.read_text().replace("synthetic-distribution-example", name))
    with pytest.raises(FunctionalWorkflowError, match="distribution name collides"):
        generate_functional_kedro_project(
            source,
            config,
            tmp_path / "out",
            project_root=tmp_path,
            package_name=generated_name,
        )
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("package", ["other/package", "example"])
def test_package_layout_must_stay_inside_its_project(tmp_path: Path, package: str) -> None:
    with pytest.raises(FunctionalWorkflowError, match="inside the pyproject directory"):
        capture.capture_application_project(
            tmp_path, ApplicationProject("example/pyproject.toml"), package
        )


@pytest.mark.parametrize(
    "declaration",
    [
        "project = 1",
        '[project]\nversion = "1.0"',
        '[project]\nname = "-bad"\nversion = "1.0"',
        '[project]\nname = "app"\nversion = 3',
        '[project]\nname = "app"\nversion = "bad version"',
        '[project]\nname = "app"\nversion = ""',
        '[project]\nname = "app"\nversion = "1.0"\ndynamic = true',
        '[project]\nname = "app"\nversion = "1.0"\ndynamic = ["dependencies"]',
        '[project]\nname = "app"\nversion = "1.0"\nrequires-python = 3',
        '[project]\nname = "app"\nversion = "1.0"\ndependencies = "guessed"',
        '[project]\nname = "app"\nversion = "1.0"\ndependencies = [""]',
        '[project]\nname = "app"\nversion = "1.0"\ndependencies = ["bad\\nrequirement"]',
        '[project]\nname = "app"\nversion = "1.0"\noptional-dependencies = []',
        '[project]\nname = "app"\nversion = "1.0"\nscripts = []',
        '[project]\nname = "app"\nversion = "1.0"\nscripts = {app = false}',
        '[project]\nname = "app"\nversion = "1.0"\nscripts = {"" = "app:main"}',
        '[project]\nname = "app"\nversion = "1.0"\nreadme = "../outside.md"',
        "[invalid",
    ],
)
def test_invalid_static_declarations_block_before_publication(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
    declaration: str,
) -> None:
    source, config = workspace
    (tmp_path / "example/pyproject.toml").write_text(declaration, encoding="utf-8")
    with pytest.raises(FunctionalWorkflowError):
        generate_functional_kedro_project(source, config, tmp_path / "out", project_root=tmp_path)
    assert not (tmp_path / "out").exists()


def test_minimal_metadata_and_inline_text_keep_defaults_and_deduplicate_files(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
) -> None:
    source, config = workspace
    (tmp_path / "example/pyproject.toml").write_text(
        '[project]\nname="app"\nversion="1.0"\n'
        'readme={file="README.md", content-type="text/markdown"}\nlicense={text="CC0"}\n'
    )
    config = replace(
        config,
        application_project=ApplicationProject(
            "example/pyproject.toml", ("README.md", "src/distribution_ml/resource.txt")
        ),
    )
    plan = plan_functional_workflow_path(source, config, project_root=tmp_path)
    distribution = plan.application_distribution
    assert distribution is not None
    assert distribution.requires_python is None
    assert distribution.dependencies == ()
    assert distribution.optional_dependencies == ()
    assert distribution.scripts == ()
    _, copies = render_functional_workflow(plan, root=tmp_path, package_name="minimal")
    targets = [target for _, target in copies]
    assert targets.count(Path("application/README.md")) == 1
    assert targets.count(Path("application/src/distribution_ml/resource.txt")) == 1


@pytest.mark.parametrize("case", ["limit", "encoding", "read_failure"])
def test_metadata_reads_are_bounded_and_report_io_failures(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    source, config = workspace
    metadata = tmp_path / "example/pyproject.toml"
    if case == "limit":
        monkeypatch.setattr(capture, "MAX_PROJECT_BYTES", 1)
    elif case == "encoding":
        metadata.write_bytes(b"\xff")
    else:
        original = Path.open
        calls = 0

        def open_file(path: Path, *args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            if path == metadata:
                calls += 1
                if calls == 2:
                    raise OSError("synthetic read failure")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", open_file)
    with pytest.raises(FunctionalWorkflowError):
        plan_functional_workflow_path(source, config, project_root=tmp_path)


@pytest.mark.parametrize("capture_index", [1, 2])
def test_metadata_changes_during_capture_are_rejected(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capture_index: int,
) -> None:
    source, config = workspace
    original = capture_file_references
    calls = 0

    def identities(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == capture_index:
            result = (
                replace(result[0], files=(replace(result[0].files[0], sha256="0" * 64),)),
                *result[1:],
            )
        return result

    monkeypatch.setattr(capture, "capture_file_references", identities)
    with pytest.raises(FunctionalWorkflowError, match="changed during capture"):
        plan_functional_workflow_path(source, config, project_root=tmp_path)


def test_local_operations_preview_hashes_and_publish_the_selected_application_files(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
) -> None:
    source, config = workspace
    (tmp_path / "workflow.json").write_text(json.dumps(config.to_dict()), encoding="utf-8")
    settings = tmp_path / "project.json"
    settings.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_root": ".",
                "source_kind": "functional",
                "source": source.relative_to(tmp_path).as_posix(),
                "workflow_configuration": "workflow.json",
            }
        ),
        encoding="utf-8",
    )
    local = load_local_project_configuration(settings)
    before = set(tmp_path.rglob("*"))
    preview = plan_project(PlanRequest(local))
    assert set(tmp_path.rglob("*")) == before
    payload: Any = preview.to_dict()
    assert payload["schema_version"] == "1.0"
    assert payload["plan"]["schema_version"] == "1.6"
    assert payload["plan"]["configuration"]["schema_version"] == "1.7"
    assert any(item.destination == "application/pyproject.toml" for item in preview.copies)
    generated = generate_project(GenerateRequest(local, Path("generated")))
    for item in preview.copies:
        assert (
            hashlib.sha256((generated.destination / item.destination).read_bytes()).hexdigest()
            == item.sha256
        )


def test_distribution_capture_composes_with_artifact_ownership_raw_inputs_and_ordering(
    tmp_path: Path,
) -> None:
    example = ROOT / "examples/functional_artifacts"
    shutil.copytree(example, tmp_path / "examples/functional_artifacts")
    metadata = tmp_path / "examples/functional_artifacts/pyproject.toml"
    metadata.write_text('[project]\nname="artifact-application"\nversion="0.1.0"\n')
    config = replace(
        load_functional_workflow_configuration(example / "file_workflow.json"),
        schema_version="1.7",
        application_project=ApplicationProject("examples/functional_artifacts/pyproject.toml"),
    )
    plan = plan_functional_workflow_path(
        metadata.parent / "src/artifact_ml/file_workflow.py", config, project_root=tmp_path
    )
    files, copies = render_functional_workflow(plan, root=tmp_path, package_name="composition")
    payload = json.loads(plan.to_json())
    assert len(payload["ordering"]["after"]) == len(plan.order_after) == 1
    assert payload["result_boundary"]["mode"] == "memory"
    manifest = json.loads(files[Path("functional-workflow.json")])
    assert manifest["artifact_policy_sha256"] is not None
    assert manifest["artifact_policy"]["destinations"] == plan.artifact_bindings()
    assert len(manifest["file_reference_destinations"]) == 1
    assert Path("artifact-policy.json") in files
    assert any(
        target == Path("application/src/artifact_ml/file_workflow.py") for _, target in copies
    )


def test_generation_captures_backend_declarations_without_importing_build_code(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
) -> None:
    source, config = workspace
    metadata = tmp_path / "example/pyproject.toml"
    metadata.write_text(
        '[build-system]\nrequires=[]\nbuild-backend="fixture_backend"\n[project]\nname="app"\nversion="1.0"\n'
    )
    marker = tmp_path / "backend_imported"
    backend = tmp_path / "example/fixture_backend.py"
    backend.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    config = replace(
        config,
        application_project=ApplicationProject("example/pyproject.toml", ("fixture_backend.py",)),
    )
    generate_functional_kedro_project(source, config, tmp_path / "out", project_root=tmp_path)
    assert (tmp_path / "out/application/fixture_backend.py").read_bytes() == backend.read_bytes()
    assert not marker.exists()
