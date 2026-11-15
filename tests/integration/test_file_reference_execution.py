"""Synthetic domain loaders receive staged paths and retain responsibility for validation."""

from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner, ThreadRunner

from notebook_to_kedro import (
    GenerateRequest,
    KedroArchitectureProfile,
    LocalProjectConfiguration,
    PlanRequest,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    run_local_operation,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_files"
SOURCE = EXAMPLE / "src/reference_ml/workflow.py"


@pytest.fixture(autouse=True)
def clean_modules() -> Iterator[None]:
    prefixes = {"reference_ml", "files_case", "invalid_files_case"}
    prior = {name: module for name, module in sys.modules.items() if name.split(".")[0] in prefixes}
    for name in prior:
        del sys.modules[name]
    yield
    for name in list(sys.modules):
        if name.split(".")[0] in prefixes:
            del sys.modules[name]
    sys.modules.update(prior)


@pytest.mark.integration
@pytest.mark.parametrize("custom_profile", [False, True])
@pytest.mark.parametrize("threaded", [False, True])
def test_copied_file_paths_keep_original_loaders_domain_types_identity_and_call_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    custom_profile: bool,
    threaded: bool,
) -> None:
    destination = tmp_path / "project"
    profile = (
        KedroArchitectureProfile("test.files", "1.0.0", "training", "ml_")
        if custom_profile
        else None
    )
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    generate_functional_kedro_project(
        SOURCE,
        config,
        destination,
        project_root=ROOT,
        package_name="files_case",
        architecture_profile=profile,
    )
    monkeypatch.syspath_prepend(str(destination / "src"))
    monkeypatch.chdir(destination)
    domain = importlib.import_module("reference_ml.domain")
    workflow = importlib.import_module("reference_ml.workflow")
    assert domain.__file__ is not None
    assert Path(domain.__file__).is_relative_to(destination)
    assert (destination / "src/reference_ml/workflow.py").read_bytes() == SOURCE.read_bytes()
    pipeline_name = "notebook_pipeline" if profile is None else profile.pipeline_name
    nodes = importlib.import_module(f"files_case.pipelines.{pipeline_name}.nodes")
    original = workflow.evaluate_candidate
    identities = []
    loaded: dict[str, Any] = {}

    def snapshot(path: str) -> Any:
        loaded["dataset"] = workflow.load_snapshot(path)
        return loaded["dataset"]

    def protocol_input(path: str) -> Any:
        loaded["protocol"] = workflow.load_protocol(path)
        return loaded["protocol"]

    def evaluate(dataset: Any, protocol: Any, candidate: Any) -> Any:
        assert type(dataset) is domain.Measurements
        assert type(protocol) is domain.Protocol
        assert dataset is loaded["dataset"]
        assert protocol is loaded["protocol"]
        identities.append((dataset, protocol))
        return original(dataset, protocol, candidate)

    monkeypatch.setattr(nodes, "evaluate_candidate", evaluate)
    monkeypatch.setattr(nodes, "load_snapshot", snapshot)
    monkeypatch.setattr(nodes, "load_protocol", protocol_input)
    loader = OmegaConfigLoader(conf_source=str(destination / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    for name, value in loader["parameters"].items():
        catalog[f"params:{name}"] = MemoryDataset(value)
    assert catalog.load("snapshot_path") == "data/01_raw/snapshot_path/measurements.txt"
    registry = importlib.import_module("files_case.pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    runner = ThreadRunner() if threaded else SequentialRunner()
    runner.run(pipeline, catalog)
    assert domain.TRACE == ["snapshot", "protocol", "evaluate"]
    assert len(identities) == 1
    assert json.loads((destination / "data/08_reporting/result.json").read_text()) == {
        "total": 12.5,
        "unit": "widgets",
    }
    assert "tests/test_workflow_regressions.py" not in {
        path.relative_to(destination).as_posix() for path in destination.rglob("*.py")
    }


@pytest.mark.integration
@pytest.mark.parametrize("change", ["missing", "mismatch"])
def test_existing_domain_reader_rejects_missing_or_incompatible_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    destination = tmp_path / "project"
    generate_functional_kedro_project(
        SOURCE,
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
        destination,
        project_root=ROOT,
        package_name="invalid_files_case",
    )
    sidecar = destination / "data/01_raw/snapshot_path/measurements.metadata.json"
    if change == "missing":
        sidecar.unlink()
    else:
        sidecar.write_text('{"unit":"incompatible"}')
    monkeypatch.syspath_prepend(str(destination / "src"))
    monkeypatch.chdir(destination)
    workflow = importlib.import_module("reference_ml.workflow")
    error = FileNotFoundError if change == "missing" else ValueError
    with pytest.raises(error):
        workflow.workflow(
            "data/01_raw/snapshot_path/measurements.txt",
            "data/01_raw/protocol_path/study.json",
            {"bias": 0.5},
        )
    assert not (destination / "data/08_reporting/result.json").exists()
    assert (
        json.loads((EXAMPLE / "data/measurements.metadata.json").read_text())["unit"] == "widgets"
    )


@pytest.mark.integration
def test_local_operations_preview_and_publish_the_same_file_bundle(tmp_path: Path) -> None:
    shutil.copytree(EXAMPLE, tmp_path / "example")
    data = json.loads((tmp_path / "example/workflow.json").read_text())
    data["source_package"] = "example/src/reference_ml"
    for value in data["file_inputs"].values():
        value["path"] = value["path"].replace("examples/functional_files", "example")
        value["sidecars"] = [
            item.replace("examples/functional_files", "example") for item in value["sidecars"]
        ]
    (tmp_path / "workflow.json").write_text(json.dumps(data))
    config = LocalProjectConfiguration(
        project_root=tmp_path,
        source=tmp_path / "example/src/reference_ml/workflow.py",
        source_kind="functional",
        workflow_configuration=tmp_path / "workflow.json",
    )
    preview: Any = run_local_operation(PlanRequest(config)).to_dict()
    assert preview["execution_status"] == "not_run"
    assert preview["plan"]["schema_version"] == "1.3"
    assert not (tmp_path / "out").exists()
    published = run_local_operation(GenerateRequest(config, Path("out"))).to_dict()
    assert published["execution_status"] == "not_run"
    assert (tmp_path / "out/data/01_raw/snapshot_path/measurements.metadata.json").read_bytes() == (
        EXAMPLE / "data/measurements.metadata.json"
    ).read_bytes()
