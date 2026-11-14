"""Flat candidate mappings remain explicit, immutable and single-use across nodes."""

from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    FunctionalWorkflowConfiguration,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    plan_functional_workflow_path,
)
from notebook_to_kedro.analysis.functional import analyze_functional_blocks
from notebook_to_kedro.exceptions import FunctionalWorkflowError
from notebook_to_kedro.ir.functional import SourceUnit
from notebook_to_kedro.semantic.functional_workflow import plan_functional_workflow

ROOT = Path(__file__).parents[3]
EXAMPLE = ROOT / "examples/functional_candidate"


def _settings(**changes: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "entrypoint": "workflow",
        "inputs": {"x": "input.json"},
        "parameters": {"candidate": {"name": "synthetic", "seed": 42}},
        "outputs": {"total": "data/08_reporting/total.json"},
        **changes,
    }


def _analysis(body: str) -> Any:
    source = (
        "def f(x):\n    return x\ndef g(x, y):\n    return x\ndef workflow(x, candidate):\n" + body
    )
    return analyze_functional_blocks(
        (SourceUnit("module", "workflow.py", "python", "a" * 64, source),)
    )


def test_mapping_configuration_is_copied_immutable_and_round_trips(tmp_path: Path) -> None:
    data = _settings()
    config = FunctionalWorkflowConfiguration.from_dict(data)
    assert config.schema_version == "1.1"
    assert config.parameters == (("candidate", (("name", "synthetic"), ("seed", 42))),)
    assert config.to_dict() == data
    data["parameters"]["candidate"]["seed"] = 999
    values = config.parameter_values()
    values["candidate"]["seed"] = 0  # type: ignore[index]
    exported: Any = config.to_dict()
    exported["parameters"]["candidate"]["name"] = "changed"
    assert config.parameter_values() == {"candidate": {"name": "synthetic", "seed": 42}}
    with pytest.raises(FrozenInstanceError):
        config.parameters = ()  # type: ignore[misc]
    location = tmp_path / "workflow.json"
    location.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    assert load_functional_workflow_configuration(location) == config


@pytest.mark.parametrize("value", [{}, {"a.b": None, "": True, "é": "false", "scale": -1.5}])
def test_empty_and_scalar_valued_mappings_preserve_json_values(value: dict[str, Any]) -> None:
    config = FunctionalWorkflowConfiguration.from_dict(_settings(parameters={"candidate": value}))
    assert config.parameter_values() == {"candidate": value}
    assert config == replace(config, parameters=(("candidate", tuple(value.items())),))


@pytest.mark.parametrize(
    "value", [[], [1], {"nested": {}}, {"array": []}, {1: 2}, {"x": float("nan")}, {"x": object()}]
)
def test_json_mappings_reject_non_scalar_contents(value: Any) -> None:
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(_settings(parameters={"candidate": value}))


@pytest.mark.parametrize("value", [(), (("seed", 42),), object(), float("inf")])
def test_dict_decoder_rejects_non_json_parameter_values(value: Any) -> None:
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(_settings(parameters={"candidate": value}))


@pytest.mark.parametrize(
    "value",
    [{}, [], ("x",), (("x",),), (("x", 1, 2),), ((1, 2),), (("x", []),), (("x", 1), ("x", 2))],
)
def test_direct_construction_requires_valid_immutable_mapping_pairs(value: Any) -> None:
    config = FunctionalWorkflowConfiguration.from_dict(_settings())
    with pytest.raises(FunctionalWorkflowError):
        replace(config, parameters=(("candidate", value),))


@pytest.mark.parametrize("version", ["1.0", None, [], {}, 1.1])
def test_mappings_need_the_explicit_1_1_schema(version: Any) -> None:
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(_settings(schema_version=version))


def test_duplicate_json_mapping_keys_are_rejected(tmp_path: Path) -> None:
    source = json.dumps(_settings()).replace('"seed": 42', '"seed": 42, "seed": 0')
    location = tmp_path / "workflow.json"
    location.write_text(source, encoding="utf-8")
    with pytest.raises(FunctionalWorkflowError, match="Duplicate"):
        load_functional_workflow_configuration(location)


@pytest.mark.parametrize(
    "body",
    [
        "    total = g(candidate, candidate)\n    return total",
        "    a = f(candidate)\n    total = g(a, candidate)\n    return total",
    ],
)
def test_mapping_parameters_cannot_be_reused_or_aliased_across_calls(body: str) -> None:
    config = FunctionalWorkflowConfiguration.from_dict(_settings())
    with pytest.raises(FunctionalWorkflowError, match="at most once"):
        plan_functional_workflow(_analysis(body), config)


def test_scalar_reuse_and_single_mapping_consumption_are_distinct() -> None:
    body = "    total = g(candidate, candidate)\n    return total"
    scalar = FunctionalWorkflowConfiguration.from_dict(_settings(parameters={"candidate": 42}))
    assert plan_functional_workflow(_analysis(body), scalar).steps[0].inputs == (
        ("x", "candidate"),
        ("y", "candidate"),
    )
    mapping = FunctionalWorkflowConfiguration.from_dict(_settings())
    body = "    a = g(x, candidate)\n    total = f(a)\n    return total"
    assert len(plan_functional_workflow(_analysis(body), mapping).steps) == 2


def test_paired_candidate_sources_and_schema_1_1_generation(tmp_path: Path) -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    script = plan_functional_workflow_path(EXAMPLE / "workflow.py", config, project_root=ROOT)
    notebook = plan_functional_workflow_path(EXAMPLE / "workflow.ipynb", config, project_root=ROOT)
    assert script.analysis.structure_sha256 == notebook.analysis.structure_sha256
    destination = tmp_path / "project"
    generate_functional_kedro_project(
        EXAMPLE / "workflow.py", config, destination, project_root=ROOT
    )
    parameters = json.loads((destination / "conf/base/parameters.yml").read_text())
    assert parameters == config.parameter_values()
    assert isinstance(parameters["candidate"], dict)
    generated = destination / "src/generated_workflow/workflow_source.py"
    assert ast.dump(ast.parse(generated.read_text())) == ast.dump(
        ast.parse((EXAMPLE / "workflow.py").read_text())
    )
    snapshot = json.loads((destination / "functional-workflow.json").read_text())
    assert snapshot["configuration"] == config.to_dict()


def test_candidate_mapping_does_not_approve_independent_loaders_or_fan_in(tmp_path: Path) -> None:
    source = tmp_path / "workflow.py"
    source.write_text(
        "def load_observations(path):\n    return path\n"
        "def load_specification(path):\n    return path\n"
        "def evaluate_candidate(data, specification, candidate):\n    return candidate\n"
        "def workflow(data_path, specification_path, candidate):\n"
        "    data = load_observations(data_path)\n"
        "    specification = load_specification(specification_path)\n"
        "    total = evaluate_candidate(data, specification, candidate)\n"
        "    return total\n",
        encoding="utf-8",
    )
    config = FunctionalWorkflowConfiguration.from_dict(
        _settings(
            inputs={},
            parameters={
                "data_path": "snapshot.parquet",
                "specification_path": "spec.json",
                "candidate": {"name": "baseline", "phase": "validation"},
            },
        )
    )
    with pytest.raises(FunctionalWorkflowError, match="preceding result"):
        generate_functional_kedro_project(
            source, config, tmp_path / "project", project_root=tmp_path
        )
    assert not (tmp_path / "project").exists()
