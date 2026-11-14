"""Local operations preserve engine output, explicit boundaries and static-only behavior."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    GenerateRequest,
    InspectRequest,
    LocalProjectConfiguration,
    PlanRequest,
    generate_functional_kedro_project,
    generate_kedro_project,
    generate_project,
    inspect_project,
    load_functional_workflow_configuration,
    load_local_project_configuration,
    load_workflow_regression_contract,
    plan_notebook_path,
    plan_project,
    run_local_operation,
)
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import FunctionalWorkflowError, LocalOperationError
from notebook_to_kedro.generation.kedro.functional import (
    plan_functional_workflow_path,
    render_functional_workflow,
)
from notebook_to_kedro.operations.configuration import MAX_LOCAL_CONFIGURATION_BYTES, contained_path

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_workflow"


def _settings(**changes: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project_root": ".",
        "source_kind": "functional",
        "source": "examples/functional_workflow/workflow.py",
        "workflow_configuration": "examples/functional_workflow/workflow.json",
        **changes,
    }


def _workspace(tmp_path: Path, **changes: Any) -> tuple[Path, Path]:
    root = tmp_path / "workspace"
    root.mkdir()
    shutil.copytree(EXAMPLE, root / "examples/functional_workflow")
    settings = root / "project.json"
    settings.write_text(json.dumps(_settings(**changes)), encoding="utf-8")
    return root, settings


def test_configuration_is_explicit_anchored_and_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, path = _workspace(
        tmp_path, regression_contract="examples/functional_workflow/regression.json"
    )
    monkeypatch.chdir(tmp_path)
    config = load_local_project_configuration(path)
    assert config.project_root == root
    assert config.source == root / "examples/functional_workflow/workflow.py"
    assert config.regression_contract == root / "examples/functional_workflow/regression.json"
    dynamic: Any = config
    with pytest.raises(FrozenInstanceError):
        dynamic.package_name = "changed"
    exported = config.to_dict()
    exported["package_name"] = "changed"
    assert config.to_dict()["package_name"] == "generated_project"
    roundtrip = root / "roundtrip.json"
    roundtrip.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    assert load_local_project_configuration(roundtrip) == config


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {**_settings(), "extra": "ignored"},
        _settings(schema_version="2.0"),
        _settings(source_kind="prompt"),
        _settings(project_root=None),
        _settings(project_root=""),
        _settings(project_root="missing"),
        _settings(project_root="C:relative"),
        _settings(source=None),
        _settings(source=""),
        _settings(source="C:relative.py"),
        _settings(source="/absolute.py"),
        _settings(source="\\\\server\\share\\source.py"),
        _settings(source="examples\\source.py"),
        _settings(source=".."),
        _settings(source="."),
        _settings(package_name=None),
        _settings(package_name="not-valid"),
        _settings(package_name="_private"),
        _settings(package_name="class"),
        {key: value for key, value in _settings().items() if key != "workflow_configuration"},
        _settings(source_kind="notebook"),
        {
            **{key: value for key, value in _settings().items() if key != "workflow_configuration"},
            "source_kind": "notebook",
            "regression_contract": "regression.json",
        },
        _settings(architecture_profile=None),
        _settings(regression_contract=17),
    ],
    ids=lambda data: str(data)[:100],
)
def test_invalid_json_settings_are_rejected_before_work(tmp_path: Path, data: Any) -> None:
    path = tmp_path / "project.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(LocalOperationError) as error:
        load_local_project_configuration(path)
    assert error.value.code == "LO001"
    assert set(tmp_path.iterdir()) == {path}


@pytest.mark.parametrize(
    "content",
    [
        b'{"schema_version":"1.0","schema_version":"2.0"}',
        b"not JSON",
        b"\xff",
        b"[" * 1100 + b"]" * 1100,
        b" " * (MAX_LOCAL_CONFIGURATION_BYTES + 1),
    ],
    ids=["duplicate", "syntax", "encoding", "depth", "size"],
)
def test_bounded_configuration_loading(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "project.json"
    path.write_bytes(content)
    with pytest.raises(LocalOperationError):
        load_local_project_configuration(path)


def test_missing_configuration_is_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(LocalOperationError, match="Cannot read local configuration"):
        load_local_project_configuration(tmp_path / "missing.json")


@pytest.mark.parametrize(
    "changes",
    [
        {"project_root": "string"},
        {"source": "string"},
        {"workflow_configuration": "string"},
    ],
)
def test_direct_configuration_rejects_non_path_values(
    tmp_path: Path, changes: dict[str, Any]
) -> None:
    values: dict[str, Any] = {
        "project_root": tmp_path,
        "source": Path("source.py"),
        "source_kind": "functional",
        "workflow_configuration": Path("workflow.json"),
    }
    with pytest.raises(LocalOperationError, match=r"pathlib\.Path"):
        LocalProjectConfiguration(**{**values, **changes})


@pytest.mark.parametrize("path", ["string", Path("C:relative"), Path("\\rooted"), Path("..")])
def test_api_paths_cannot_escape_or_use_ambiguous_platform_forms(tmp_path: Path, path: Any) -> None:
    with pytest.raises(LocalOperationError):
        contained_path(tmp_path, path)


@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("with_contract", [False, True])
def test_preview_matches_existing_functional_generator_without_writes(
    tmp_path: Path, suffix: str, *, with_contract: bool
) -> None:
    root, location = _workspace(tmp_path, source=f"examples/functional_workflow/workflow{suffix}")
    config = load_local_project_configuration(location)
    if with_contract:
        config = replace(
            config, regression_contract=root / "examples/functional_workflow/regression.json"
        )
    before = set(root.rglob("*"))
    result = plan_project(PlanRequest(config))
    assert set(root.rglob("*")) == before
    inspection = inspect_project(InspectRequest(config))
    assert inspection.to_dict()["status"] == "inspected"
    assert inspection.to_dict()["execution_status"] == "not_run"
    preview = result.to_dict()
    assert preview["status"] == "planned"
    destination = root / "generated"
    generated = generate_project(GenerateRequest(config, Path("generated")))
    assert generated.destination == destination
    assert generated.to_dict()["installation_status"] == "not_checked"
    for file in result.files:
        assert (destination / file.path).read_bytes() == file.content.encode("utf-8")
        assert file.sha256 == hashlib.sha256((destination / file.path).read_bytes()).hexdigest()
    for copied in result.copies:
        assert (
            hashlib.sha256((destination / copied.destination).read_bytes()).hexdigest()
            == copied.sha256
        )
    legacy = root / "legacy"
    assert config.workflow_configuration is not None
    generate_functional_kedro_project(
        config.source,
        load_functional_workflow_configuration(config.workflow_configuration),
        legacy,
        project_root=root,
        package_name=config.package_name,
        regression_contract=None
        if config.regression_contract is None
        else load_workflow_regression_contract(config.regression_contract),
    )
    assert set(generated.files) == {
        str(path.relative_to(legacy).as_posix()) for path in legacy.rglob("*") if path.is_file()
    }
    assert all(
        (legacy / file).read_bytes() == (destination / file).read_bytes()
        for file in generated.files
    )


def test_notebook_operation_preserves_existing_audited_generator(tmp_path: Path) -> None:
    root = tmp_path
    source = root / "source.ipynb"
    shutil.copyfile(ROOT / "tests/fixtures/notebooks/simple_training.ipynb", source)
    config = LocalProjectConfiguration(root, source, "notebook")
    inspection = run_local_operation(InspectRequest(config))
    assert inspection.to_dict()["status"] == "inspected"
    result = plan_project(PlanRequest(config))
    assert result.to_dict()["plan"]
    generated = generate_project(GenerateRequest(config, Path("new")))
    legacy = root / "legacy"
    generate_kedro_project(
        plan_notebook_path(source, project_root=root), legacy, package_name=config.package_name
    )
    assert all(
        (legacy / file).read_bytes() == (generated.destination / file).read_bytes()
        for file in generated.files
    )


def _write_notebook(path: Path, sources: tuple[str, ...]) -> None:
    data = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"language_info": {"name": "python"}},
        "cells": [
            {
                "id": f"cell-{index}",
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": source,
            }
            for index, source in enumerate(sources)
        ],
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_catalog_copies_are_previewed_with_exact_input_identity(tmp_path: Path) -> None:
    source = tmp_path / "source.ipynb"
    _write_notebook(
        source,
        (
            "import pandas as pd",
            'df = pd.read_csv("orders.csv")',
            'total = df["amount"].sum()',
        ),
    )
    data = b"amount\n1\n2\n"
    (tmp_path / "orders.csv").write_bytes(data)
    config = LocalProjectConfiguration(tmp_path, source, "notebook")
    result = plan_project(PlanRequest(config))
    assert len(result.copies) == 1
    assert result.copies[0].sha256 == hashlib.sha256(data).hexdigest()
    assert result.copies[0].source == "orders.csv"
    generated = generate_project(GenerateRequest(config, Path("generated")))
    assert (generated.destination / result.copies[0].destination).read_bytes() == data


def test_drift_blocks_generation_instead_of_applying_the_old_preview(tmp_path: Path) -> None:
    root, location = _workspace(tmp_path)
    config = load_local_project_configuration(location)
    assert plan_project(PlanRequest(config)).files
    config.source.write_text(
        config.source.read_text() + '\nprint("unaccounted")\n', encoding="utf-8"
    )
    with pytest.raises(LocalOperationError, match="LO002"):
        run_local_operation(GenerateRequest(config, Path("new_parent/generated")))
    assert not (root / "new_parent").exists()


def test_generation_does_not_import_application_dependencies_or_overwrite(tmp_path: Path) -> None:
    root, location = _workspace(tmp_path)
    config = load_local_project_configuration(location)
    config.source.write_text(
        config.source.read_text().replace(
            "import math", "import math\nimport unavailable_application_dependency"
        ),
        encoding="utf-8",
    )
    assert run_local_operation(PlanRequest(config)).to_dict()["status"] == "planned"
    result = run_local_operation(GenerateRequest(config, Path("generated")))
    assert result.to_dict()["status"] == "generated"
    sentinel = root / "generated/sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(LocalOperationError, match="already exists"):
        run_local_operation(GenerateRequest(config, Path("generated")))
    assert sentinel.read_text() == "keep"


@pytest.mark.parametrize("kind", ["notebook", "functional"])
def test_blocked_inspection_is_not_conversion_success(tmp_path: Path, kind: str) -> None:
    root, location = _workspace(tmp_path)
    config = load_local_project_configuration(location)
    if kind == "notebook":
        source = root / "source.ipynb"
        _write_notebook(source, ("%time value = 1",))
        config = LocalProjectConfiguration(root, source, "notebook")
    else:
        config.source.write_text("print('unsupported')\n", encoding="utf-8")
    assert run_local_operation(InspectRequest(config)).to_dict()["status"] == "blocked"


def test_unknown_request_and_missing_source_have_typed_diagnostics(tmp_path: Path) -> None:
    request: Any = "not-a-request"
    with pytest.raises(LocalOperationError, match="Unsupported"):
        run_local_operation(request)
    config = LocalProjectConfiguration(tmp_path, Path("missing.ipynb"), "notebook")
    with pytest.raises(LocalOperationError) as error:
        run_local_operation(InspectRequest(config))
    assert error.value.code == "LO002"
    assert error.value.__cause__ is not None


def test_modified_functional_plan_is_rejected_by_the_extracted_renderer(tmp_path: Path) -> None:
    root, location = _workspace(tmp_path)
    config = load_local_project_configuration(location)
    plan = plan_functional_workflow_path(
        config.source,
        load_functional_workflow_configuration(root / "examples/functional_workflow/workflow.json"),
        project_root=root,
    )
    modified = replace(
        plan, steps=(replace(plan.steps[0], source="prepared = 999"), *plan.steps[1:])
    )
    with pytest.raises(FunctionalWorkflowError, match="recomputed source wiring"):
        render_functional_workflow(modified, root=root, package_name="example")


def test_cli_reuses_local_operations_and_keeps_paths_independent_of_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, location = _workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    for command in ("inspect", "plan", "generate"):
        arguments = ["project", command, str(location)]
        if command == "generate":
            arguments.append("output")
        assert main(arguments) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["operation"] == command
        assert payload["execution_status"] == "not_run"
    assert (root / "output/pyproject.toml").is_file()
    assert not (tmp_path / "output").exists()
    assert main(["project", "generate", str(location), "../escape"]) == 1
    assert "LO001" in capsys.readouterr().err


def test_cli_reports_blocked_inspection_and_invalid_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, location = _workspace(tmp_path)
    config = load_local_project_configuration(location)
    config.source.write_text("print('unsupported')\n", encoding="utf-8")
    assert main(["project", "inspect", str(location)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    assert main(["project", "plan", str(location)]) == 1
    assert "LO002" in capsys.readouterr().err
    location.write_text("{}", encoding="utf-8")
    assert main(["project", "inspect", str(location)]) == 1
    assert "LO001" in capsys.readouterr().err


def test_configured_profile_is_reused_in_file_preview(tmp_path: Path) -> None:
    root, location = _workspace(tmp_path)
    profile = root / "profile.json"
    shutil.copyfile(ROOT / "examples/kedro_profiles/team_training.json", profile)
    config = replace(load_local_project_configuration(location), architecture_profile=profile)
    exported = config.to_dict()
    assert exported["architecture_profile"] == "profile.json"
    preview = plan_project(PlanRequest(config))
    manifest = next(item for item in preview.files if item.path == "architecture-profile.json")
    assert json.loads(manifest.content)["profile"]["pipeline_name"] == "training"


def test_operations_recheck_paths_after_configuration_was_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, location = _workspace(tmp_path)
    config = load_local_project_configuration(location)
    original_resolve = Path.resolve

    def retarget(path: Path, *args: Any, **kwargs: Any) -> Path:
        if path == config.source:
            return tmp_path / "outside.py"
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", retarget)
    with pytest.raises(LocalOperationError, match="inside project_root"):
        run_local_operation(GenerateRequest(config, Path("generated")))
    assert not (root / "generated").exists()


def test_external_catalog_copy_is_rejected_without_reading_or_writing(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    _write_notebook(
        root / "source.ipynb",
        ("import pandas as pd", 'df = pd.read_csv("../outside.csv")', 'total = df["amount"].sum()'),
    )
    (tmp_path / "outside.csv").write_text("amount\n7\n", encoding="utf-8")
    config = LocalProjectConfiguration(root, root / "source.ipynb", "notebook")
    with pytest.raises(LocalOperationError, match="inside project_root"):
        run_local_operation(PlanRequest(config))
    assert set(root.iterdir()) == {root / "source.ipynb"}


@pytest.mark.parametrize("name", ["functional", "notebook"])
def test_committed_local_configurations_match_their_engine_paths(name: str) -> None:
    config = load_local_project_configuration(ROOT / f"examples/local_operations/{name}.json")
    assert config.project_root == ROOT
    result = run_local_operation(PlanRequest(config)).to_dict()
    assert result["status"] == "planned"
    assert result["configuration"] == config.to_dict()
