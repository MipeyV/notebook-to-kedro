"""Real Kedro proves ordered independent calls, identity and exception boundaries."""

from __future__ import annotations

import importlib
import json
import pickle
import runpy
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.pipeline import Pipeline, node
from kedro.runner import SequentialRunner, ThreadRunner

from notebook_to_kedro import (
    KedroArchitectureProfile,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
)

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_join"


def _generated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    package: str,
    suffix: str = ".py",
    profile: KedroArchitectureProfile | None = None,
) -> tuple[Any, Pipeline, DataCatalog, Path]:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    destination = tmp_path / "project"
    generate_functional_kedro_project(
        EXAMPLE / f"workflow{suffix}",
        config,
        destination,
        project_root=ROOT,
        package_name=package,
        architecture_profile=profile,
    )
    monkeypatch.syspath_prepend(str(destination / "src"))
    monkeypatch.chdir(destination)
    pipeline_name = "notebook_pipeline" if profile is None else profile.pipeline_name
    source = importlib.import_module(f"{package}.pipelines.{pipeline_name}.nodes")
    registry = importlib.import_module(f"{package}.pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    loader = OmegaConfigLoader(conf_source=str(destination / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    catalog["params:candidate"] = MemoryDataset(loader["parameters"]["candidate"])
    return source, pipeline, catalog, destination


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("custom_profile", [False, True])
@pytest.mark.parametrize("threaded", [False, True])
@pytest.mark.parametrize("scenario_id", ["positive", "override"])
def test_ordered_join_matches_source_and_expectations_with_original_arguments(  # noqa: PLR0913
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    scenario_id: str,
    *,
    custom_profile: bool,
    threaded: bool,
) -> None:
    profile = (
        KedroArchitectureProfile("test.ordered", "1.0.0", "validation", "ml_")
        if custom_profile
        else None
    )
    package = f"ordered_{suffix[1:]}_{int(custom_profile)}_{int(threaded)}_{scenario_id}"
    source, pipeline, catalog, destination = _generated(
        tmp_path, monkeypatch, package, suffix, profile
    )
    contract = load_workflow_regression_contract(EXAMPLE / "regression.json").to_dict()
    case = next(value for value in contract["scenarios"] if value["id"] == scenario_id)
    expected = runpy.run_path(str(EXAMPLE / "workflow.py"))["workflow"](
        **case["inputs"], **case["parameters"]
    )
    assert expected == case["expected"]
    for name, value in case["inputs"].items():
        (destination / f"data/01_raw/{name}.json").write_text(json.dumps(value), encoding="utf-8")
    catalog["params:candidate"] = MemoryDataset(case["parameters"]["candidate"])
    original_first, original_second, original_evaluate = (
        source.load_values,
        source.load_specification,
        source.evaluate,
    )
    events: list[str] = []
    objects: list[Any] = []

    def first(raw_values: list[Any]) -> Any:
        events.append("first")
        result = original_first(raw_values)
        objects.append(result)
        return result

    def second(raw_specification: dict[str, Any]) -> Any:
        assert events == ["first"]
        events.append("second")
        result = original_second(raw_specification)
        objects.append(result)
        return result

    def evaluate(observations: Any, specification: Any, candidate: Any) -> Any:
        assert events == ["first", "second"]
        events.append("evaluate")
        assert observations is objects[0]
        assert specification is objects[1]
        return original_evaluate(observations, specification, candidate)

    monkeypatch.setattr(source, "load_values", first)
    monkeypatch.setattr(source, "load_specification", second)
    monkeypatch.setattr(source, "evaluate", evaluate)
    assert [len(group) for group in pipeline.grouped_nodes] == [1, 1, 1]
    runner = ThreadRunner(max_workers=3) if threaded else SequentialRunner()
    runner.run(pipeline, catalog)
    assert events == ["first", "second", "evaluate"]
    actual = json.loads((destination / "data/08_reporting/total.json").read_text())
    assert json.dumps(actual, sort_keys=True) == json.dumps(case["expected"], sort_keys=True)
    assert "_ntk_after" not in actual


@pytest.mark.integration
@pytest.mark.parametrize("failure", ["first", "second"])
@pytest.mark.parametrize("threaded", [False, True])
def test_ordered_join_stops_after_the_same_failing_call_without_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str, *, threaded: bool
) -> None:
    source, pipeline, catalog, destination = _generated(
        tmp_path, monkeypatch, f"ordered_failure_{failure}_{int(threaded)}"
    )
    events: list[str] = []

    def first(raw_values: list[Any]) -> Any:
        events.append("first")
        if failure == "first":
            raise RuntimeError("trusted loader failure")
        return raw_values

    def second(_raw_specification: dict[str, Any]) -> Any:
        events.append("second")
        raise RuntimeError("trusted loader failure")

    def evaluate(*_args: Any, **_kwargs: Any) -> Any:
        events.append("unexpected")
        raise AssertionError("The join must not execute after a loader failure")

    monkeypatch.setattr(source, "load_values", first)
    monkeypatch.setattr(source, "load_specification", second)
    monkeypatch.setattr(source, "evaluate", evaluate)
    runner = ThreadRunner(max_workers=3) if threaded else SequentialRunner()
    with pytest.raises(RuntimeError, match="trusted loader failure"):
        runner.run(pipeline, catalog)
    assert events == (["first"] if failure == "first" else ["first", "second"])
    assert not (destination / "data/08_reporting/total.json").exists()


@pytest.mark.integration
def test_removing_order_dependency_allows_the_forbidden_concurrent_loader_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, pipeline, catalog, _ = _generated(tmp_path, monkeypatch, "ordered_negative")
    nodes = importlib.import_module("ordered_negative.pipelines.notebook_pipeline.nodes")
    original = pipeline.nodes
    unordered = Pipeline(
        [
            original[0],
            node(
                nodes.step_0001_load_specification,
                inputs="raw_specification",
                outputs="specification",
                name=original[1].name,
            ),
            original[2],
        ]
    )
    started, finish, completed = Event(), Event(), Event()
    observed: list[bool] = []

    def first(raw_values: list[Any]) -> Any:
        started.set()
        assert finish.wait(5), "The negative-control second loader did not start"
        completed.set()
        return raw_values

    def second(_raw_specification: dict[str, Any]) -> Any:
        assert started.wait(5), "The negative-control first loader did not start"
        observed.append(completed.is_set())
        finish.set()
        raise RuntimeError("second loader started before first returned")

    monkeypatch.setattr(source, "load_values", first)
    monkeypatch.setattr(source, "load_specification", second)
    with pytest.raises(RuntimeError, match="second loader started before first returned"):
        ThreadRunner(max_workers=2).run(unordered, catalog)
    assert observed == [False]


@pytest.mark.integration
def test_generated_ordering_callable_survives_pickle_and_keeps_the_business_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, pipeline, _, _ = _generated(tmp_path, monkeypatch, "ordered_pickle")
    ordered = pipeline.nodes[1]
    restored = pickle.loads(pickle.dumps(ordered.func))
    specification = {"scale": 2.0, "offset": 1.0}
    assert restored(_ntk_after=object(), raw_specification=specification) is specification
    nodes = importlib.import_module("ordered_pickle.pipelines.notebook_pipeline.nodes")
    assert nodes.step_0001_load_specification(raw_specification=specification) is specification
