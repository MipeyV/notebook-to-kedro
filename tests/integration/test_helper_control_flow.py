"""Paired preserved helper control flow, real runners, errors and shipped JSON tests."""

from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner, ThreadRunner

from notebook_to_kedro import (
    FunctionalWorkflowConfiguration,
    KedroArchitectureProfile,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
)
from notebook_to_kedro.generation.writer import write_project

ROOT = Path(__file__).parents[2]


def _prepare(root: Path, suffix: str) -> tuple[Path, dict[str, Any]]:
    corpus = json.loads(
        (ROOT / "examples/agent_comparison/challenges/corpus.json").read_text(encoding="utf-8")
    )
    case = next(c for c in corpus["cases"] if c["case_id"] == "messy-control-flow")
    files = {Path(name): text for name, text in case["files"].items() if name.startswith("input/")}
    spec = json.loads(files[Path("input/acceptance.json")])
    files[Path("input/workflow.py")] = spec["source_text"]
    write_project(root, files)
    return root / ("input/workflow" + suffix), spec


def _run(root: Path, name: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(root / "pyproject.toml"),
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(root.parent / name),
            "-q",
            "--tb=short",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("profile", [False, True])
@pytest.mark.parametrize("threaded", [False, True])
@pytest.mark.parametrize(
    "scenario_id", ["missing_and_outliers", "normal", "negative", "all_missing", "strict_missing"]
)
def test_registered_pipeline_matches_original_results_errors_order_and_identity(  # noqa: PLR0913, PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    scenario_id: str,
    *,
    profile: bool,
    threaded: bool,
) -> None:
    source_root = tmp_path / "source"
    source, spec = _prepare(source_root, suffix)
    contract = load_workflow_regression_contract(source_root / "input/regression.json")
    scenarios = contract.to_dict()["scenarios"] + spec["failure_scenarios"]
    case = next(c for c in scenarios if c["id"] == scenario_id)
    configuration = load_functional_workflow_configuration(
        source_root / "input/workflow.json"
    ).to_dict()
    configuration["parameters"] = case["parameters"]
    (source_root / "input/raw_values.json").write_text(
        json.dumps(case["inputs"]["raw_values"]), encoding="utf-8"
    )
    package = f"cf_{suffix[1:]}_{int(profile)}_{int(threaded)}_{scenario_id}"
    project = tmp_path / "project"
    generate_functional_kedro_project(
        source,
        FunctionalWorkflowConfiguration.from_dict(configuration),
        project,
        project_root=source_root,
        package_name=package,
        regression_contract=contract,
        architecture_profile=KedroArchitectureProfile("control.test", "1.0.0", "training", "ml_")
        if profile
        else None,
    )
    original_tree = ast.parse(spec["source_text"])
    actual_tree = ast.parse((project / f"src/{package}/workflow_source.py").read_text())
    assert ast.dump(original_tree) == ast.dump(actual_tree)
    reference: dict[str, Any] = {}
    # Trusted original function definitions only; no notebook/cell execution or recorded outputs.
    exec(compile(original_tree, "trusted_original_helpers", "exec"), reference)
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline_name = "training" if profile else "notebook_pipeline"
    nodes_module = importlib.import_module(f"{package}.pipelines.{pipeline_name}.nodes")
    events: list[str] = []
    arguments: list[tuple[Any, ...]] = []
    results: list[Any] = []

    def track(name: str) -> Any:
        original = getattr(nodes_module, name)

        def invoke(*args: Any, **kwargs: Any) -> Any:
            events.append(name)
            arguments.append(args)
            result = original(*args, **kwargs)
            results.append(result)
            return result

        return invoke

    for helper in spec["helper_asts"]:
        monkeypatch.setattr(nodes_module, helper, track(helper))
    registry = importlib.import_module(package + ".pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    assert [len(group) for group in pipeline.grouped_nodes] == [1, 1, 1]
    loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    for name, value in case["parameters"].items():
        catalog["params:" + name] = MemoryDataset(value)
    runner = ThreadRunner(max_workers=3) if threaded else SequentialRunner()
    if "error" in case:
        with pytest.raises(ValueError, match=case["error"]) as expected:
            reference["workflow"](**case["inputs"], **case["parameters"])
        with pytest.raises(type(expected.value), match=case["error"]) as actual:
            runner.run(pipeline, catalog)
        assert actual.value.args == expected.value.args
        assert not (project / "data/08_reporting/report.json").exists()
        assert events == (
            ["clean_values"] if scenario_id == "strict_missing" else spec["helper_asts"]
        )
    else:
        assert reference["workflow"](**case["inputs"], **case["parameters"]) == case["expected"]
        runner.run(pipeline, catalog)
        assert catalog.load("report") == case["expected"]
        assert events == spec["helper_asts"]
        assert arguments[1][0] is results[0]
        assert arguments[2][0] is results[1]


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
def test_delivered_json_suite_keeps_all_oracles_and_detects_changed_loop_logic(
    tmp_path: Path, suffix: str
) -> None:
    source_root = tmp_path / "source"
    source, _ = _prepare(source_root, suffix)
    project = tmp_path / "project"
    generate_functional_kedro_project(
        source,
        load_functional_workflow_configuration(source_root / "input/workflow.json"),
        project,
        project_root=source_root,
        regression_contract=load_workflow_regression_contract(
            source_root / "input/regression.json"
        ),
    )
    result = _run(project, "positive-suite")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "12 passed" in result.stdout
    original = project / "src/generated_workflow/workflow_source.py"
    text = original.read_text()
    changed = text.replace("sum(bounded) / len(bounded)", "sum(bounded)")
    assert changed != text
    original.write_text(changed + "\n# deliberate arithmetic control\n", encoding="utf-8")
    result = _run(project, "negative-suite")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "6 failed" in result.stdout


@pytest.mark.integration
@pytest.mark.parametrize("threaded", [False, True])
@pytest.mark.parametrize(
    ("values", "expected"),
    [([1.0, 2.0, 3.0], 7.0), ([-1.0, 2.0], 3.0), ([1.0, 9.0, 2.0], 1.0), ([], 1.0)],
)
def test_while_break_continue_and_else_are_not_rewritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    values: list[float],
    expected: float,
    *,
    threaded: bool,
) -> None:
    source = tmp_path / "workflow.py"
    source.write_text(
        "def accumulate(values, stop):\n    total = 0.0\n    index = 0\n"
        "    while index < len(values):\n        value = values[index]\n        index += 1\n"
        "        if value < 0:\n            continue\n        if value > stop:\n            break\n"
        "        total += value\n    else:\n        total += 1.0\n    return total\n\n"
        "def workflow(values, stop):\n    report = accumulate(values, stop)\n    return report\n",
        encoding="utf-8",
    )
    (tmp_path / "input.json").write_text(json.dumps(values), encoding="utf-8")
    config = FunctionalWorkflowConfiguration.from_dict(
        {
            "schema_version": "1.0",
            "entrypoint": "workflow",
            "inputs": {"values": "input.json"},
            "parameters": {"stop": 5.0},
            "outputs": {"report": "data/08_reporting/report.json"},
        }
    )
    package = "while_case_" + str(int(threaded)) + "_" + str(expected).replace(".", "_")
    project = tmp_path / "project"
    generate_functional_kedro_project(
        source, config, project, project_root=tmp_path, package_name=package
    )
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline = importlib.import_module(package + ".pipeline_registry").register_pipelines()[
        "__default__"
    ]
    loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    catalog["params:stop"] = MemoryDataset(5.0)
    runner = ThreadRunner(max_workers=2) if threaded else SequentialRunner()
    runner.run(pipeline, catalog)
    assert catalog.load("report") == expected
