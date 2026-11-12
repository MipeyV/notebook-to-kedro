"""Trusted paired fixtures exercise real generated Kedro pipelines and JSON catalog I/O."""

from __future__ import annotations

import importlib
import json
import runpy
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner

from notebook_to_kedro import (
    FunctionalWorkflowConfiguration,
    KedroArchitectureProfile,
    generate_functional_kedro_project,
)

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_workflow"


def _reference(path: Path) -> dict[str, Any]:
    if path.suffix == ".py":
        return runpy.run_path(str(path))
    scope: dict[str, Any] = {}
    notebook = json.loads(path.read_text(encoding="utf-8"))
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            exec(compile(cell["source"], "trusted_fixture_cell", "exec"), scope)
    return scope


def _track(module: Any, name: str, counts: Counter[str], observed: list[Any]) -> Any:
    original = getattr(module, name)

    def tracked(*args: Any, **kwargs: Any) -> Any:
        counts[name] += 1
        observed.append((name, args))
        return original(*args, **kwargs)

    return tracked


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("custom_profile", [False, True])
@pytest.mark.parametrize("scenario", [(-3.0, 2.0, 6.0), (0.0, 2.0, 0.0), (1.25, 4.0, 5.0)])
def test_paired_workflows_match_hand_expectations_and_execute_each_call_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    *,
    custom_profile: bool,
    scenario: tuple[float, float, float],
) -> None:
    value, scale, expected = scenario
    source = EXAMPLE / f"workflow{suffix}"
    scope = _reference(source)
    assert scope["workflow"](value, scale) == expected
    source_input = tmp_path / "input.json"
    source_input.write_text(json.dumps(value), encoding="utf-8")
    configuration = FunctionalWorkflowConfiguration(
        "workflow",
        (("values", "input.json"),),
        (("scale", scale),),
        (("total", "data/08_reporting/total.json"),),
    )
    profile = (
        KedroArchitectureProfile("test.functional", "1.0.0", "training", "ml_")
        if custom_profile
        else None
    )
    scenario_id = str(value).replace("-", "n").replace(".", "_")
    package = f"functional_{suffix[1:]}_{int(custom_profile)}_{scenario_id}"
    destination = tmp_path / "project"
    generate_functional_kedro_project(
        source,
        configuration,
        destination,
        project_root=tmp_path,
        package_name=package,
        architecture_profile=profile,
    )
    monkeypatch.syspath_prepend(str(destination / "src"))
    monkeypatch.chdir(destination)
    module = importlib.import_module(f"{package}.workflow_source")
    counts: Counter[str] = Counter()
    observed: list[Any] = []
    for name in ("prepare_values", "summarize"):
        monkeypatch.setattr(module, name, _track(module, name, counts, observed))
    registry = importlib.import_module(f"{package}.pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    loader = OmegaConfigLoader(conf_source=str(destination / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    for name, parameter in loader["parameters"].items():
        catalog[f"params:{name}"] = MemoryDataset(parameter)
    SequentialRunner().run(pipeline, catalog)
    assert json.loads((destination / "data/08_reporting/total.json").read_text()) == expected
    assert (destination / "data/01_raw/values.json").read_bytes() == source_input.read_bytes()
    assert counts == {"prepare_values": 1, "summarize": 1}
    assert [item[0] for item in observed] == ["prepare_values", "summarize"]
    assert observed[1][1] == (value * scale,)
    assert len(pipeline.nodes) == 2
    manifest = json.loads((destination / "functional-workflow.json").read_text())
    assert len(manifest["statement_destinations"]) == len(manifest["analysis"]["statements"])


@pytest.mark.integration
def test_mutable_intermediate_identity_and_internal_helper_calls_are_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "workflow.py"
    source.write_text(
        "def helper(x):\n    x.append(3)\n    return x\n"
        "def first(x):\n    y = helper(x)\n    return y\n"
        "def second(x):\n    x.append(4)\n    total = len(x)\n    return total\n"
        "def workflow(x):\n    a = first(x)\n    total = second(a)\n    return total\n",
        encoding="utf-8",
    )
    assert _reference(source)["workflow"]([1, 2]) == 4
    (tmp_path / "input.json").write_text("[1, 2]", encoding="utf-8")
    configuration = FunctionalWorkflowConfiguration(
        "workflow", (("x", "input.json"),), (), (("total", "data/08_reporting/total.json"),)
    )
    destination = tmp_path / "project"
    generate_functional_kedro_project(
        source,
        configuration,
        destination,
        project_root=tmp_path,
        package_name="functional_mutation",
    )
    monkeypatch.syspath_prepend(str(destination / "src"))
    monkeypatch.chdir(destination)
    module = importlib.import_module("functional_mutation.workflow_source")
    counts: Counter[str] = Counter()
    observed: list[Any] = []
    for name in ("helper", "first", "second"):
        monkeypatch.setattr(module, name, _track(module, name, counts, observed))
    registry = importlib.import_module("functional_mutation.pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    loader = OmegaConfigLoader(conf_source=str(destination / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    SequentialRunner().run(pipeline, catalog)
    assert json.loads((destination / "data/08_reporting/total.json").read_text()) == 4
    assert counts == {"helper": 1, "first": 1, "second": 1}
    assert observed[0][1][0] is observed[2][1][0]
    assert len(pipeline.nodes) == 2
