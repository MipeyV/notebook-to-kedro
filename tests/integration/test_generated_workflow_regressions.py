"""Execute shipped pytest suites in fresh processes and prove meaningful negative controls."""

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
from notebook_to_kedro.exceptions import WorkflowRegressionError
from notebook_to_kedro.generation.writer import write_project

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


def _fixture_contract(root: Path, scenarios: list[dict[str, Any]]) -> Path:
    directory = root / "fixtures"
    directory.mkdir()
    references = []
    for index, scenario in enumerate(scenarios):
        source = json.dumps(scenario, indent=2).replace("\n", "\r\n").encode()
        path = directory / f"scenario_{index}.json"
        path.write_bytes(source)
        references.append(
            {"path": f"fixtures/{path.name}", "sha256": hashlib.sha256(source).hexdigest()}
        )
    path = root / "fixture-contract.json"
    path.write_text(
        json.dumps({"schema_version": "1.1", "scenarios": references}), encoding="utf-8"
    )
    return path


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
@pytest.mark.parametrize("custom_profile", [False, True])
def test_fixture_suites_are_self_contained_and_detect_code_drift(
    tmp_path: Path, suffix: str, *, custom_profile: bool
) -> None:
    data = load_workflow_regression_contract(EXAMPLE / "regression.json").to_dict()
    contract_path = _fixture_contract(tmp_path, data["scenarios"])
    contract = load_workflow_regression_contract(contract_path)
    # The direct API publishes its validated snapshot, without reopening source fixtures.
    for source_fixture in (tmp_path / "fixtures").iterdir():
        source_fixture.unlink()
    contract_path.unlink()
    project = tmp_path / "project"
    generate_functional_kedro_project(
        EXAMPLE / ("workflow" + suffix),
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
        project,
        project_root=ROOT,
        regression_contract=contract,
        architecture_profile=KedroArchitectureProfile("fixture.test", "1.0.0", "training", "ml_")
        if custom_profile
        else None,
    )
    report = json.loads((project / "regression-coverage.json").read_text())
    assert report["pipeline_scenarios"] == 3
    assert report["missing_node_expectations"] == []
    for fixture, captured in zip(report["fixtures"], contract.fixture_jsons, strict=True):
        assert (project / fixture["path"]).read_bytes() == captured.encode()
        assert hashlib.sha256(captured.encode()).hexdigest() == fixture["sha256"]
    result, xml = _run(project, tmp_path / "fixture-pass.xml")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(xml.findall(".//testcase")) == 5
    source = project / "src/generated_workflow/workflow_source.py"
    source.write_text(
        source.read_text().replace("prepared = values * scale", "prepared = values + scale")
        + "\n# fixture-suite negative control\n",
        encoding="utf-8",
    )
    result, xml = _run(project, tmp_path / "fixture-code-drift.xml")
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(xml.findall(".//failure")) == 4
    assert not xml.findall(".//error")


@pytest.mark.integration
def test_runtime_fixture_guards_fail_before_application_import(tmp_path: Path) -> None:
    data = load_workflow_regression_contract(EXAMPLE / "regression.json").to_dict()
    contract = load_workflow_regression_contract(_fixture_contract(tmp_path, data["scenarios"]))
    project = tmp_path / "project"
    generate_functional_kedro_project(
        EXAMPLE / "workflow.py",
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
        project,
        project_root=ROOT,
        regression_contract=contract,
    )
    source = project / "src/generated_workflow/workflow_source.py"
    source.write_text("raise AssertionError('APPLICATION_MUST_NOT_IMPORT')\n", encoding="utf-8")
    metadata_path = project / "tests/regression_cases.json"
    metadata = json.loads(metadata_path.read_text())
    definition = metadata["contract"]["scenarios"][0]
    fixture = project / "tests" / definition["path"]
    original = fixture.read_bytes()
    for index, (change, message) in enumerate(
        (
            ("hash", "SHA-256"),
            ("size", "byte budget"),
            ("directory", "regular files"),
            ("escape", "contained generated paths"),
            ("version", "Invalid generated"),
            ("count", "Invalid generated"),
            ("aggregate", "byte budget"),
        )
    ):
        changed = json.loads(json.dumps(metadata))
        if change == "hash":
            fixture.write_bytes(original + b" ")
        elif change == "size":
            fixture.write_bytes(b" " * (1024 * 1024 + 1))
        elif change == "directory":
            fixture.unlink()
            fixture.mkdir()
        elif change == "escape":
            changed["contract"]["scenarios"][0]["path"] = "../outside.json"
        elif change == "version":
            changed["contract"]["schema_version"] = "1.0"
        elif change == "count":
            changed["contract"]["scenarios"] *= 34
        else:
            payload = original + b" " * (1024 * 1024 - len(original))
            digest = hashlib.sha256(payload).hexdigest()
            large = project / "tests/regression_fixtures" / (digest + ".json")
            large.write_bytes(payload)
            changed["contract"]["scenarios"] = [
                {"path": "regression_fixtures/" + digest + ".json", "sha256": digest}
            ] * 9
        metadata_path.write_text(json.dumps(changed), encoding="utf-8")
        result, xml = _run(project, tmp_path / f"fixture-guard-{index}.xml")
        assert result.returncode == 2, result.stdout + result.stderr
        assert xml.findall(".//error")
        assert message in result.stdout
        assert "APPLICATION_MUST_NOT_IMPORT" not in result.stdout + result.stderr
        if fixture.is_dir():
            fixture.rmdir()
        fixture.write_bytes(original)


@pytest.mark.integration
def test_eight_step_notebook_retains_every_oracle_and_ships_27_passing_tests(
    tmp_path: Path,
) -> None:
    corpus = json.loads(
        (ROOT / "examples/agent_comparison/challenges/corpus.json").read_text(encoding="utf-8")
    )
    case = next(c for c in corpus["cases"] if c["case_id"] == "larger-ml-notebook")
    root = tmp_path / "source"
    write_project(
        root,
        {Path(name): text for name, text in case["files"].items() if name.startswith("input/")},
    )
    with pytest.raises(WorkflowRegressionError, match="64 KiB"):
        load_workflow_regression_contract(root / "input/regression.json")
    expected = json.loads((root / "input/regression.json").read_text())
    manifest = _fixture_contract(root / "input", expected["scenarios"])
    contract = load_workflow_regression_contract(manifest)
    assert contract.resolved_dict() == expected
    assert len(contract.canonical_json.encode()) < 65536
    assert sum(len(text.encode()) for text in contract.fixture_jsons) > 65536
    project = tmp_path / "project"
    generate_functional_kedro_project(
        root / "input/workflow.ipynb",
        load_functional_workflow_configuration(root / "input/workflow.json"),
        project,
        project_root=root,
        package_name="eight_step_fixtures",
        regression_contract=contract,
        architecture_profile=KedroArchitectureProfile("fixture.large", "1.0.0", "training", "ml_"),
    )
    result, xml = _run(project, tmp_path / "eight-step.xml")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(xml.findall(".//testcase")) == 27
    assert not xml.findall(".//failure")
    assert not xml.findall(".//error")
    report = json.loads((project / "regression-coverage.json").read_text())
    assert report["missing_node_expectations"] == []
    assert report["pipeline_scenarios"] == 3
    assert sum(report["node_scenarios"].values()) == 24
    source = project / "src/eight_step_fixtures/workflow_source.py"
    original = source.read_text()
    changed = original.replace("+ fitted['intercept']", "- fitted['intercept']")
    assert changed != original
    source.write_text(changed + "\n# eight-step negative control\n", encoding="utf-8")
    result, xml = _run(project, tmp_path / "eight-step-mutation.xml")
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(xml.findall(".//failure")) == 6
    assert not xml.findall(".//error")
