"""Trusted application writes remain owned, explicit and separate from project publication."""

from __future__ import annotations

import importlib
import json
import pickle
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner, ThreadRunner

from notebook_to_kedro import (
    KedroArchitectureProfile,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_artifacts"
SOURCE = EXAMPLE / "src/artifact_ml/workflow.py"


@pytest.fixture(autouse=True)
def clean_modules() -> Iterator[None]:
    prior = {
        name: module
        for name, module in sys.modules.items()
        if name.split(".")[0] in {"artifact_ml", "artifact_case"}
    }
    for name in prior:
        del sys.modules[name]
    yield
    for name in list(sys.modules):
        if name.split(".")[0] in {"artifact_ml", "artifact_case"}:
            del sys.modules[name]
    sys.modules.update(prior)


def _project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    custom_profile: bool = False,
    file_inputs: bool = False,
) -> tuple[Path, Any, DataCatalog, Any]:
    project = tmp_path / "project"
    profile = (
        KedroArchitectureProfile("test.artifacts", "1.0.0", "training", "ml_")
        if custom_profile
        else None
    )
    generate_functional_kedro_project(
        EXAMPLE / "src/artifact_ml" / ("file_workflow.py" if file_inputs else "workflow.py"),
        load_functional_workflow_configuration(
            EXAMPLE / ("file_workflow.json" if file_inputs else "workflow.json")
        ),
        project,
        project_root=ROOT,
        package_name="artifact_case",
        architecture_profile=profile,
    )
    assert not (project / "artifacts").exists()
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    domain = importlib.import_module("artifact_ml.domain")
    pipeline = importlib.import_module("artifact_case.pipeline_registry").register_pipelines()[
        "__default__"
    ]
    loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    catalog["params:candidate"] = MemoryDataset(loader["parameters"]["candidate"])
    return project, domain, catalog, pipeline


def _owner(pipeline: Any) -> Any:
    return next(node.func for node in pipeline.nodes if node.name.endswith("write_run"))


@pytest.mark.integration
@pytest.mark.parametrize("custom_profile", [False, True])
@pytest.mark.parametrize("threaded", [False, True])
@pytest.mark.parametrize("file_inputs", [False, True])
def test_original_application_creates_artifacts_once_and_keeps_source_order_and_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    custom_profile: bool,
    threaded: bool,
    file_inputs: bool,
) -> None:
    project, domain, catalog, pipeline = _project(
        tmp_path, monkeypatch, custom_profile=custom_profile, file_inputs=file_inputs
    )
    # Check the composable ordering/artifact callable, without claiming process-runner support.
    restored = pickle.loads(pickle.dumps(_owner(pipeline)))
    assert type(restored) is type(_owner(pipeline))
    (ThreadRunner() if threaded else SequentialRunner()).run(pipeline, catalog)
    result = catalog.load("result")
    assert type(result) is domain.RunResult
    assert result.total == 6.5
    assert result.receipt.path == Path("artifacts/example_run")
    assert json.loads((project / "artifacts/example_run/receipt.json").read_text()) == {"bias": 0.5}
    assert domain.TRACE == ["load", "write", "finish"]
    assert (project / "src/artifact_ml/workflow.py").read_bytes() == SOURCE.read_bytes()
    with pytest.raises(FileExistsError):
        SequentialRunner().run(pipeline, catalog)
    assert domain.TRACE.count("write") == 1
    assert json.loads((project / "artifacts/example_run/receipt.json").read_text()) == {"bias": 0.5}


@pytest.mark.integration
@pytest.mark.parametrize("existing", ["directory", "file", "parent_file"])
def test_existing_targets_are_refused_without_touching_owned_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing: str
) -> None:
    project, domain, _, pipeline = _project(tmp_path, monkeypatch)
    target = project / "artifacts/example_run"
    if existing == "parent_file":
        target.parent.write_text("owned parent bytes")
    else:
        target.parent.mkdir()
        if existing == "directory":
            target.mkdir()
            (target / "keep.txt").write_text("owned bytes")
        else:
            target.write_text("owned bytes")
    error = ValueError if existing == "parent_file" else FileExistsError
    with pytest.raises(error):
        _owner(pipeline)(
            _ntk_after=(2.0, 4.0), candidate={"output": "artifacts/example_run", "bias": 0.5}
        )
    assert domain.TRACE == []
    kept = (
        target.parent
        if existing == "parent_file"
        else target / "keep.txt"
        if existing == "directory"
        else target
    )
    assert "owned" in kept.read_text()


@pytest.mark.integration
@pytest.mark.parametrize(
    "candidate", [{"output": "artifacts/different", "bias": 0.5}, {"bias": 0.5}, "not a mapping"]
)
def test_runtime_binding_changes_are_refused_before_the_application_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidate: Any
) -> None:
    project, domain, _, pipeline = _project(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="declared path"):
        _owner(pipeline)(_ntk_after=(2.0,), candidate=candidate)
    assert domain.TRACE == []
    assert not (project / "artifacts").exists()


@pytest.mark.integration
@pytest.mark.parametrize("change", ["wrong_cwd", "marker_drift", "marker_size"])
def test_runtime_requires_the_matching_project_policy_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    project, domain, _, pipeline = _project(tmp_path, monkeypatch)
    if change == "wrong_cwd":
        monkeypatch.chdir(tmp_path)
    else:
        (project / "artifact-policy.json").write_bytes(
            b"x" * 65537 if change == "marker_size" else b"{}"
        )
    error = FileNotFoundError if change == "wrong_cwd" else ValueError
    with pytest.raises(error):
        _owner(pipeline)(
            _ntk_after=(2.0,), candidate={"output": "artifacts/example_run", "bias": 0.5}
        )
    assert domain.TRACE == []
    assert not (project / "artifacts").exists()


@pytest.mark.integration
@pytest.mark.parametrize(
    "entry", ["parent_link", "parent_reparse", "marker_link", "marker_reparse", "target_link"]
)
def test_existing_links_and_reparse_points_are_never_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    project, domain, _, pipeline = _project(tmp_path, monkeypatch)
    target = project / (
        "artifact-policy.json"
        if entry.startswith("marker")
        else "artifacts/example_run"
        if entry.startswith("target")
        else "artifacts"
    )
    original = Path.lstat

    def lstat(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == target:
            reparse = entry.endswith("reparse")
            return SimpleNamespace(
                st_mode=(stat.S_IFREG if entry.startswith("marker") else stat.S_IFDIR)
                if reparse
                else stat.S_IFLNK,
                st_file_attributes=0x400 if reparse else 0,
            )
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(FileExistsError if entry.startswith("target") else ValueError):
        _owner(pipeline)(
            _ntk_after=(2.0,), candidate={"output": "artifacts/example_run", "bias": 0.5}
        )
    assert domain.TRACE == []


@pytest.mark.integration
def test_application_failure_keeps_partial_artifacts_without_cleanup_or_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, domain, catalog, pipeline = _project(tmp_path, monkeypatch)
    catalog["params:candidate"] = MemoryDataset(
        {"output": "artifacts/example_run", "bias": 0.5, "fail_after_write": True}
    )
    with pytest.raises(RuntimeError, match="failed after its owned write"):
        SequentialRunner().run(pipeline, catalog)
    receipt = project / "artifacts/example_run/receipt.json"
    assert json.loads(receipt.read_text()) == {"bias": 0.5}
    assert domain.TRACE == ["load", "write"]
    with pytest.raises(FileExistsError):
        SequentialRunner().run(pipeline, catalog)
    assert domain.TRACE.count("write") == 1
    assert json.loads(receipt.read_text()) == {"bias": 0.5}
