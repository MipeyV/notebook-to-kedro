"""Trusted synthetic business cases: source/Kedro parity and independent metric checks."""

from __future__ import annotations

import importlib
import json
import math
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
    load_notebook_regression_contract,
    plan_notebook_path,
)

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "examples/banking_insurance"
CASES = ("credit_default", "insurance_lapse")
pytestmark = pytest.mark.integration


def _workspace(tmp_path: Path, case: str) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(EXAMPLES / case, workspace)
    return workspace


def _reference(workspace: Path) -> dict[str, Any]:
    notebook = json.loads((workspace / "workflow.ipynb").read_text(encoding="utf-8"))
    namespace: dict[str, Any] = {}
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            source = cell["source"]
            exec(compile("".join(source), "trusted_synthetic_financial_case", "exec"), namespace)
    return namespace


def _independent_metrics(
    truth: list[int], scores: list[float], predictions: list[int], threshold: float, cost: int
) -> dict[str, Any]:
    """Compute the declared binary metrics directly, without sklearn metric functions."""
    positives = sum(truth)
    negatives = len(truth) - positives
    auc = math.fsum(
        float(positive > negative) + 0.5 * float(positive == negative)
        for positive, target in zip(scores, truth, strict=True)
        if target
        for negative, other in zip(scores, truth, strict=True)
        if not other
    ) / (positives * negatives)
    average_precision, previous_tp = 0.0, 0
    for cut in sorted(set(scores), reverse=True):
        selected = [target for score, target in zip(scores, truth, strict=True) if score >= cut]
        tp = sum(selected)
        average_precision += (tp - previous_tp) / positives * tp / len(selected)
        previous_tp = tp
    tp = sum(
        target == 1 and predicted == 1 for target, predicted in zip(truth, predictions, strict=True)
    )
    fp = sum(
        target == 0 and predicted == 1 for target, predicted in zip(truth, predictions, strict=True)
    )
    fn = positives - tp
    tn = negatives - fp
    return {
        "roc_auc": round(auc, 8),
        "average_precision": round(average_precision, 8),
        "brier": round(
            math.fsum((score - target) ** 2 for score, target in zip(scores, truth, strict=True))
            / len(truth),
            8,
        ),
        "precision": round(tp / (tp + fp), 8) if tp + fp else 0.0,
        "recall": round(tp / positives, 8),
        "alert_rate": round(sum(predictions) / len(truth), 8),
        "positive_rate": round(positives / len(truth), 8),
        "threshold": threshold,
        "true_negatives": tn,
        "false_positives": fp,
        "false_negatives": fn,
        "true_positives": tp,
        "cost_units": fn * cost + fp,
    }


def _independent_threshold(truth: list[int], scores: list[float], cost: int) -> float:
    grid = [0.15, 0.25, 0.35, 0.5, 0.65]
    costs = [
        sum(
            cost if target and score < threshold else 1 if not target and score >= threshold else 0
            for target, score in zip(truth, scores, strict=True)
        )
        for threshold in grid
    ]
    return grid[costs.index(min(costs))]


def _project(workspace: Path, package: str, *, custom: bool) -> Path:
    source = workspace / "workflow.ipynb"
    facts = analyze_notebook_path(source, project_root=workspace)
    plan = plan_notebook_path(source, project_root=workspace)
    assert audit_conversion_source(facts, plan).complete
    assert len(plan.task_candidates) == 10
    assert len(plan.parameters) == 2
    project = workspace / "project"
    profile = (
        KedroArchitectureProfile("financial.example", "1.0.0", "training", "ml_")
        if custom
        else None
    )
    generate_kedro_project(
        plan,
        project,
        package_name=package,
        architecture_profile=profile,
        source_facts=facts,
        regression_contract=load_notebook_regression_contract(workspace / "regression.json"),
    )
    return project


def _run_project(project: Path, package: str, *, threaded: bool) -> tuple[Any, DataCatalog]:
    registry = importlib.import_module(f"{package}.pipeline_registry")
    pipeline = registry.register_pipelines()["__default__"]
    loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    for name in pipeline.datasets():
        if name not in catalog:
            catalog[name] = MemoryDataset()
    for name, value in loader["parameters"].items():
        catalog[f"params:{name}"] = MemoryDataset(value)
    runner = ThreadRunner(max_workers=2) if threaded else SequentialRunner()
    runner.run(pipeline, catalog)
    return pipeline, catalog


def _equal(actual: Any, expected: Any) -> None:
    pandas = importlib.import_module("pandas")
    if isinstance(expected, np.ndarray):
        np.testing.assert_array_equal(actual, expected)
    elif isinstance(expected, pandas.Series):
        pandas.testing.assert_series_equal(actual, expected)
    elif isinstance(expected, pandas.DataFrame):
        pandas.testing.assert_frame_equal(actual, expected)
    else:
        assert actual == expected


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("threaded", [False, True])
def test_source_and_kedro_match_with_independent_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, *, custom: bool, threaded: bool
) -> None:
    workspace = _workspace(tmp_path, case)
    monkeypatch.chdir(workspace)
    reference = _reference(workspace)
    metadata = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    assert reference["cohort_counts"] == metadata["counts"]
    assert reference["feature_names"] == metadata["expected_encoded_features"]
    independent = _independent_metrics(
        reference["y_test"].tolist(),
        reference["test_scores"].tolist(),
        reference["test_predictions"].tolist(),
        reference["threshold"],
        metadata["miss_cost_units"],
    )
    assert reference["metrics"] == independent
    assert reference["threshold"] == _independent_threshold(
        reference["y_validation"].tolist(),
        reference["validation_scores"].tolist(),
        metadata["miss_cost_units"],
    )
    package = f"financial_{case}_{int(custom)}_{int(threaded)}"
    project = _project(workspace, package, custom=custom)
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline, catalog = _run_project(project, package, threaded=threaded)
    assert len(pipeline.nodes) == 10
    for name in pipeline.outputs():
        _equal(catalog.load(name), reference[name])
    assert catalog.load("summary")["metrics"] == independent
    assert (project / "data/01_raw/portfolio.csv").read_bytes() == (
        workspace / "data/portfolio.csv"
    ).read_bytes()


@pytest.mark.parametrize("case", CASES)
def test_holdout_labels_and_values_do_not_fit_preprocessing_or_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    workspace = _workspace(tmp_path, case)
    monkeypatch.chdir(workspace)
    reference = _reference(workspace)
    pandas = importlib.import_module("pandas")
    path = workspace / "data/portfolio.csv"
    raw = pandas.read_csv(path)
    target = "default_12m" if case == "credit_default" else "lapse_12m"
    test = raw["snapshot_month"].between(202401, 202412)
    raw.loc[test, target] = 1 - raw.loc[test, target]
    raw.to_csv(path, index=False)
    flipped = _reference(workspace)
    _equal(flipped["numeric_medians"], reference["numeric_medians"])
    _equal(flipped["category_modes"], reference["category_modes"])
    _equal(flipped["test_scores"], reference["test_scores"])
    _equal(flipped["validation_scores"], reference["validation_scores"])
    assert flipped["threshold"] == reference["threshold"]
    assert flipped["metrics"] != reference["metrics"]
    column = reference["numeric_columns"][0]
    raw.loc[test, column] = 999999
    raw.to_csv(path, index=False)
    extreme = _reference(workspace)
    _equal(extreme["numeric_medians"], reference["numeric_medians"])
    _equal(extreme["X_train_encoded"], reference["X_train_encoded"])
    assert extreme["threshold"] == reference["threshold"]


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("custom", [False, True])
def test_delivered_tests_and_kedro_cli_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, *, custom: bool
) -> None:
    workspace = _workspace(tmp_path, case)
    monkeypatch.chdir(workspace)
    project = _project(workspace, "financial_delivered", custom=custom)
    for command, expected in (
        (
            [sys.executable, "-m", "pytest", "-q", "--basetemp=" + str(tmp_path / "delivered-tmp")],
            "10 passed",
        ),
        ([sys.executable, "-m", "kedro", "run"], "successfully in"),
    ):
        result = subprocess.run(
            command, cwd=project, capture_output=True, text=True, timeout=90, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert expected in result.stdout + result.stderr


@pytest.mark.parametrize("case", CASES)
def test_generated_calculation_mutation_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    workspace = _workspace(tmp_path, case)
    monkeypatch.chdir(workspace)
    reference = _reference(workspace)
    package = "financial_mutated_" + case
    project = _project(workspace, package, custom=False)
    path = next((project / f"src/{package}/pipelines").glob("*/nodes.py"))
    text = path.read_text(encoding="utf-8")
    assert "test_scores = model.predict_proba(X_test_encoded)[:, 1]" in text
    path.write_text(
        text.replace(
            "test_scores = model.predict_proba(X_test_encoded)[:, 1]",
            "test_scores = 1.0 - model.predict_proba(X_test_encoded)[:, 1]  # negative control",
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    _, catalog = _run_project(project, package, threaded=False)
    with pytest.raises(AssertionError):
        _equal(catalog.load("summary")["metrics"], reference["metrics"])
