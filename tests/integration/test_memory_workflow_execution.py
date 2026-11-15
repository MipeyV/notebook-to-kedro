"""Trusted domain results survive in-process execution without coercion or persistence."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, DatasetError, MemoryDataset
from kedro.runner import SequentialRunner, ThreadRunner

from notebook_to_kedro import (
    GenerateRequest,
    KedroArchitectureProfile,
    LocalProjectConfiguration,
    PlanRequest,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
    run_local_operation,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_files"
SOURCE = EXAMPLE / "src/reference_ml/memory_workflow.py"


@pytest.fixture(autouse=True)
def clean_modules() -> Iterator[None]:
    prefixes = {"reference_ml", "memory_case", "json_fallback_case", "memory_fail_case"}
    prior = {name: module for name, module in sys.modules.items() if name.split(".")[0] in prefixes}
    for name in prior:
        del sys.modules[name]
    yield
    for name in list(sys.modules):
        if name.split(".")[0] in prefixes:
            del sys.modules[name]
    sys.modules.update(prior)


def _catalog(project: Path) -> DataCatalog:
    loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    for name, value in loader["parameters"].items():
        catalog[f"params:{name}"] = MemoryDataset(value)
    return catalog


@pytest.mark.integration
@pytest.mark.parametrize("custom_profile", [False, True])
@pytest.mark.parametrize("threaded", [False, True])
def test_catalog_retains_the_exact_typed_final_object_without_serialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    custom_profile: bool,
    threaded: bool,
) -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "memory_workflow.json")
    profile = (
        KedroArchitectureProfile("test.memory", "1.0.0", "training", "ml_")
        if custom_profile
        else None
    )
    project = tmp_path / "project"
    generate_functional_kedro_project(
        SOURCE,
        config,
        project,
        project_root=ROOT,
        package_name="memory_case",
        architecture_profile=profile,
    )
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    workflow = importlib.import_module("reference_ml.memory_workflow")
    domain = importlib.import_module("reference_ml.domain")
    pipeline_name = "notebook_pipeline" if profile is None else profile.pipeline_name
    nodes = importlib.import_module(f"memory_case.pipelines.{pipeline_name}.nodes")
    original = workflow.evaluate_candidate
    observed: dict[str, Any] = {}

    def evaluate(dataset: Any, protocol: Any, candidate: Any) -> Any:
        result = original(dataset, protocol, candidate)
        observed.update(dataset=dataset, protocol=protocol, result=result)
        return result

    monkeypatch.setattr(nodes, "evaluate_candidate", evaluate)
    pipeline = importlib.import_module("memory_case.pipeline_registry").register_pipelines()[
        "__default__"
    ]
    catalog = _catalog(project)
    (ThreadRunner() if threaded else SequentialRunner()).run(pipeline, catalog)
    result = catalog.load("result")
    assert result is observed["result"]
    assert type(result) is domain.EvaluationResult
    assert result.dataset is observed["dataset"]
    assert result.protocol is observed["protocol"]
    assert result.total == 12.5
    assert domain.TRACE == ["snapshot", "protocol", "evaluate"]
    result.notes.append("reviewed in this process")
    assert catalog.load("result").notes == ["reviewed in this process"]
    with pytest.raises(TypeError, match="serializable"):
        json.dumps(result)
    assert not (project / "data/08_reporting").exists()
    assert (project / "src/reference_ml/memory_workflow.py").read_bytes() == SOURCE.read_bytes()
    # A newly constructed catalog has no persisted output to recover.
    with pytest.raises(DatasetError):
        _catalog(project).load("result")


@pytest.mark.integration
def test_explicit_json_mode_does_not_silently_fall_back_for_an_opaque_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = replace(
        load_functional_workflow_configuration(EXAMPLE / "memory_workflow.json"),
        outputs=(("result", "data/08_reporting/result.json"),),
    )
    project = tmp_path / "project"
    generate_functional_kedro_project(
        SOURCE, config, project, project_root=ROOT, package_name="json_fallback_case"
    )
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline = importlib.import_module("json_fallback_case.pipeline_registry").register_pipelines()[
        "__default__"
    ]
    with pytest.raises(DatasetError, match="serializable"):
        SequentialRunner().run(pipeline, _catalog(project))
    assert (
        json.loads((project / "conf/base/catalog.yml").read_text())["result"]["type"]
        == "json.JSONDataset"
    )


@pytest.mark.integration
def test_application_failure_preserves_its_exception_and_leaves_the_new_result_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    generate_functional_kedro_project(
        SOURCE,
        load_functional_workflow_configuration(EXAMPLE / "memory_workflow.json"),
        project,
        project_root=ROOT,
        package_name="memory_fail_case",
    )
    (project / "data/01_raw/snapshot_path/measurements.metadata.json").write_text(
        '{"unit":"wrong"}'
    )
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline = importlib.import_module("memory_fail_case.pipeline_registry").register_pipelines()[
        "__default__"
    ]
    catalog = _catalog(project)
    with pytest.raises(ValueError, match="does not match"):
        SequentialRunner().run(pipeline, catalog)
    with pytest.raises(DatasetError):
        catalog.load("result")
    assert not (project / "data/08_reporting").exists()


@pytest.mark.integration
@pytest.mark.parametrize("custom_profile", [False, True])
def test_schema_15_json_mode_still_delivers_working_json_regressions(
    tmp_path: Path, *, custom_profile: bool
) -> None:
    example = ROOT / "examples/functional_package"
    config = replace(
        load_functional_workflow_configuration(example / "workflow.json"), schema_version="1.5"
    )
    profile = (
        KedroArchitectureProfile("test.json15", "1.0.0", "training", "ml_")
        if custom_profile
        else None
    )
    project = tmp_path / "project"
    generate_functional_kedro_project(
        example / "src/example_ml/workflow.py",
        config,
        project,
        project_root=ROOT,
        package_name="json15_case",
        architecture_profile=profile,
        regression_contract=load_workflow_regression_contract(example / "regression.json"),
    )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(project / ".pytest-runtime"),
            "-q",
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout


@pytest.mark.integration
def test_local_operation_preview_exposes_memory_policy_but_never_a_business_result(
    tmp_path: Path,
) -> None:
    config = LocalProjectConfiguration(
        project_root=ROOT,
        source=SOURCE,
        source_kind="functional",
        workflow_configuration=EXAMPLE / "memory_workflow.json",
    )
    preview: Any = run_local_operation(PlanRequest(config)).to_dict()
    assert preview["execution_status"] == "not_run"
    assert preview["plan"]["result_boundary"]["mode"] == "memory"
    assert preview["plan"]["result_boundary"]["persistence"] == "none"
    # Publish to a private contained fixture root instead of writing the referenced project.
    shutil.copytree(EXAMPLE, tmp_path / "example")
    data = json.loads((tmp_path / "example/memory_workflow.json").read_text())
    data["source_package"] = "example/src/reference_ml"
    for value in data["file_inputs"].values():
        value["path"] = value["path"].replace("examples/functional_files", "example")
        value["sidecars"] = [
            item.replace("examples/functional_files", "example") for item in value["sidecars"]
        ]
    (tmp_path / "workflow.json").write_text(json.dumps(data))
    local = replace(
        config,
        project_root=tmp_path,
        source=tmp_path / "example/src/reference_ml/memory_workflow.py",
        workflow_configuration=tmp_path / "workflow.json",
    )
    published = run_local_operation(GenerateRequest(local, Path("out"))).to_dict()
    assert published["execution_status"] == "not_run"
    assert not (tmp_path / "out/data/08_reporting").exists()
