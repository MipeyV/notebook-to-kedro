"""Declared packages retain complete bounded inventories without source execution."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from notebook_to_kedro import (
    FunctionalWorkflowConfiguration,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    plan_functional_workflow_path,
)
from notebook_to_kedro.analysis import source_packages
from notebook_to_kedro.analysis.functional import analyze_functional_blocks
from notebook_to_kedro.analysis.functional_sources import analyze_functional_blocks_path
from notebook_to_kedro.analysis.source_packages import capture_source_package
from notebook_to_kedro.exceptions import FunctionalWorkflowError, ProjectGenerationError
from notebook_to_kedro.generation.kedro.functional import render_functional_workflow
from notebook_to_kedro.generation.kedro.generator import render_kedro_project
from notebook_to_kedro.ir import ConversionPlan
from notebook_to_kedro.ir.functional import SourceUnit
from notebook_to_kedro.semantic.functional_workflow import plan_functional_workflow

ROOT = Path(__file__).parents[3]
EXAMPLE = ROOT / "examples/functional_package"
PACKAGE = "examples/functional_package/src/example_ml"


def _workspace(tmp_path: Path) -> tuple[Path, Path, FunctionalWorkflowConfiguration]:
    shutil.copytree(EXAMPLE, tmp_path / "examples/functional_package")
    source = tmp_path / PACKAGE / "workflow.py"
    config = load_functional_workflow_configuration(
        tmp_path / "examples/functional_package/workflow.json"
    )
    return tmp_path, source, config


def test_package_inventory_context_and_raw_copies_are_explicit(tmp_path: Path) -> None:
    root, source, config = _workspace(tmp_path)
    cache = root / PACKAGE / "__pycache__"
    cache.mkdir()
    (cache / "never.py").write_text("invalid syntax that is not source", encoding="utf-8")
    encoded = root / PACKAGE / "encoded.py"
    encoded.write_bytes(b"# coding: latin-1\r\nlabel = '\xe9'\r\n")
    plan = plan_functional_workflow_path(source, config, project_root=root)
    package = plan.source_package
    assert package is not None
    assert package.module == "example_ml.workflow"
    assert package.excluded_caches == ("__pycache__",)
    assert package.to_dict()["validation_status"] == "compiled_not_executed"
    assert package.to_dict()["dependency_status"] == "not_inferred"
    assert len(package.sha256) == 64
    assert plan.analysis.schema_version == "1.2"
    assert plan.analysis.package_module == "example_ml.workflow"
    assert json.loads(plan.to_json())["schema_version"] == "1.2"
    files, copies = render_functional_workflow(plan, root=root, package_name="generated_case")
    assert Path("src/generated_case/workflow_source.py") not in files
    assert any(path == Path("src/example_ml/encoded.py") for _, path in copies)
    destination = tmp_path / "generated"
    generate_functional_kedro_project(source, config, destination, project_root=root)
    assert (destination / "src/example_ml/encoded.py").read_bytes() == encoded.read_bytes()
    for item in package.files:
        target = destination / "src/example_ml" / item.path
        assert hashlib.sha256(target.read_bytes()).hexdigest() == item.sha256
    manifest = json.loads((destination / "functional-workflow.json").read_text())
    assert manifest["source_module"] == "src/example_ml/workflow.py"
    assert manifest["source_package_sha256"] == package.sha256
    assert not (destination / "src/example_ml/__pycache__").exists()
    assert "example_ml" not in sys.modules


@pytest.mark.parametrize("relative", ["", "..", "/absolute", "C:/drive", "a\\b", "a//b", "a/./b"])
def test_package_root_paths_are_contained_and_portable(tmp_path: Path, relative: str) -> None:
    with pytest.raises(FunctionalWorkflowError):
        capture_source_package(tmp_path, tmp_path / "workflow.py", relative)


@pytest.mark.parametrize("name", ["json", "kedro", "kedro_datasets", "bad-name", "_private", "été"])
def test_package_names_cannot_shadow_supported_namespaces(tmp_path: Path, name: str) -> None:
    package = tmp_path / name
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    source = package / "workflow.py"
    source.write_text("", encoding="utf-8")
    with pytest.raises(FunctionalWorkflowError, match="namespaces"):
        capture_source_package(tmp_path, source, name)


@pytest.mark.parametrize("case", ["missing", "file", "outside", "notebook", "uncaptured"])
def test_package_and_source_must_be_regular_and_contained(tmp_path: Path, case: str) -> None:
    root, source, _ = _workspace(tmp_path)
    relative = PACKAGE
    if case == "missing":
        relative = "absent"
    elif case == "file":
        relative += "/workflow.py"
    elif case == "outside":
        source = root / "outside.py"
        source.write_text("", encoding="utf-8")
    elif case == "notebook":
        source = source.with_suffix(".ipynb")
    else:
        source = source.with_name("absent.py")
    with pytest.raises(FunctionalWorkflowError):
        capture_source_package(root, source, relative)


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("bad-name.py", b"x = 1", "identifiers"),
        ("class.py", b"x = 1", "identifiers"),
        ("loose/module.py", b"x = 1", "ancestors"),
        ("extra.pyc", b"bytecode", "Compiled"),
        ("extra.py", b"def broken(:", "capture"),
        ("extra.py", b"return 1", "capture"),
        ("extra.py", b"\xff", "capture"),
        ("extra.py", b"from .absent import value", "no captured module"),
        ("extra.py", b"from ..outside import value", "escapes"),
    ],
)
def test_invalid_or_incomplete_packages_block_publication(
    tmp_path: Path, filename: str, content: bytes, message: str
) -> None:
    root, source, config = _workspace(tmp_path)
    path = root / PACKAGE / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    with pytest.raises(FunctionalWorkflowError, match=message):
        generate_functional_kedro_project(source, config, root / "out", project_root=root)
    assert not (root / "out").exists()


def test_regular_packages_nested_initializers_and_imports_are_captured(tmp_path: Path) -> None:
    root, source, _ = _workspace(tmp_path)
    package = root / PACKAGE
    (package / "__init__.py").write_text("from . import settings\n", encoding="utf-8")
    nested = package / "nested"
    nested.mkdir()
    (nested / "__init__.py").write_text("from ..domain import Intermediate\n", encoding="utf-8")
    (nested / "tool.py").write_text(
        "import example_ml.transforms\nimport absent_external\n", encoding="utf-8"
    )
    snapshot = capture_source_package(root, nested / "__init__.py", PACKAGE)
    assert snapshot.module == "example_ml.nested"
    assert any(item.module == "example_ml" and item.local for item in snapshot.imports)
    assert any(item.module == "absent_external" and not item.local for item in snapshot.imports)
    assert "absent_external" not in sys.modules
    (package / "__init__.py").unlink()
    with pytest.raises(FunctionalWorkflowError, match="__init__"):
        capture_source_package(root, source, PACKAGE)


@pytest.mark.parametrize("kind", ["link", "reparse", "special"])
def test_source_package_rejects_links_and_special_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    root, source, _ = _workspace(tmp_path)
    target = root / PACKAGE / "assets/offset.json"
    original = Path.lstat

    def changed(path: Path) -> Any:
        if path == target:
            return SimpleNamespace(
                st_mode=stat.S_IFLNK
                if kind == "link"
                else stat.S_IFDIR
                if kind == "reparse"
                else stat.S_IFIFO,
                st_file_attributes=0x400 if kind == "reparse" else 0,
            )
        return original(path)

    monkeypatch.setattr(Path, "lstat", changed)
    with pytest.raises(FunctionalWorkflowError, match=r"links|regular"):
        capture_source_package(root, source, PACKAGE)


@pytest.mark.parametrize(
    "limit",
    ["MAX_PACKAGE_FILES", "MAX_PACKAGE_BYTES", "MAX_PACKAGE_FILE_BYTES", "MAX_PYTHON_BYTES"],
)
def test_package_capture_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    root, source, _ = _workspace(tmp_path)
    monkeypatch.setattr(source_packages, limit, 1)
    with pytest.raises(FunctionalWorkflowError, match=r"limit|files"):
        capture_source_package(root, source, PACKAGE)


@pytest.mark.parametrize("changed", ["transforms.py", "assets/offset.json", "new.json"])
def test_package_drift_is_rejected_when_rendering_a_captured_plan(
    tmp_path: Path, changed: str
) -> None:
    root, source, config = _workspace(tmp_path)
    plan = plan_functional_workflow_path(source, config, project_root=root)
    path = root / PACKAGE / changed
    path.write_text("# changed\n" if path.suffix == ".py" else "{}", encoding="utf-8")
    with pytest.raises(FunctionalWorkflowError, match="captured inventory"):
        render_functional_workflow(plan, root=root, package_name="drift")


def test_package_capture_never_executes_initializers_or_dependencies(tmp_path: Path) -> None:
    root, source, config = _workspace(tmp_path)
    marker = root / "executed"
    (root / PACKAGE / "__init__.py").write_text(
        f"open({str(marker)!r}, 'w').close()\n", encoding="utf-8"
    )
    generate_functional_kedro_project(source, config, root / "out", project_root=root)
    assert not marker.exists()


@pytest.mark.parametrize("value", [None, "", "../escape", "/absolute", "a\\b", "a//b", "C:drive"])
def test_schema_1_3_requires_explicit_package_paths(value: Any) -> None:
    data = load_functional_workflow_configuration(EXAMPLE / "workflow.json").to_dict()
    data["source_package"] = value
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(data)


def test_package_configuration_and_context_cannot_be_silently_discarded(tmp_path: Path) -> None:
    root, source, config = _workspace(tmp_path)
    data = config.to_dict()
    del data["source_package"]
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(data)
    with pytest.raises(FunctionalWorkflowError, match=r"schema 1\.3"):
        replace(config, schema_version="1.2")
    plan = plan_functional_workflow_path(source, config, project_root=root)
    assert plan.source_package is not None
    with pytest.raises(FunctionalWorkflowError, match="matching captured"):
        plan_functional_workflow(plan.analysis, config)
    for modified in (
        replace(plan.source_package, root="other"),
        replace(plan.source_package, module="example_ml.other"),
        replace(plan.source_package, files=()),
    ):
        with pytest.raises(FunctionalWorkflowError, match="matching captured"):
            plan_functional_workflow(plan.analysis, config, source_package=modified)
    old = replace(config, schema_version="1.2", source_package=None)
    with pytest.raises(FunctionalWorkflowError, match="explicit source_package"):
        plan_functional_workflow(plan.analysis, old, source_package=plan.source_package)
    ordinary = analyze_functional_blocks_path(source, project_root=root)
    with pytest.raises(FunctionalWorkflowError, match="explicit source_package"):
        plan_functional_workflow(ordinary, old, source_package=plan.source_package)


def test_relative_selected_imports_require_context_and_preserve_raw_source(tmp_path: Path) -> None:
    root, source, config = _workspace(tmp_path)
    text = source.read_text().replace("from example_ml.", "from .")
    source.write_text(text, encoding="utf-8", newline="")
    assert not analyze_functional_blocks_path(source).complete
    plan = plan_functional_workflow_path(source, config, project_root=root)
    assert plan.analysis.complete
    assert plan.analysis.sources[0].source == text
    assert (
        plan.analysis.structure_sha256
        != analyze_functional_blocks_path(EXAMPLE / "src/example_ml/workflow.py").structure_sha256
    )


@pytest.mark.parametrize("context", ["", "bad-name", "class", "pkg..flow", "été.flow"])
def test_invalid_declared_module_contexts_are_rejected(context: str) -> None:
    unit = SourceUnit("module", "source.py", "python", "a" * 64, "def f(x):\n    return x")
    with pytest.raises(ValueError, match="context"):
        analyze_functional_blocks((unit,), package_module=context)


def test_package_mode_requires_one_python_unit() -> None:
    unit = SourceUnit("cell", "source.ipynb", "notebook", "a" * 64, "def f(x):\n    return x")
    with pytest.raises(ValueError, match="context"):
        analyze_functional_blocks((unit,), package_module="pkg.flow")
    with pytest.raises(ValueError, match="context"):
        analyze_functional_blocks((), package_module="pkg.flow")


def test_generated_and_source_package_names_cannot_collide(tmp_path: Path) -> None:
    root, source, config = _workspace(tmp_path)
    with pytest.raises(ProjectGenerationError, match="collides"):
        generate_functional_kedro_project(
            source, config, root / "out", project_root=root, package_name="example_ml"
        )
    plan = ConversionPlan("1.0", "test", "source.py", ())
    with pytest.raises(ProjectGenerationError):
        render_kedro_project(plan, source_package_name="bad-name")
    assert not (root / "out").exists()


def test_package_context_rejects_missing_units_and_hash_mismatches(tmp_path: Path) -> None:
    root, source, config = _workspace(tmp_path)
    plan = plan_functional_workflow_path(source, config, project_root=root)
    assert plan.source_package is not None
    package = plan.source_package
    with pytest.raises(FunctionalWorkflowError, match="matching captured"):
        plan_functional_workflow(replace(plan.analysis, sources=()), config, source_package=package)
    files = tuple(
        replace(item, sha256="0" * 64) if item.path == package.source_file else item
        for item in package.files
    )
    with pytest.raises(FunctionalWorkflowError, match="matching captured"):
        plan_functional_workflow(
            plan.analysis, config, source_package=replace(package, files=files)
        )
    old = replace(config, schema_version="1.2", source_package=None)
    with pytest.raises(FunctionalWorkflowError, match="explicit source_package"):
        plan_functional_workflow(plan.analysis, old)


def test_resolution_drift_cannot_redirect_a_package_outside_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, source, _ = _workspace(tmp_path)
    original = Path.resolve

    def redirected(path: Path, *args: Any, **kwargs: Any) -> Path:
        return (
            root.parent / "outside" if path == root / PACKAGE else original(path, *args, **kwargs)
        )

    monkeypatch.setattr(Path, "resolve", redirected)
    with pytest.raises(FunctionalWorkflowError, match="inside source_package"):
        capture_source_package(root, source, PACKAGE)
