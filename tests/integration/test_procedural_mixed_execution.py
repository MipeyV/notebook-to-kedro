"""Trusted procedural reference versus actual generated Kedro catalog/pipeline behavior."""

from __future__ import annotations

import ast
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner, ThreadRunner

from notebook_to_kedro import (
    KedroArchitectureProfile,
    analyze_notebook_path,
    audit_conversion_source,
    generate_kedro_project,
    plan_notebook_path,
)

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/procedural_notebook"


def _cell_source(cell: dict[str, Any]) -> str:
    value = cell["source"]
    return "".join(value) if isinstance(value, list) else str(value)


def _prepare(root: Path, *, separate_imports: bool = False, stale: bool = False) -> Path:
    workspace = root / "workspace"
    shutil.copytree(EXAMPLE, workspace)
    source = workspace / "workflow.ipynb"
    notebook = json.loads(source.read_text(encoding="utf-8"))
    if separate_imports:
        imports, business = _cell_source(notebook["cells"][1]).split("\n\n", 1)
        notebook["cells"][1]["source"] = imports
        notebook["cells"].insert(
            2,
            {
                "cell_type": "code",
                "source": business,
                "id": "separate-loader",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
            },
        )
    if stale:
        for i, cell in enumerate(c for c in notebook["cells"] if c["cell_type"] == "code"):
            cell["execution_count"] = 99 - i
        notebook["cells"][-1]["outputs"] = [
            {
                "output_type": "execute_result",
                "data": {"text/plain": "999.0"},
                "metadata": {},
                "execution_count": 96,
            }
        ]
    source.write_text(json.dumps(notebook), encoding="utf-8")
    return workspace


def _reference(source: Path) -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    for cell in json.loads(source.read_text(encoding="utf-8"))["cells"]:
        if cell["cell_type"] == "code":
            exec(compile(_cell_source(cell), "trusted_synthetic_reference", "exec"), namespace)
    return namespace


def _catalog(project: Path, pipeline: Any) -> DataCatalog:
    loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    for name in pipeline.datasets():
        if name not in catalog:
            catalog[name] = MemoryDataset()
    for name, value in loader["parameters"].items():
        catalog[f"params:{name}"] = MemoryDataset(value)
    return catalog


@pytest.mark.integration
@pytest.mark.parametrize("custom_profile", [False, True])
@pytest.mark.parametrize("threaded", [False, True])
@pytest.mark.parametrize("separate_imports", [False, True])
def test_procedural_notebook_matches_reference_with_real_catalog_and_parameters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    custom_profile: bool,
    threaded: bool,
    separate_imports: bool,
) -> None:
    workspace = _prepare(tmp_path, separate_imports=separate_imports, stale=True)
    source = workspace / "workflow.ipynb"
    monkeypatch.chdir(workspace)
    expected = _reference(source)
    assert len(expected["df"]) == 36
    assert len(expected["predictions"]) == 9
    assert 0.0 <= expected["accuracy"] <= 1.0
    facts = analyze_notebook_path(source, project_root=workspace)
    plan = plan_notebook_path(source, project_root=workspace)
    assert audit_conversion_source(facts, plan).complete
    profile = (
        KedroArchitectureProfile("procedural.test", "1.0.0", "training", "ml_")
        if custom_profile
        else None
    )
    package = f"procedural_{int(custom_profile)}_{int(threaded)}_{int(separate_imports)}"
    project = workspace / "project"
    generate_kedro_project(
        plan, project, package_name=package, architecture_profile=profile, source_facts=facts
    )
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    registry = importlib.import_module(f"{package}.pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    assert [len(group) for group in pipeline.grouped_nodes] == [1, 1, 1, 1]
    catalog = _catalog(project, pipeline)
    pandas = importlib.import_module("pandas")
    original_reader = pandas.read_csv
    reads: list[str] = []

    def read_csv(*args: Any, **kwargs: Any) -> Any:
        reads.append(str(args[0]))
        return original_reader(*args, **kwargs)

    monkeypatch.setattr(pandas, "read_csv", read_csv)
    runner = ThreadRunner(max_workers=3) if threaded else SequentialRunner()
    runner.run(pipeline, catalog)
    assert len(reads) == 1
    assert reads[0].endswith("training.csv")
    assert catalog.load("accuracy") == expected["accuracy"]
    np.testing.assert_array_equal(catalog.load("predictions"), expected["predictions"])
    assert (project / "data/01_raw/training.csv").read_bytes() == (
        workspace / "data/training.csv"
    ).read_bytes()
    nodes_path = next((project / "src" / package / "pipelines").glob("*/nodes.py"))
    generated_tree = ast.parse(nodes_path.read_text())
    assert len([n for n in generated_tree.body if isinstance(n, ast.FunctionDef)]) == 4
    assert "pd.read_csv" not in nodes_path.read_text()
    first = pipeline.nodes[0]
    assert "df" in first.inputs
    assert "df__procedural_ml_notebook" in first.outputs


@pytest.mark.integration
@pytest.mark.parametrize("threaded", [False, True])
def test_original_preparation_assertion_stops_later_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    threaded: bool,
) -> None:
    workspace = _prepare(tmp_path)
    (workspace / "data/training.csv").write_text(
        "feature_a,feature_b,target\n,,\n", encoding="utf-8"
    )
    monkeypatch.chdir(workspace)
    source = workspace / "workflow.ipynb"
    with pytest.raises(AssertionError):
        _reference(source)
    plan = plan_notebook_path(source, project_root=workspace)
    package = f"procedural_error_{int(threaded)}"
    project = workspace / "project"
    generate_kedro_project(plan, project, package_name=package)
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline = importlib.import_module(f"{package}.pipeline_registry").register_pipelines()[
        "__default__"
    ]
    catalog = _catalog(project, pipeline)
    runner = ThreadRunner(max_workers=3) if threaded else SequentialRunner()
    with pytest.raises(AssertionError):
        runner.run(pipeline, catalog)
    assert not catalog.exists("accuracy")


@pytest.mark.integration
def test_actual_kedro_cli_runs_the_generated_procedural_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _prepare(tmp_path)
    monkeypatch.chdir(workspace)
    plan = plan_notebook_path(workspace / "workflow.ipynb", project_root=workspace)
    project = workspace / "project"
    generate_kedro_project(plan, project, package_name="procedural_cli")
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-m", "kedro", "run"],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "successfully" in result.stdout


@pytest.mark.integration
def test_business_mutation_disagrees_with_the_independent_notebook_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _prepare(tmp_path)
    monkeypatch.chdir(workspace)
    source = workspace / "workflow.ipynb"
    expected = _reference(source)
    plan = plan_notebook_path(source, project_root=workspace)
    package = "procedural_mutation"
    project = workspace / "project"
    generate_kedro_project(plan, project, package_name=package)
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    nodes = importlib.import_module(f"{package}.pipelines.notebook_pipeline.nodes")
    assert nodes.__file__ is not None
    nodes_path = Path(nodes.__file__)
    original = nodes_path.read_text()
    changed = original.replace("accuracy = accuracy_score(", "accuracy = 1.0 - accuracy_score(")
    assert changed != original
    # Execute only this deliberately changed synthetic module; avoid any stale bytecode cache.
    exec(compile(changed, "trusted_synthetic_mutation", "exec"), nodes.__dict__)
    pipeline = importlib.import_module(f"{package}.pipeline_registry").register_pipelines()[
        "__default__"
    ]
    catalog = _catalog(project, pipeline)
    SequentialRunner().run(pipeline, catalog)
    assert catalog.load("accuracy") != expected["accuracy"]
    assert nodes_path.read_text() == original


@pytest.mark.integration
@pytest.mark.parametrize("threaded", [False, True])
def test_csv_read_is_not_optimized_away_when_the_business_code_ignores_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    threaded: bool,
) -> None:
    workspace = _prepare(tmp_path)
    source = workspace / "workflow.ipynb"
    notebook = json.loads(source.read_text(encoding="utf-8"))
    notebook["cells"] = [
        {
            "cell_type": "code",
            "id": "ignored-input",
            "metadata": {},
            "execution_count": None,
            "outputs": [],
            "source": 'import pandas as pd\ndf = pd.read_csv("data/training.csv")\nanswer = 1',
        }
    ]
    source.write_text(json.dumps(notebook), encoding="utf-8")
    monkeypatch.chdir(workspace)
    assert _reference(source)["answer"] == 1
    plan = plan_notebook_path(source, project_root=workspace)
    project = workspace / "project"
    package = f"procedural_ignored_{int(threaded)}"
    generate_kedro_project(plan, project, package_name=package)
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    registry = importlib.import_module(f"{package}.pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    catalog = _catalog(project, pipeline)
    pandas = importlib.import_module("pandas")
    original_reader = pandas.read_csv
    reads: list[str] = []

    def read_csv(*args: Any, **kwargs: Any) -> Any:
        reads.append(str(args[0]))
        return original_reader(*args, **kwargs)

    monkeypatch.setattr(pandas, "read_csv", read_csv)
    runner = ThreadRunner(max_workers=3) if threaded else SequentialRunner()
    runner.run(pipeline, catalog)
    assert len(reads) == 1
    assert catalog.load("answer") == 1
