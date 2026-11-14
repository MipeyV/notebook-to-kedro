"""Real Kedro preserves flat candidate values and immutable generation settings."""

from __future__ import annotations

import ast
import importlib
import json
import runpy
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
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
)

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_candidate"


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("custom_profile", [False, True])
@pytest.mark.parametrize("scenario_id", ["positive", "override"])
def test_candidate_mappings_reach_real_kedro_and_keep_supplied_json_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    scenario_id: str,
    *,
    custom_profile: bool,
) -> None:
    contract = load_workflow_regression_contract(EXAMPLE / "regression.json")
    scenario = next(case for case in contract.to_dict()["scenarios"] if case["id"] == scenario_id)
    settings = load_functional_workflow_configuration(EXAMPLE / "workflow.json").to_dict()
    settings["parameters"] = scenario["parameters"]
    config = FunctionalWorkflowConfiguration.from_dict(settings)
    captured = config.to_dict()
    source = EXAMPLE / f"workflow{suffix}"
    package = f"candidate_{suffix[1:]}_{int(custom_profile)}_{scenario_id}"
    destination = tmp_path / "project"
    profile = (
        KedroArchitectureProfile("test.candidate", "1.0.0", "validation", "candidate_")
        if custom_profile
        else None
    )
    generate_functional_kedro_project(
        source,
        config,
        destination,
        project_root=ROOT,
        package_name=package,
        architecture_profile=profile,
    )
    input_path = destination / "data/01_raw/values.json"
    input_path.write_text(json.dumps(scenario["inputs"]["values"]), encoding="utf-8")
    monkeypatch.syspath_prepend(str(destination / "src"))
    monkeypatch.chdir(destination)
    registry = importlib.import_module(f"{package}.pipeline_registry")
    loader = OmegaConfigLoader(conf_source=str(destination / "conf/base"))
    assert loader["parameters"]["candidate"] == scenario["parameters"]["candidate"]
    catalog = DataCatalog.from_config(loader["catalog"])
    catalog["params:candidate"] = MemoryDataset(loader["parameters"]["candidate"])
    SequentialRunner().run(registry.register_pipelines()["__default__"], catalog)
    actual = json.loads((destination / "data/08_reporting/total.json").read_text())
    assert json.dumps(actual, sort_keys=True) == json.dumps(scenario["expected"], sort_keys=True)
    assert config.to_dict() == captured
    assert (destination / "conf/base/parameters.yml").is_file()
    assert ast.dump(ast.parse((destination / f"src/{package}/workflow_source.py").read_text())) == (
        ast.dump(ast.parse((EXAMPLE / "workflow.py").read_text()))
    )


@pytest.mark.integration
def test_consumed_mapping_can_mutate_and_flow_by_identity_without_mutating_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "workflow.py"
    source.write_text(
        "def first(candidate):\n    candidate.update({'seen': True})\n    return candidate\n"
        "def second(value):\n    return value\n"
        "def workflow(candidate):\n    value = first(candidate)\n"
        "    total = second(value)\n    return total\n",
        encoding="utf-8",
    )
    config = FunctionalWorkflowConfiguration.from_dict(
        {
            "schema_version": "1.1",
            "entrypoint": "workflow",
            "inputs": {},
            "parameters": {"candidate": {"seed": 42}},
            "outputs": {"total": "data/08_reporting/total.json"},
        }
    )
    original = runpy.run_path(str(source))["workflow"]({"seed": 42})
    destination = tmp_path / "project"
    generate_functional_kedro_project(
        source, config, destination, project_root=tmp_path, package_name="candidate_mutation"
    )
    monkeypatch.syspath_prepend(str(destination / "src"))
    monkeypatch.chdir(destination)
    module = importlib.import_module("candidate_mutation.workflow_source")
    first, second = module.first, module.second
    received: list[Any] = []

    def track_first(candidate: dict[str, Any]) -> Any:
        received.append(candidate)
        return first(candidate)

    def track_second(value: dict[str, Any]) -> Any:
        received.append(value)
        return second(value)

    monkeypatch.setattr(module, "first", track_first)
    monkeypatch.setattr(module, "second", track_second)
    registry = importlib.import_module("candidate_mutation.pipeline_registry")
    loader = OmegaConfigLoader(conf_source=str(destination / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    catalog["params:candidate"] = MemoryDataset(loader["parameters"]["candidate"])
    SequentialRunner().run(registry.register_pipelines()["__default__"], catalog)
    assert len(received) == 2
    assert received[0] is received[1]
    assert json.loads((destination / "data/08_reporting/total.json").read_text()) == original
    assert config.parameter_values() == {"candidate": {"seed": 42}}
