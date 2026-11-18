"""Preserved shared identity, mutation order and failures through actual Kedro runners."""

from __future__ import annotations

import copy
import importlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.pipeline import Pipeline, node
from kedro.runner import SequentialRunner, ThreadRunner

from notebook_to_kedro import (
    FunctionalWorkflowConfiguration,
    KedroArchitectureProfile,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
)

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_shared_data"


def _generated(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    package: str,
    *,
    suffix: str = ".py",
    custom_profile: bool = False,
) -> tuple[Any, Pipeline, DataCatalog, Path]:
    project = root / "project"
    generate_functional_kedro_project(
        EXAMPLE / ("workflow" + suffix),
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
        project,
        project_root=ROOT,
        package_name=package,
        architecture_profile=KedroArchitectureProfile("shared.test", "1.0.0", "training", "ml_")
        if custom_profile
        else None,
        regression_contract=load_workflow_regression_contract(EXAMPLE / "regression.json"),
    )
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline_name = "training" if custom_profile else "notebook_pipeline"
    functions = importlib.import_module(f"{package}.pipelines.{pipeline_name}.nodes")
    registry = importlib.import_module(f"{package}.pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    for name, value in loader["parameters"].items():
        catalog[f"params:{name}"] = MemoryDataset(value)
    return functions, pipeline, catalog, project


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("custom_profile", [False, True])
@pytest.mark.parametrize("threaded", [False, True])
@pytest.mark.parametrize("scenario_id", ["positive", "negative", "empty"])
def test_source_and_registered_nodes_keep_shared_objects_and_order(  # noqa: PLR0913
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    scenario_id: str,
    *,
    custom_profile: bool,
    threaded: bool,
) -> None:
    package = f"shared_{suffix[1:]}_{int(custom_profile)}_{int(threaded)}_{scenario_id}"
    functions, pipeline, catalog, project = _generated(
        tmp_path,
        monkeypatch,
        package,
        suffix=suffix,
        custom_profile=custom_profile,
    )
    scenarios = load_workflow_regression_contract(EXAMPLE / "regression.json").to_dict()[
        "scenarios"
    ]
    case = next(c for c in scenarios if c["id"] == scenario_id)
    expected = runpy.run_path(str(EXAMPLE / "workflow.py"))["workflow"](
        **copy.deepcopy(case["inputs"]),
        **case["parameters"],
    )
    assert expected == case["expected"]
    (project / "data/01_raw/raw_values.json").write_text(
        json.dumps(case["inputs"]["raw_values"]),
        encoding="utf-8",
    )
    for name, value in case["parameters"].items():
        catalog[f"params:{name}"] = MemoryDataset(value)
    original = {
        name: getattr(functions, name)
        for name in ("create_buffer", "read_left", "read_right", "combine")
    }
    trace: list[str] = []
    objects: dict[str, Any] = {}

    def create_buffer(raw_values: list[Any]) -> Any:
        trace.append("create")
        objects["raw"] = raw_values
        objects["buffer"] = original["create_buffer"](raw_values)
        return objects["buffer"]

    def read_left(buffer: Any, gain: float) -> Any:
        assert trace == ["create"]
        assert buffer is objects["buffer"]
        trace.append("left")
        objects["left"] = original["read_left"](buffer, gain)
        return objects["left"]

    def read_right(buffer: Any, bias: float) -> Any:
        assert trace == ["create", "left"]
        assert buffer is objects["buffer"]
        trace.append("right")
        objects["right"] = original["read_right"](buffer, bias)
        return objects["right"]

    def combine(left: Any, right: Any) -> Any:
        assert trace == ["create", "left", "right"]
        assert left is objects["left"]
        assert right is objects["right"]
        assert left["buffer"] is right["buffer"] is objects["buffer"]
        assert left["buffer"]["values"] is objects["raw"]
        trace.append("combine")
        return original["combine"](left, right)

    for function in (create_buffer, read_left, read_right, combine):
        monkeypatch.setattr(functions, function.__name__, function)
    assert [len(group) for group in pipeline.grouped_nodes] == [1, 1, 1, 1]
    runner = ThreadRunner(max_workers=3) if threaded else SequentialRunner()
    runner.run(pipeline, catalog)
    assert trace == ["create", "left", "right", "combine"]
    assert objects["buffer"]["events"] == ["left", "right"]
    assert catalog.load("report") == expected


@pytest.mark.integration
@pytest.mark.parametrize("failure", ["left", "right"])
@pytest.mark.parametrize("threaded", [False, True])
def test_ordered_shared_consumers_stop_after_the_original_failure_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    *,
    threaded: bool,
) -> None:
    functions, pipeline, catalog, project = _generated(
        tmp_path,
        monkeypatch,
        f"shared_error_{failure}_{int(threaded)}",
    )
    original_left, original_right = functions.read_left, functions.read_right
    trace: list[str] = []
    error = RuntimeError("Original shared-consumer failure")

    def read_left(buffer: Any, gain: float) -> Any:
        trace.append("left")
        if failure == "left":
            raise error
        return original_left(buffer, gain)

    def read_right(buffer: Any, bias: float) -> Any:
        trace.append("right")
        if failure == "right":
            raise error
        return original_right(buffer, bias)

    monkeypatch.setattr(functions, "read_left", read_left)
    monkeypatch.setattr(functions, "read_right", read_right)
    runner = ThreadRunner(max_workers=3) if threaded else SequentialRunner()
    with pytest.raises(RuntimeError, match="Original shared-consumer failure") as caught:
        runner.run(pipeline, catalog)
    assert caught.value is error
    assert trace == (["left"] if failure == "left" else ["left", "right"])
    assert not (project / "data/08_reporting/report.json").exists()


@pytest.mark.integration
def test_deepcopy_storage_breaks_the_required_source_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, pipeline, catalog, _ = _generated(tmp_path, monkeypatch, "shared_copy_control")
    catalog["buffer"] = MemoryDataset(copy_mode="deepcopy")
    with pytest.raises(AssertionError, match="Shared buffer identity changed"):
        SequentialRunner().run(pipeline, catalog)


@pytest.mark.integration
def test_removing_the_order_edge_permits_wrong_shared_mutation_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    functions, pipeline, catalog, _ = _generated(tmp_path, monkeypatch, "shared_order_control")
    original_left, original_right = functions.read_left, functions.read_right
    right_finished = Event()

    def read_left(buffer: Any, gain: float) -> Any:
        assert right_finished.wait(timeout=5), "Unordered right consumer did not start"
        return original_left(buffer, gain)

    def read_right(buffer: Any, bias: float) -> Any:
        result = original_right(buffer, bias)
        right_finished.set()
        return result

    monkeypatch.setattr(functions, "read_left", read_left)
    monkeypatch.setattr(functions, "read_right", read_right)
    original = pipeline.nodes
    unordered = Pipeline(
        [
            original[0],
            original[1],
            node(
                functions.step_0002_read_right,
                inputs={"buffer": "buffer", "bias": "params:bias"},
                outputs="right",
                name=original[2].name,
            ),
            original[3],
        ]
    )
    assert [len(group) for group in unordered.grouped_nodes] == [1, 2, 1]
    with pytest.raises(AssertionError, match="Source call order changed"):
        ThreadRunner(max_workers=3).run(unordered, catalog)


def _run_shipped(project: Path, temporary: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment.pop("PYTEST_ADDOPTS", None)
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(project / "pyproject.toml"),
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(temporary),
            "-q",
            "--tb=short",
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("custom_profile", [False, True])
def test_four_shipped_tests_detect_the_original_arithmetic_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    *,
    custom_profile: bool,
) -> None:
    _, _, _, project = _generated(
        tmp_path,
        monkeypatch,
        f"shared_shipped_{suffix[1:]}_{int(custom_profile)}",
        suffix=suffix,
        custom_profile=custom_profile,
    )
    result = _run_shipped(project, tmp_path / "shipped")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 passed" in result.stdout
    path = next((project / "src").glob("*/workflow_source.py"))
    source = path.read_text()
    changed = source.replace(" * gain", " + gain")
    assert changed != source
    path.write_text(changed, encoding="utf-8")
    result = _run_shipped(project, tmp_path / "mutated")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "3 failed, 1 passed" in result.stdout


@pytest.mark.integration
@pytest.mark.parametrize("threaded", [False, True])
def test_two_arguments_can_explicitly_receive_the_same_intermediate_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    threaded: bool,
) -> None:
    source = tmp_path / "source.py"
    source.write_text(
        "def create(x):\n    return {'value': x}\n"
        "def pair(a, b):\n    assert a is b\n    return {'same': a is b}\n"
        "def workflow(x):\n    shared = create(x)\n    result = pair(shared, shared)\n"
        "    return result\n",
        encoding="utf-8",
    )
    config = FunctionalWorkflowConfiguration.from_dict(
        {
            "schema_version": "1.2",
            "entrypoint": "workflow",
            "inputs": {},
            "parameters": {"x": 1.0},
            "outputs": {"result": "data/08_reporting/result.json"},
            "shared_data": {"schema_version": "1.0", "values": ["shared"]},
        }
    )
    project = tmp_path / "project"
    package = f"shared_alias_{int(threaded)}"
    generate_functional_kedro_project(
        source, config, project, project_root=tmp_path, package_name=package
    )
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    registry = importlib.import_module(f"{package}.pipeline_registry")
    loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    catalog["params:x"] = MemoryDataset(1.0)
    runner = ThreadRunner(max_workers=3) if threaded else SequentialRunner()
    runner.run(registry.register_pipelines()["__default__"], catalog)
    assert catalog.load("result") == {"same": True}
