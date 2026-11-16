"""Trusted local distributions expose real metadata through installed Kedro entrypoints."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import zipfile
from email.parser import BytesParser
from pathlib import Path

import pytest

from notebook_to_kedro import (
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
)

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_distribution"

_PROBE = """import importlib, json, sys
from importlib.metadata import distribution, version
from pathlib import Path
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner

project, expected_lock, editable = Path(sys.argv[1]), sys.argv[2], sys.argv[3] == "True"
app = distribution("synthetic-distribution-example")
assert app.version == "1.2.3"
assert "nbformat<6,>=5.10" in app.requires
assert "test" in app.metadata.get_all("Provides-Extra")
entry = next(item for item in app.entry_points if item.name == "distribution-example")
assert entry.value == "distribution_ml.cli:main"
entry.load()()
module = importlib.import_module("distribution_ml.workflow")
source_root = project / "application/src" if editable else Path(sys.prefix)
assert Path(module.__file__).resolve().is_relative_to(source_root.resolve())
registry = importlib.import_module("distribution_case.pipeline_registry")
assert Path(registry.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
loader = OmegaConfigLoader(conf_source=str(project / "conf/base"))
catalog = DataCatalog.from_config(loader["catalog"])
catalog["params:factor"] = MemoryDataset(loader["parameters"]["factor"])
SequentialRunner().run(registry.register_pipelines()["__default__"], catalog)
actual = json.loads((project / "data/08_reporting/result.json").read_text())
assert actual == {
    "value": 6.0, "version": "1.2.3", "resource": "synthetic-resource",
    "lock_sha256": expected_lock if editable else None,
}, actual
print(json.dumps({"metadata_version": version("synthetic-distribution-example"),
                  "editable": editable, "result": actual}))
"""


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "UV_PROJECT_ENVIRONMENT",
        "PYTEST_ADDOPTS",
    ):
        environment.pop(name, None)
    environment.update(DO_NOT_TRACK="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run(
        command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.mark.integration
@pytest.mark.parametrize("editable", [False, True])
def test_built_application_and_generated_wheels_install_and_run_with_real_metadata(
    tmp_path: Path,
    *,
    editable: bool,
) -> None:
    project = tmp_path / "project"
    lock_sha256 = hashlib.sha256((EXAMPLE / "application.lock").read_bytes()).hexdigest()
    expected = {
        "value": 6.0,
        "version": "1.2.3",
        "resource": "synthetic-resource",
        "lock_sha256": lock_sha256 if editable else None,
    }
    expectations = tmp_path / "regression.json"
    expectations.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "scenarios": [
                    {
                        "id": "installed",
                        "inputs": {"raw": 3.0},
                        "parameters": {"factor": 2.0},
                        "expected": expected,
                        "nodes": {
                            "step_0000_report": {
                                "inputs": {"raw": 3.0, "factor": 2.0},
                                "expected": expected,
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    generate_functional_kedro_project(
        EXAMPLE / "src/distribution_ml/workflow.py",
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
        project,
        project_root=ROOT,
        package_name="distribution_case",
        regression_contract=load_workflow_regression_contract(expectations),
    )
    # Build only this repository's trusted synthetic application and generated wrapper.
    backend_call = (
        "from hatchling.build import build_editable; build_editable('dist')"
        if editable
        else "from hatchling.build import build_wheel; build_wheel('dist')"
    )
    _run([sys.executable, "-I", "-c", backend_call], project / "application")
    _run([sys.executable, "-I", "-m", "hatchling", "build", "--target", "wheel"], project)
    app_wheel = next((project / "application/dist").glob("*.whl"))
    generated_wheel = next((project / "dist").glob("*.whl"))
    with zipfile.ZipFile(generated_wheel) as archive:
        assert not any(name.startswith("distribution_ml/") for name in archive.namelist())
        metadata = BytesParser().parsebytes(
            archive.read(
                next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
            )
        )
        assert "synthetic-distribution-example==1.2.3" in metadata.get_all("Requires-Dist", [])
    # Reuse locked runtime dependencies through an explicit site path in a new environment.
    environment = tmp_path / "venv"
    _run(
        [
            sys.executable,
            "-I",
            "-m",
            "venv",
            "--copies",
            "--without-pip",
            str(environment),
        ],
        tmp_path,
    )
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    site = (
        environment / "Lib/site-packages"
        if os.name == "nt"
        else environment
        / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    )
    (site / "locked-runtime.pth").write_text(sysconfig.get_path("purelib") + "\n", encoding="utf-8")
    uv = shutil.which("uv")
    assert uv is not None, "The repository verification environment requires uv"
    _run(
        [
            uv,
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--python",
            str(python),
            str(app_wheel),
            str(generated_wheel),
        ],
        tmp_path,
    )
    probe = _run(
        [str(python), "-I", "-c", _PROBE, str(project), lock_sha256, str(editable)], project
    )
    assert '"metadata_version": "1.2.3"' in probe.stdout
    shipped = _run(
        [
            str(python),
            "-I",
            "-m",
            "pytest",
            "tests",
            "-q",
            "-o",
            "addopts=",
            "--basetemp",
            str(tmp_path / "shipped-tmp"),
        ],
        project,
    )
    assert "2 passed" in shipped.stdout
    _run([str(python), "-I", "-m", "kedro", "run"], project)
