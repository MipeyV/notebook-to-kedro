"""Run standalone positive/error suites and reject misleading exception matches."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    KedroArchitectureProfile,
    WorkflowRegressionContract,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
)

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_control_flow"


def _run(project: Path, report: Path) -> tuple[subprocess.CompletedProcess[str], ET.Element]:
    environment = dict(os.environ)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment.pop("PYTEST_ADDOPTS", None)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(project / "pyproject.toml"),
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(report.with_suffix("")),
            "--junitxml",
            str(report),
            "-q",
            "--tb=short",
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert report.is_file(), result.stdout + result.stderr
    return result, ET.parse(report).getroot()


def _generate(
    root: Path,
    data: dict[str, Any],
    *,
    suffix: str = ".py",
    fixtures: bool = False,
    profile: bool = True,
) -> Path:
    captures: tuple[str, ...] = ()
    if fixtures:
        captures = tuple(json.dumps(case) for case in data["scenarios"])
        data = {
            "schema_version": "1.2",
            "storage": "fixtures",
            "scenarios": [
                {"path": f"case_{i}.json", "sha256": hashlib.sha256(text.encode()).hexdigest()}
                for i, text in enumerate(captures)
            ],
        }
    contract = WorkflowRegressionContract.from_dict(data, fixture_jsons=captures)
    project = root / "project"
    generate_functional_kedro_project(
        EXAMPLE / ("workflow" + suffix),
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
        project,
        project_root=ROOT,
        regression_contract=contract,
        architecture_profile=KedroArchitectureProfile("errors.test", "1.0.0", "training", "ml_")
        if profile
        else None,
    )
    return project


def _data() -> dict[str, Any]:
    return load_workflow_regression_contract(EXAMPLE / "regression-exceptions.json").to_dict()


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("fixtures", [False, True])
@pytest.mark.parametrize("profile", [False, True])
def test_fourteen_shipped_tests_preserve_positive_cases_and_error_paths(
    tmp_path: Path, suffix: str, *, fixtures: bool, profile: bool
) -> None:
    data = _data()
    old = load_workflow_regression_contract(EXAMPLE / "regression.json").to_dict()
    assert data["scenarios"][:3] == old["scenarios"]
    project = _generate(tmp_path, data, suffix=suffix, fixtures=fixtures, profile=profile)
    result, report = _run(project, tmp_path / "fourteen.xml")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(report.findall(".//testcase")) == 14
    assert not report.findall(".//failure")
    assert not report.findall(".//error")
    assert not (project / "data/08_reporting/report.json").exists()
    coverage = json.loads((project / "regression-coverage.json").read_text())
    assert coverage["pipeline_exception_scenarios"] == 2
    assert coverage["node_exception_scenarios"] == {
        "step_0000_clean_values": 0,
        "step_0001_winsorize": 0,
        "step_0002_summarize": 0,
    }
    assert coverage["execution_status"] == "not_run"
    assert "notebook_to_kedro" not in (project / "tests/test_workflow_regressions.py").read_text()


@pytest.mark.integration
def test_node_errors_use_the_same_literal_outcome_contract(tmp_path: Path) -> None:
    data = _data()
    data["scenarios"] = [data["scenarios"][-1]]
    case = data["scenarios"][0]
    case["nodes"] = {
        "step_0000_clean_values": {
            "inputs": {"raw_values": [None], "missing_policy": "error"},
            "raises": {"type": "ValueError", "message": "Missing observation"},
        }
    }
    project = _generate(tmp_path, data)
    result, report = _run(project, tmp_path / "node-errors.xml")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(report.findall(".//testcase")) == 2
    metadata = json.loads((project / "tests/regression_cases.json").read_text())
    metadata["contract"]["scenarios"][0]["nodes"]["step_0000_clean_values"]["raises"]["message"] = (
        "wrong message"
    )
    (project / "tests/regression_cases.json").write_text(json.dumps(metadata), encoding="utf-8")
    result, report = _run(project, tmp_path / "wrong-node-message.xml")
    assert result.returncode == 1
    assert len(report.findall(".//failure")) == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    "control",
    ["message", "type", "owner", "no_error", "catalog", "registry", "subclass", "published"],
)
def test_pipeline_error_expectations_reject_false_positives(tmp_path: Path, control: str) -> None:
    data = _data()
    data["scenarios"] = [data["scenarios"][-1]]
    case = data["scenarios"][0]
    if control == "message":
        case["raises"]["message"] = "Missing.*"
    elif control == "type":
        case["raises"]["type"] = "TypeError"
    elif control == "owner":
        case["raises"]["node"] = "step_0002_summarize"
    elif control == "no_error":
        case["inputs"]["raw_values"] = [1.0, 2.0]
    project = _generate(tmp_path, data)
    if control == "catalog":
        catalog_path = project / "conf/base/catalog.yml"
        catalog = json.loads(catalog_path.read_text())
        catalog["report"]["filepath"] = "../outside.json"
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    elif control == "registry":
        registry = project / "src/generated_workflow/pipeline_registry.py"
        registry.write_text('raise ValueError("Missing observation")\n', encoding="utf-8")
    elif control == "subclass":
        source = project / "src/generated_workflow/workflow_source.py"
        text = source.read_text()
        changed = text.replace("raise ValueError(", "raise UnicodeError(")
        assert changed != text
        source.write_text(changed, encoding="utf-8")
    elif control == "published":
        source = project / "src/generated_workflow/workflow_source.py"
        text = source.read_text()
        changed = text.replace(
            "    cleaned = []",
            "    from pathlib import Path\n"
            '    Path("data/08_reporting").mkdir(parents=True, exist_ok=True)\n'
            '    Path("data/08_reporting/report.json").write_text("{}")\n'
            "    cleaned = []",
        )
        assert changed != text
        source.write_text(changed, encoding="utf-8")
    result, report = _run(project, tmp_path / "negative.xml")
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(report.findall(".//failure")) == 1
    assert not (tmp_path / "outside.json").exists()


@pytest.mark.integration
@pytest.mark.parametrize("field", ["storage", "schema_version"])
def test_new_fixture_header_is_checked_before_application_imports(
    tmp_path: Path, field: str
) -> None:
    project = _generate(tmp_path, _data(), fixtures=True)
    metadata_path = project / "tests/regression_cases.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["contract"][field] = "invalid"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    result, report = _run(project, tmp_path / "header.xml")
    assert result.returncode == 2
    assert "Invalid generated fixture contract" in result.stdout
    assert len(report.findall(".//error")) == 1
