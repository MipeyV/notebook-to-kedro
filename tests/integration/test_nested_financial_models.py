"""Nested sklearn objects retain fitted behavior; alias and CV failures stay explicit."""

from __future__ import annotations

import functools
import importlib
import importlib.util
import json
import shutil
import subprocess
import sys
from contextlib import chdir
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner, ThreadRunner
from sklearn.exceptions import NotFittedError  # type: ignore[import-untyped]

from notebook_to_kedro import (
    KedroArchitectureProfile,
    analyze_notebook_path,
    audit_conversion_source,
    generate_kedro_project,
    load_notebook_regression_contract,
    plan_notebook_path,
)

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "examples/nested_financial"
CASES = ("credit_pipeline", "lapse_calibrated_vote")
pytestmark = pytest.mark.integration


def _baseline_helpers() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "financial_baseline_checks", Path(__file__).with_name("test_financial_business_cases.py")
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reference(workspace: Path, filename: str = "workflow.ipynb") -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    for cell in json.loads((workspace / filename).read_text(encoding="utf-8"))["cells"]:
        if cell["cell_type"] == "code":
            exec(compile("".join(cell["source"]), "trusted_nested_financial", "exec"), namespace)
    return namespace


def _prepare(
    tmp_path: Path, case: str, package: str, *, custom: bool, filename: str = "workflow.ipynb"
) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    shutil.copytree(EXAMPLES / case, workspace)
    source = workspace / filename
    plan = plan_notebook_path(source, project_root=workspace)
    facts = analyze_notebook_path(source, project_root=workspace)
    assert audit_conversion_source(facts, plan).complete
    assert len(plan.task_candidates) == 9
    project = workspace / "project"
    profile = (
        KedroArchitectureProfile("nested.example", "1.0.0", "training", "ml_") if custom else None
    )
    # Source-copy paths are rooted by the caller's cwd, as for the public notebook API.
    with chdir(workspace):
        generate_kedro_project(
            plan,
            project,
            package_name=package,
            architecture_profile=profile,
            source_facts=facts,
            regression_contract=load_notebook_regression_contract(workspace / "regression.json"),
        )
    return workspace, project


def _pipeline(project: Path, package: str) -> tuple[Any, DataCatalog]:
    pipeline = importlib.import_module(package + ".pipeline_registry").register_pipelines()[
        "__default__"
    ]
    loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
    catalog = DataCatalog.from_config(loader["catalog"])
    for name in pipeline.datasets():
        if name not in catalog:
            catalog[name] = MemoryDataset()
    for name, value in loader["parameters"].items():
        catalog["params:" + name] = MemoryDataset(value)
    return pipeline, catalog


def _preprocessing(estimator: Any, namespace: dict[str, Any], indices: Any) -> None:
    training = namespace["X_train"].iloc[indices]
    numeric = namespace["numeric_columns"]
    categorical = namespace["categorical_columns"]
    preprocessor = estimator.named_steps["preprocessing"]
    fitted_numeric = preprocessor.named_transformers_["numeric"]
    fitted_categorical = preprocessor.named_transformers_["categorical"]
    medians = training[numeric].median()
    np.testing.assert_allclose(fitted_numeric.named_steps["imputer"].statistics_, medians)
    np.testing.assert_allclose(
        fitted_numeric.named_steps["scale"].mean_, training[numeric].fillna(medians).mean()
    )
    modes = training[categorical].mode().iloc[0]
    np.testing.assert_array_equal(fitted_categorical.named_steps["imputer"].statistics_, modes)
    assert fitted_categorical.named_steps["encode"].handle_unknown == "ignore"
    for index, column in enumerate(categorical):
        np.testing.assert_array_equal(
            fitted_categorical.named_steps["encode"].categories_[index],
            sorted(training[column].fillna(modes[column]).unique()),
        )


def _fitted_model(actual: Any, expected: Any, namespace: dict[str, Any], case: str) -> None:
    assert type(actual) is type(expected)
    for name in ("X_validation", "X_test"):
        np.testing.assert_allclose(
            actual.predict_proba(namespace[name]),
            expected.predict_proba(namespace[name]),
            rtol=0,
            atol=1e-12,
        )
    if case == "credit_pipeline":
        _preprocessing(actual, namespace, np.arange(len(namespace["X_train"])))
        assert actual.named_steps["classifier"].C == 1.0
        assert actual.named_steps["classifier"].max_iter == 300
        return
    assert actual.ensemble is True
    assert actual.method == "sigmoid"
    assert len(actual.calibrated_classifiers_) == 3
    splits = list(namespace["time_cv"].split(namespace["X_train"], namespace["y_train"]))
    for fitted, (training, calibration) in zip(actual.calibrated_classifiers_, splits, strict=True):
        assert (
            namespace["train"].iloc[training]["outcome_end_month"].max()
            < namespace["train"].iloc[calibration]["snapshot_month"].min()
        )
        assert (
            namespace["train"].iloc[calibration]["outcome_end_month"].max()
            < namespace["validation"]["snapshot_month"].min()
        )
        _preprocessing(fitted.estimator, namespace, training)
        assert fitted.estimator.named_steps["classifier"].voting == "soft"
        vote = fitted.estimator.named_steps["classifier"]
        assert vote.weights == [1, 1]
        assert vote.named_estimators_["forest"].n_estimators == 15
        transformed = fitted.estimator.named_steps["preprocessing"].transform(
            namespace["X_validation"]
        )
        probabilities = [member.predict_proba(transformed) for member in vote.estimators_]
        np.testing.assert_allclose(
            vote.predict_proba(transformed), np.mean(probabilities, axis=0), rtol=0, atol=1e-12
        )
    np.testing.assert_allclose(
        actual.predict_proba(namespace["X_validation"]),
        np.mean(
            [
                fitted.predict_proba(namespace["X_validation"])
                for fitted in actual.calibrated_classifiers_
            ],
            axis=0,
        ),
        rtol=0,
        atol=1e-12,
    )


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("threaded", [False, True])
def test_nested_estimators_match_source_and_preserve_fitted_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, *, custom: bool, threaded: bool
) -> None:
    package = f"nested_{case}_{int(custom)}_{int(threaded)}"
    workspace, project = _prepare(tmp_path, case, package, custom=custom)
    monkeypatch.chdir(workspace)
    namespace = _reference(workspace)
    helpers = _baseline_helpers()
    manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    assert namespace["feature_names"] == manifest["expected_encoded_features"]
    assert namespace["metrics"] == helpers._independent_metrics(
        namespace["y_test"].tolist(),
        namespace["test_scores"].tolist(),
        namespace["test_predictions"].tolist(),
        namespace["threshold"],
        manifest["miss_cost_units"],
    )
    assert namespace["threshold"] == helpers._independent_threshold(
        namespace["y_validation"].tolist(),
        namespace["validation_scores"].tolist(),
        manifest["miss_cost_units"],
    )
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline, catalog = _pipeline(project, package)
    runner = ThreadRunner(max_workers=2) if threaded else SequentialRunner()
    runner.run(pipeline, catalog)
    for name in pipeline.outputs():
        if name == "fitted_model":
            _fitted_model(catalog.load(name), namespace[name], namespace, case)
        else:
            helpers._equal(catalog.load(name), namespace[name])


@pytest.mark.parametrize("custom", [False, True])
def test_fitted_alias_is_a_runtime_boundary_not_static_completeness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, custom: bool
) -> None:
    package = f"nested_alias_{int(custom)}"
    workspace, project = _prepare(
        tmp_path, "credit_pipeline", package, custom=custom, filename="boundary_fitted_alias.ipynb"
    )
    monkeypatch.chdir(workspace)
    reference = _reference(workspace, "boundary_fitted_alias.ipynb")
    assert reference["preprocessor"] is reference["model"].named_steps["preprocessing"]
    assert reference["feature_names"]
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline, catalog = _pipeline(project, package)
    with pytest.raises(NotFittedError, match="ColumnTransformer"):
        SequentialRunner().run(pipeline, catalog)
    assert not catalog.exists("fitted_model")


@pytest.mark.parametrize("custom", [False, True])
def test_temporal_stacking_preserves_the_original_sklearn_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, custom: bool
) -> None:
    package = f"nested_stacking_{int(custom)}"
    workspace, project = _prepare(
        tmp_path,
        "lapse_calibrated_vote",
        package,
        custom=custom,
        filename="boundary_stacking_timeseries.ipynb",
    )
    monkeypatch.chdir(workspace)
    with pytest.raises(ValueError, match="cross_val_predict only works for partitions"):
        _reference(workspace, "boundary_stacking_timeseries.ipynb")
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline, catalog = _pipeline(project, package)
    target = next(
        node
        for node in pipeline.nodes
        if node.name == ("ml_train_model" if custom else "train_model")
    )
    original, observed = target.func, []

    @functools.wraps(original)
    def tracked(*args: Any, **kwargs: Any) -> Any:
        try:
            return original(*args, **kwargs)
        except ValueError as error:
            observed.append(error)
            raise

    monkeypatch.setattr(target, "func", tracked)
    with pytest.raises(ValueError, match="cross_val_predict only works for partitions") as caught:
        SequentialRunner().run(pipeline, catalog)
    assert observed[-1] is caught.value
    assert not catalog.exists("fitted_model")


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("custom", [False, True])
def test_nested_projects_deliver_ten_tests_and_run_the_cli(
    tmp_path: Path, case: str, *, custom: bool
) -> None:
    _, project = _prepare(tmp_path, case, "nested_delivered", custom=custom)
    for command, phrase in (
        (
            [sys.executable, "-m", "pytest", "-q", "--basetemp=" + str(tmp_path / "tests-tmp")],
            "10 passed",
        ),
        ([sys.executable, "-m", "kedro", "run"], "successfully in"),
    ):
        outcome = subprocess.run(
            command, cwd=project, capture_output=True, text=True, timeout=90, check=False
        )
        assert outcome.returncode == 0, outcome.stdout + outcome.stderr
        assert phrase in outcome.stdout + outcome.stderr


@pytest.mark.parametrize("case", CASES)
def test_changing_a_nested_component_breaks_prediction_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    package = "nested_mutation_" + case
    workspace, project = _prepare(tmp_path, case, package, custom=False)
    monkeypatch.chdir(workspace)
    source = _reference(workspace)
    path = next((project / f"src/{package}/pipelines").glob("*/nodes.py"))
    before = path.read_text(encoding="utf-8")
    original, replacement = (
        ("C=1.0", "C=0.01") if case == "credit_pipeline" else ("weights=[1, 1]", "weights=[1, 0]")
    )
    assert original in before
    path.write_text(
        before.replace(original, replacement) + "\n# nested mutation\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(project / "src"))
    monkeypatch.chdir(project)
    pipeline, catalog = _pipeline(project, package)
    SequentialRunner().run(pipeline, catalog)
    with pytest.raises(AssertionError):
        np.testing.assert_allclose(
            catalog.load("scored_test")["score"], source["test_scores"], rtol=0, atol=1e-12
        )
