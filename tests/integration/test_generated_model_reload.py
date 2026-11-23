"""Delivered tests must inspect actual stored predictions, not a retained parent object."""

from __future__ import annotations

import json
import os
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


def _project(  # noqa: PLR0913
    tmp_path: Path,
    *,
    custom: bool = False,
    nested: bool = False,
    no_csv: bool = False,
    typed: bool = False,
    enforce: bool = False,
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
            enforce_node_types=enforce,
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
@pytest.mark.parametrize("enforce", [False, True])
def test_explicit_types_preserve_delivered_pipeline_and_fresh_model_reload(
    tmp_path: Path, *, custom: bool, enforce: bool
) -> None:
    project = _project(tmp_path, custom=custom, nested=True, typed=True, enforce=enforce)
    result = _run(project, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 passed" in result.stdout
    report = json.loads((project / "node-types.json").read_text(encoding="utf-8"))
    assert not report["untyped_datasets"]
    # External test execution never rewrites the generation-time declaration status.
    assert report["runtime_type_validation"] == "not_run"
    assert ("runtime_checks" in report) is enforce


@pytest.mark.parametrize(("dataset", "code"), [("df", "NTV001"), ("X", "NTV002")])
def test_runtime_type_failures_stop_kedro_before_model_publication_under_optimization(
    tmp_path: Path, dataset: str, code: str
) -> None:
    project = _project(tmp_path, nested=True, typed=True, enforce=True)
    declaration = json.loads((project / "node-types.json").read_text(encoding="utf-8"))[
        "declaration"
    ]
    declaration["datasets"][dataset] = "str"
    source = project.parent / "workflow.ipynb"
    target = project.parent / "wrong_types"
    with chdir(source.parent):
        generate_kedro_project(
            plan_notebook_path(source),
            target,
            source_facts=analyze_notebook_path(source),
            package_name="wrong_types",
            node_types=NotebookTypeContract(
                declaration["source_sha256"], tuple(declaration["datasets"].items())
            ),
            enforce_node_types=True,
            model_output="fitted_model",
        )
    result = subprocess.run(
        [sys.executable, "-O", "-m", "kedro", "run"],
        cwd=target,
        env={**os.environ, "PYTHONPATH": str(target / "src"), "KEDRO_DISABLE_TELEMETRY": "1"},
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode != 0
    assert code in result.stdout + result.stderr
    assert not (target / "data/06_models").exists()


_WHEEL_RUNTIME_CHECK = """import builtins
import sys
sys.path.insert(0, sys.argv[1])
original_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split(".")[0] == "notebook_to_kedro":
        raise RuntimeError("Generated runtime imported the converter")
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded
import reload_example
import pandas as pd
from reload_example.pipeline_registry import register_pipelines
if ".whl" not in reload_example.__file__:
    raise RuntimeError("The generated package did not load from its wheel")
function = register_pipelines()["__default__"].nodes[0].func
try:
    function(df=[])
except TypeError as error:
    if "NTV001" not in str(error):
        raise RuntimeError("Wrong runtime diagnostic") from error
else:
    raise RuntimeError("Runtime class check was disabled by -O")
result = function(df=pd.DataFrame({"x": [0.0, 1.0], "y": [0, 1]}))
if not isinstance(result[0], pd.DataFrame) or not isinstance(result[1], pd.Series):
    raise RuntimeError("Declared outputs failed positive checks")
print("Wheel runtime checks passed under -O without the converter")
"""


def test_generated_runtime_is_packaged_and_works_from_a_wheel_without_converter_imports(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path, nested=True, typed=True, enforce=True)
    built = subprocess.run(
        [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(tmp_path / "dist")],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    wheel = next((tmp_path / "dist").glob("*.whl"))
    empty = tmp_path / "empty"
    empty.mkdir()
    result = subprocess.run(
        [sys.executable, "-O", "-I", "-c", _WHEEL_RUNTIME_CHECK, str(wheel)],
        cwd=empty,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Wheel runtime checks passed under -O without the converter" in result.stdout


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
