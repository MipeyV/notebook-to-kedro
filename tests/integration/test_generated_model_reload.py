"""Delivered tests must inspect actual stored predictions, not a retained parent object."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from contextlib import chdir
from pathlib import Path

import pytest

from notebook_to_kedro import (
    KedroArchitectureProfile,
    NotebookTypeContract,
    analyze_notebook_path,
    generate_kedro_project,
    load_notebook_regression_contract,
    plan_notebook_path,
)

ROOT = Path(__file__).parents[2]
pytestmark = pytest.mark.integration


def _project(
    tmp_path: Path,
    *,
    custom: bool = False,
    nested: bool = False,
    no_csv: bool = False,
    typed: bool = False,
) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(ROOT / "examples/model_reload", workspace)
    source = workspace / "workflow.ipynb"
    notebook = json.loads(source.read_text(encoding="utf-8"))
    if nested:
        imports = (
            "from sklearn.pipeline import Pipeline\n"
            "from sklearn.preprocessing import StandardScaler\n"
        )
        notebook["cells"][0]["source"].insert(0, imports)
        notebook["cells"][1]["source"] = [
            'model = Pipeline([("scale", StandardScaler()), '
            '("classifier", DecisionTreeClassifier(random_state=42))])\n',
            "model.fit(X, y)",
        ]
    if no_csv:
        original = "".join(notebook["cells"][0]["source"])
        notebook["cells"][0]["source"] = original.replace(
            'pd.read_csv("data/training.csv")',
            'pd.DataFrame({"x": [0.0, 1.0, 2.0, 3.0], "y": [0, 0, 1, 1]})',
        )
        path = workspace / "regression.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["fixtures"] = {}
        data["scenarios"] = [data["scenarios"][0]]
        data["scenarios"][0]["inputs"] = {}
        for check in data["model_checks"]:
            check["input"] = {
                "kind": "frame",
                "columns": ["x"],
                "data": [[0.0], [3.0]],
                "dtypes": ["float64"],
                "index": [0, 1],
                "index_name": None,
                "column_name": None,
            }
        path.write_text(json.dumps(data), encoding="utf-8")
    source.write_text(json.dumps(notebook), encoding="utf-8")
    project = workspace / "project"
    profile = (
        KedroArchitectureProfile("reload.example", "1.0.0", "training", "ml_") if custom else None
    )
    with chdir(workspace):
        facts = analyze_notebook_path(source)
        generate_kedro_project(
            plan_notebook_path(source),
            project,
            source_facts=facts,
            package_name="reload_example",
            architecture_profile=profile,
            model_output="fitted_model",
            regression_contract=load_notebook_regression_contract(workspace / "regression.json"),
            node_types=None
            if not typed
            else NotebookTypeContract(
                facts.notebook.content_sha256,
                (
                    ("df", "pandas.DataFrame"),
                    ("X", "pandas.DataFrame"),
                    ("y", "pandas.Series"),
                    ("model", "sklearn.pipeline.Pipeline"),
                    ("fitted_model", "sklearn.pipeline.Pipeline"),
                    ("predictions", "numpy.ndarray"),
                ),
            ),
        )
    return project


def _run(project: Path, tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--basetemp=" + str(tmp_path / "executed"), *args],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_delivered_reload_checks_run_for_plain_and_nested_models(
    tmp_path: Path, *, custom: bool, nested: bool
) -> None:
    project = _project(tmp_path, custom=custom, nested=nested)
    result = _run(project, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 passed" in result.stdout
    assert not (project / "data/06_models").exists()
    artifacts = {
        artifact.resolve()
        for artifact in (tmp_path / "executed").glob(
            "*/data/06_models/model.pkl/model-check/model.pkl"
        )
    }
    assert len(artifacts) == 2
    assert all(artifact.is_file() for artifact in artifacts)


def test_model_only_catalog_and_frame_probes_have_a_working_delivered_suite(tmp_path: Path) -> None:
    project = _project(tmp_path, no_csv=True, nested=True)
    result = _run(project, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 passed" in result.stdout
    assert not (project / "data/06_models").exists()


@pytest.mark.parametrize("custom", [False, True])
def test_explicit_types_preserve_delivered_pipeline_and_fresh_model_reload(
    tmp_path: Path, *, custom: bool
) -> None:
    project = _project(tmp_path, custom=custom, nested=True, typed=True)
    result = _run(project, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 passed" in result.stdout
    report = json.loads((project / "node-types.json").read_text(encoding="utf-8"))
    assert not report["untyped_datasets"]
    # External test execution never rewrites the generation-time declaration status.
    assert report["runtime_type_validation"] == "not_run"


_WRONG_MODEL = """import copy
from kedro_datasets.pickle import PickleDataset
original = PickleDataset.save
def wrong(self, data):
    data = copy.deepcopy(data)
    estimator = data.named_steps["classifier"] if hasattr(data, "named_steps") else data
    estimator.tree_.value[:] = estimator.tree_.value[..., ::-1]
    return original(self, data)
PickleDataset.save = wrong
"""

_CORRUPT_MODEL = """from pathlib import Path
from kedro.runner import SequentialRunner
original = SequentialRunner.run

def corrupt(self, *args, **kwargs):
    result = original(self, *args, **kwargs)
    for artifact in Path.cwd().glob("data/06_models/model.pkl/*/model.pkl"):
        artifact.write_bytes(b"broken-pickle")
    return result
SequentialRunner.run = corrupt
"""


@pytest.mark.parametrize("mutation", ["wrong_model", "corrupt", "wrong_oracle"])
def test_invalid_artifacts_and_false_prediction_oracles_fail_after_storage(
    tmp_path: Path, mutation: str
) -> None:
    project = _project(tmp_path, nested=True)
    if mutation == "wrong_oracle":
        path = project / "tests/regression_cases.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["contract"]["model_checks"][0]["expected"]["data"] = [1, 0]
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        (project / "tests/conftest.py").write_text(
            _WRONG_MODEL if mutation == "wrong_model" else _CORRUPT_MODEL, encoding="utf-8"
        )
    result = _run(project, tmp_path, "-k", "model_reload")
    assert result.returncode != 0
    assert "Fresh model reload failed" in result.stdout
    assert not (project / "data/06_models").exists()


@pytest.mark.parametrize("missing", ["dataset", "configuration"])
def test_storage_declaration_tampering_cannot_be_hidden_by_memory_outputs(
    tmp_path: Path, missing: str
) -> None:
    project = _project(tmp_path)
    path = project / "conf/base/catalog.yml"
    text = path.read_text(encoding="utf-8")
    if missing == "dataset":
        text = text[: text.index('"fitted_model":')]
    else:
        text = text.replace('"pickle"', '"json"')
    path.write_text(text, encoding="utf-8")
    result = _run(project, tmp_path, "-k", "model_reload")
    assert result.returncode != 0
    assert "Regression model catalog declaration changed" in result.stdout
    assert not list(
        (tmp_path / "executed").glob("*/data/06_models/model.pkl/model-check/model.pkl")
    )
