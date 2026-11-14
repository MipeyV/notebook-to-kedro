"""A configured operation ships the same runnable project and independent test suite."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from notebook_to_kedro import GenerateRequest, LocalProjectConfiguration, run_local_operation

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
def test_configured_generation_delivers_real_passing_regressions(
    tmp_path: Path, suffix: str
) -> None:
    root = tmp_path / "workspace"
    shutil.copytree(ROOT / "examples/functional_workflow", root / "examples/functional_workflow")
    profile = root / "profile.json"
    shutil.copyfile(ROOT / "examples/kedro_profiles/team_training.json", profile)
    config = LocalProjectConfiguration(
        root,
        root / f"examples/functional_workflow/workflow{suffix}",
        "functional",
        package_name="configured_delivery",
        workflow_configuration=root / "examples/functional_workflow/workflow.json",
        architecture_profile=profile,
        regression_contract=root / "examples/functional_workflow/regression.json",
    )
    destination = root / "project"
    result = run_local_operation(GenerateRequest(config, destination))
    assert result.to_dict()["execution_status"] == "not_run"
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTEST_ADDOPTS", None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    report = tmp_path / "pytest.xml"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(destination / "pyproject.toml"),
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(tmp_path / "pytest-tmp"),
            "--junitxml",
            str(report),
            "-q",
            "--tb=short",
        ],
        cwd=destination,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    results = ET.parse(report).getroot()
    assert len(results.findall(".//testcase")) == 5
    assert not results.findall(".//skipped")
    assert not results.findall(".//failure")
    assert not results.findall(".//error")
    snapshot = json.loads((destination / "regression-coverage.json").read_text())
    assert snapshot["execution_status"] == "not_run"
