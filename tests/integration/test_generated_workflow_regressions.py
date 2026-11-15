"""Execute shipped pytest suites in fresh processes and prove meaningful negative controls."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from notebook_to_kedro import (
    KedroArchitectureProfile,
    WorkflowRegressionContract,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
)

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_workflow"


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


@pytest.mark.integration
@pytest.mark.parametrize("source_name", ["workflow", "expression_returns"])
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("custom_profile", [False, True])
def test_shipped_tests_pass_for_both_inputs_and_profiles(
    tmp_path: Path,
    source_name: str,
    suffix: str,
    *,
    custom_profile: bool,
) -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    contract = load_workflow_regression_contract(EXAMPLE / "regression.json")
    destination = tmp_path / "project"
    profile = (
        KedroArchitectureProfile("test.regression", "1.0.0", "training", "ml_")
        if custom_profile
        else None
    )
    generate_functional_kedro_project(
        EXAMPLE / f"{source_name}{suffix}",
        config,
        destination,
        project_root=ROOT,
        regression_contract=contract,
        architecture_profile=profile,
    )
    original_input = (destination / "data/01_raw/values.json").read_bytes()
    original_parameters = (destination / "conf/base/parameters.yml").read_bytes()
    result, report = _run(destination, tmp_path / "tests.xml")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(report.findall(".//testcase")) == 5
    assert not report.findall(".//failure")
    assert not report.findall(".//skipped")
    assert not report.findall(".//error")
    assert (destination / "data/01_raw/values.json").read_bytes() == original_input
    assert (destination / "conf/base/parameters.yml").read_bytes() == original_parameters
    assert not (destination / "data/08_reporting/total.json").exists()
    assert (
        "notebook_to_kedro" not in (destination / "tests/test_workflow_regressions.py").read_text()
    )


@pytest.mark.integration
def test_generated_suites_detect_code_oracle_and_path_regressions(tmp_path: Path) -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    contract = load_workflow_regression_contract(EXAMPLE / "regression.json")
    project = tmp_path / "project"
    generate_functional_kedro_project(
        EXAMPLE / "workflow.py", config, project, project_root=ROOT, regression_contract=contract
    )
    source = project / "src/generated_workflow/workflow_source.py"
    original = source.read_text(encoding="utf-8")
    source.write_text(
        original.replace("prepared = values * scale", "prepared = values + scale")
        + "\n# negative code control\n",
        encoding="utf-8",
    )
    result, report = _run(project, tmp_path / "bad_code.xml")
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(report.findall(".//failure")) == 4
    assert not report.findall(".//error")
    source.write_text(original + "\n# restored control\n", encoding="utf-8")
    cases_path = project / "tests/regression_cases.json"
    cases = json.loads(cases_path.read_text())
    cases["contract"]["scenarios"][0]["expected"] = 999
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    result, report = _run(project, tmp_path / "bad_oracle.xml")
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(report.findall(".//failure")) == 1
    assert not report.findall(".//error")
    cases["contract"]["scenarios"][0]["expected"] = 6.0
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    catalog_path = project / "conf/base/catalog.yml"
    catalog = json.loads(catalog_path.read_text())
    catalog["total"]["filepath"] = "../should_not_be_written.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    result, report = _run(project, tmp_path / "bad_path.xml")
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(report.findall(".//failure")) == 3
    assert "contained generated JSON" in result.stdout
    assert not (tmp_path / "should_not_be_written.json").exists()


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("custom_profile", [False, True])
def test_shipped_ordered_join_tests_keep_business_node_interfaces_and_detect_changed_logic(
    tmp_path: Path, suffix: str, *, custom_profile: bool
) -> None:
    example = ROOT / "examples/functional_join"
    config = load_functional_workflow_configuration(example / "workflow.json")
    contract = load_workflow_regression_contract(example / "regression.json")
    project = tmp_path / "project"
    profile = (
        KedroArchitectureProfile("test.ordered", "1.0.0", "validation", "ml_")
        if custom_profile
        else None
    )
    generate_functional_kedro_project(
        example / f"workflow{suffix}",
        config,
        project,
        project_root=ROOT,
        regression_contract=contract,
        architecture_profile=profile,
    )
    metadata = json.loads((project / "tests/regression_cases.json").read_text())
    assert "_ntk_after" not in json.dumps(metadata["contract"])
    result, report = _run(project, tmp_path / "ordered-join.xml")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(report.findall(".//testcase")) == 5
    assert not report.findall(".//failure")
    source = project / "src/generated_workflow/workflow_source.py"
    original = source.read_text()
    changed = original.replace("+ specification['offset']", "- specification['offset']")
    assert changed != original
    source.write_text(
        changed + "\n# deliberate synthetic arithmetic regression\n", encoding="utf-8"
    )
    result, report = _run(project, tmp_path / "ordered-join-changed.xml")
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(report.findall(".//failure")) == 3
    assert not report.findall(".//error")


@pytest.mark.integration
def test_pipeline_only_contract_does_not_invent_passing_node_tests(tmp_path: Path) -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    data = load_workflow_regression_contract(EXAMPLE / "regression.json").to_dict()
    for scenario in data["scenarios"]:
        scenario.pop("nodes", None)
    project = tmp_path / "project"
    generate_functional_kedro_project(
        EXAMPLE / "workflow.py",
        config,
        project,
        project_root=ROOT,
        regression_contract=WorkflowRegressionContract.from_dict(data),
    )
    result, report = _run(project, tmp_path / "pipeline_only.xml")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(report.findall(".//testcase")) == 3
    assert not report.findall(".//skipped")
    coverage = json.loads((project / "regression-coverage.json").read_text())
    assert len(coverage["missing_node_expectations"]) == 2


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("custom_profile", [False, True])
def test_shipped_candidate_tests_pass_and_detect_a_changed_mapping_setting(
    tmp_path: Path, suffix: str, *, custom_profile: bool
) -> None:
    example = ROOT / "examples/functional_candidate"
    config = load_functional_workflow_configuration(example / "workflow.json")
    contract = load_workflow_regression_contract(example / "regression.json")
    project = tmp_path / "project"
    profile = (
        KedroArchitectureProfile("test.candidate", "1.0.0", "validation", "candidate_")
        if custom_profile
        else None
    )
    generate_functional_kedro_project(
        example / f"workflow{suffix}",
        config,
        project,
        project_root=ROOT,
        regression_contract=contract,
        architecture_profile=profile,
    )
    original_parameters = (project / "conf/base/parameters.yml").read_bytes()
    result, report = _run(project, tmp_path / "candidate.xml")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(report.findall(".//testcase")) == 3
    assert not report.findall(".//failure")
    assert (project / "conf/base/parameters.yml").read_bytes() == original_parameters
    cases_path = project / "tests/regression_cases.json"
    cases = json.loads(cases_path.read_text())
    cases["contract"]["scenarios"][1]["parameters"]["candidate"]["scale"] = 99.0
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    result, report = _run(project, tmp_path / "candidate-changed.xml")
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(report.findall(".//failure")) == 1
    assert not report.findall(".//error")


@pytest.mark.integration
@pytest.mark.parametrize("custom_profile", [False, True])
def test_shipped_package_pipeline_tests_keep_resources_and_report_typed_node_gaps(
    tmp_path: Path, *, custom_profile: bool
) -> None:
    example = ROOT / "examples/functional_package"
    config = load_functional_workflow_configuration(example / "workflow.json")
    contract = load_workflow_regression_contract(example / "regression.json")
    project = tmp_path / "project"
    profile = (
        KedroArchitectureProfile("test.package", "1.0.0", "training", "ml_")
        if custom_profile
        else None
    )
    generate_functional_kedro_project(
        example / "src/example_ml/workflow.py",
        config,
        project,
        project_root=ROOT,
        regression_contract=contract,
        architecture_profile=profile,
    )
    original = (example / "src/example_ml/assets/offset.json").read_bytes()
    result, report = _run(project, tmp_path / "package.xml")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(report.findall(".//testcase")) == 2
    assert not report.findall(".//failure")
    gaps = json.loads((project / "regression-coverage.json").read_text())
    assert gaps["missing_node_expectations"] == ["step_0000_prepare", "step_0001_summarize"]
    asset = project / "src/example_ml/assets/offset.json"
    asset.write_text('{"offset": 0.5}', encoding="utf-8")
    result, report = _run(project, tmp_path / "package-changed-resource.xml")
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(report.findall(".//failure")) == 2
    assert not report.findall(".//error")
    assert (example / "src/example_ml/assets/offset.json").read_bytes() == original
