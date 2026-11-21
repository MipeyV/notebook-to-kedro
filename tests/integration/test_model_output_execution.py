"""Trusted synthetic models survive versioned catalog storage and a fresh-process reload."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from contextlib import chdir
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, DatasetError, MemoryDataset
from kedro.runner import SequentialRunner, ThreadRunner

from notebook_to_kedro import (
    KedroArchitectureProfile,
    NotebookRegressionContract,
    analyze_notebook_path,
    generate_kedro_project,
    load_notebook_regression_contract,
    plan_notebook_path,
)

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).parents[2]
CASES = ("credit_pipeline", "lapse_calibrated_vote")
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def checks() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stored_model_checks", Path(__file__).with_name("test_nested_financial_models.py")
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare(tmp_path: Path, case: str, package: str, *, custom: bool) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    shutil.copytree(ROOT / "examples/nested_financial" / case, workspace)
    source = workspace / "workflow.ipynb"
    profile = (
        KedroArchitectureProfile("storage.example", "1.0.0", "training", "ml_") if custom else None
    )
    project = workspace / "project"
    with chdir(workspace):
        generate_kedro_project(
            plan_notebook_path(source),
            project,
            package_name=package,
            source_facts=analyze_notebook_path(source),
            architecture_profile=profile,
            regression_contract=load_notebook_regression_contract(workspace / "regression.json"),
            model_output="fitted_model",
        )
    assert not (project / "data/06_models").exists()
    return workspace, project


def _catalog(project: Path, *, version: str) -> DataCatalog:
    loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
    return DataCatalog.from_config(
        loader["catalog"], save_version=version, load_versions={"fitted_model": version}
    )


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("variant", [(False, False), (False, True), (True, False), (True, True)])
def test_stored_models_preserve_source_predictions_and_fitted_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checks: ModuleType,
    case: str,
    variant: tuple[bool, bool],
) -> None:
    custom, threaded = variant
    package = f"stored_{case}_{int(custom)}_{int(threaded)}"
    workspace, project = _prepare(tmp_path, case, package, custom=custom)
    monkeypatch.chdir(workspace)
    reference = checks._reference(workspace)
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline = importlib.import_module(package + ".pipeline_registry").register_pipelines()[
        "__default__"
    ]
    catalog = _catalog(project, version="first")
    loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
    for name in pipeline.datasets():
        if name not in catalog:
            catalog[name] = MemoryDataset()
    for name, value in loader["parameters"].items():
        catalog["params:" + name] = MemoryDataset(value)
    runner = ThreadRunner(max_workers=2) if threaded else SequentialRunner()
    runner.run(pipeline, catalog)
    path = project / "data/06_models/model.pkl/first/model.pkl"
    assert path.is_file()
    original_bytes = path.read_bytes()
    # A new catalog must reload from disk, with no in-memory estimator handed to it.
    loaded = _catalog(project, version="first").load("fitted_model")
    checks._fitted_model(loaded, reference["fitted_model"], reference, case)
    equal = checks._baseline_helpers()._equal
    for name in pipeline.outputs() - {"fitted_model"}:
        equal(catalog.load(name), reference[name])
    with pytest.raises(DatasetError, match="must not exist"):
        _catalog(project, version="first").save("fitted_model", loaded)
    assert path.read_bytes() == original_bytes


_RELOAD = """
import json, sys
import numpy as np
import pandas as pd
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog
with open(sys.argv[1], encoding="utf-8") as stream:
    expected = json.load(stream)
frame = pd.read_csv("data/01_raw/portfolio.csv")
features = frame.loc[frame.snapshot_month.between(202401, 202412), expected["features"]]
settings = OmegaConfigLoader(conf_source="conf/base")["catalog"]
for version in expected["versions"]:
    catalog = DataCatalog.from_config(settings, load_versions={"fitted_model": version})
    model = catalog.load("fitted_model")
    np.testing.assert_allclose(
        model.predict_proba(features)[:, 1], expected["scores"], rtol=0, atol=1e-12)
print("Fresh-process reload predictions matched")
"""


@pytest.mark.parametrize("case", CASES)
def test_cli_versions_and_fresh_process_reload_preserve_earlier_artifacts(
    tmp_path: Path, checks: ModuleType, case: str
) -> None:
    workspace, project = _prepare(tmp_path, case, "model_cli", custom=False)
    with chdir(workspace):
        reference = checks._reference(workspace)
    root = project / "data/06_models/model.pkl"
    previous: dict[Path, bytes] = {}
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-m", "kedro", "run"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert all(path.read_bytes() == value for path, value in previous.items())
        current = {path: path.read_bytes() for path in root.glob("*/model.pkl")}
        assert len(current) == len(previous) + 1
        previous = current
    manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    expected = workspace / "reload.json"
    expected.write_text(
        json.dumps(
            {
                "features": manifest["feature_columns"],
                "scores": reference["test_scores"].tolist(),
                "versions": [path.parent.name for path in previous],
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-c", _RELOAD, str(expected)],
        cwd=project,
        env=dict(os.environ, PYTHONPATH=str(project / "src")),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Fresh-process reload predictions matched" in result.stdout


@pytest.mark.parametrize("case", CASES)
def test_delivered_regressions_stay_memory_only_and_reject_changed_storage(
    tmp_path: Path, case: str
) -> None:
    _, project = _prepare(tmp_path, case, "model_tests", custom=True)
    command = [sys.executable, "-m", "pytest", "-q", "--basetemp=" + str(tmp_path / "tests-temp")]
    result = subprocess.run(
        command, cwd=project, capture_output=True, text=True, timeout=90, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "10 passed" in result.stdout
    assert not (project / "data/06_models").exists()
    report = json.loads((project / "regression-coverage.json").read_text(encoding="utf-8"))
    assert "fitted_model" in report["missing_pipeline_outputs"]
    catalog = project / "conf/base/catalog.yml"
    catalog.write_text(
        catalog.read_text(encoding="utf-8").replace('"pickle"', '"json"'), encoding="utf-8"
    )
    result = subprocess.run(
        command, cwd=project, capture_output=True, text=True, timeout=90, check=False
    )
    assert result.returncode != 0
    assert "Regression model catalog declaration changed" in result.stdout
    assert not (project / "data/06_models").exists()


def test_model_only_catalog_is_validated_even_without_csv_inputs(tmp_path: Path) -> None:
    source = tmp_path / "model.ipynb"
    source.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"language_info": {"name": "python"}},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "model",
                        "metadata": {},
                        "source": "model = {'coef': 42}",
                        "execution_count": None,
                        "outputs": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    contract = NotebookRegressionContract.from_dict(
        {
            "schema_version": "1.0",
            "fixtures": {},
            "scenarios": [
                {
                    "id": "baseline",
                    "inputs": {},
                    "parameters": {},
                    "expected": {"model": {"kind": "json", "value": {"coef": 42}}},
                }
            ],
        }
    )
    project = tmp_path / "project"
    generate_kedro_project(
        plan_notebook_path(source),
        project,
        source_facts=analyze_notebook_path(source),
        regression_contract=contract,
        model_output="model",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--basetemp=" + str(tmp_path / "tests-temp")],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert not (project / "data/06_models").exists()
