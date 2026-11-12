"""Supplied oracles stay immutable, strict, bounded and independent of source execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    WorkflowRegressionContract,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
    plan_functional_workflow_path,
)
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import FunctionalWorkflowError, WorkflowRegressionError
from notebook_to_kedro.generation.kedro.regression_contract import (
    MAX_REGRESSION_BYTES,
    MAX_REGRESSION_DEPTH,
    validate_regression_binding,
)

ROOT = Path(__file__).parents[3]
EXAMPLE = ROOT / "examples/functional_workflow"


def _data(**changes: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scenarios": [
            {
                "id": "case",
                "inputs": {"values": -3.0},
                "parameters": {"scale": 2.0},
                "expected": 6.0,
            }
        ],
        **changes,
    }


def _scenario(**changes: Any) -> dict[str, Any]:
    return {**_data()["scenarios"][0], **changes}


def test_immutable_identity_and_fresh_exports() -> None:
    data = _data()
    contract = WorkflowRegressionContract.from_dict(data)
    assert len(contract.sha256) == 64
    assert WorkflowRegressionContract(json.dumps(data, indent=2)).sha256 == contract.sha256
    data["scenarios"][0]["expected"] = 99
    exported = contract.to_dict()
    exported["scenarios"][0]["expected"] = 0
    assert contract.to_dict()["scenarios"][0]["expected"] == 6.0
    assert (
        load_workflow_regression_contract(EXAMPLE / "regression.json").to_dict()["scenarios"][0][
            "expected"
        ]
        == 6.0
    )


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        _data(schema_version="2"),
        _data(extra=1),
        _data(scenarios={}),
        _data(scenarios=[]),
        _data(scenarios=[_scenario()] * 101),
        _data(scenarios=[None]),
        _data(scenarios=[{}]),
        _data(scenarios=[_scenario(extra=1)]),
        _data(scenarios=[_scenario(id=1)]),
        _data(scenarios=[_scenario(id="../bad")]),
        _data(scenarios=[_scenario(), _scenario()]),
        _data(scenarios=[_scenario(inputs=[])]),
        _data(scenarios=[_scenario(parameters=[])]),
        _data(scenarios=[_scenario(nodes=[])]),
        _data(scenarios=[_scenario(nodes={"step": {}})]),
        _data(scenarios=[_scenario(nodes={"step": {"inputs": [], "expected": 1}})]),
        _data(scenarios=[_scenario(expected=float("nan"))]),
        _data(scenarios=[_scenario(expected=object())]),
        _data(scenarios=[_scenario(expected={1: "bad key"})]),
    ],
    ids=[f"invalid-{i}" for i in range(22)],
)
def test_invalid_contracts(data: object) -> None:
    with pytest.raises(WorkflowRegressionError):
        WorkflowRegressionContract.from_dict(data)


def test_depth_and_large_numbers_are_rejected() -> None:
    nested: Any = 0
    for _ in range(MAX_REGRESSION_DEPTH + 1):
        nested = [nested]
    with pytest.raises(WorkflowRegressionError, match="nesting"):
        WorkflowRegressionContract.from_dict(_data(scenarios=[_scenario(expected=nested)]))
    with pytest.raises(WorkflowRegressionError, match="serialize"):
        WorkflowRegressionContract.from_dict(_data(scenarios=[_scenario(expected=10**5000)]))


@pytest.mark.parametrize(
    "source",
    [
        "{",
        "[" * 2000,
        "\ud800",
        " " * (MAX_REGRESSION_BYTES + 1),
        '{"schema_version": "1.0", "schema_version": "1.0"}',
        '{"schema_version":"1.0", "scenarios":[{"id":"case",'
        '"inputs":{},"parameters":{},"expected":NaN}]}',
    ],
    ids=["syntax", "recursion", "unicode", "size", "duplicate", "nan"],
)
def test_direct_serialized_values_are_validated(source: str) -> None:
    with pytest.raises(WorkflowRegressionError):
        WorkflowRegressionContract(source)


def test_direct_non_text_is_rejected() -> None:
    with pytest.raises(WorkflowRegressionError):
        WorkflowRegressionContract(1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "content", [b"\xff", b" " * (MAX_REGRESSION_BYTES + 1)], ids=["encoding", "size"]
)
def test_invalid_files(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "cases.json"
    path.write_bytes(content)
    with pytest.raises(WorkflowRegressionError):
        load_workflow_regression_contract(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(WorkflowRegressionError):
        load_workflow_regression_contract(tmp_path / "missing.json")


@pytest.mark.parametrize(
    "changes",
    [
        {"inputs": {}},
        {"parameters": {}},
        {"parameters": {"scale": []}},
        {"nodes": {"unknown": {"inputs": {}, "expected": 1}}},
        {"nodes": {"step_0000_prepare_values": {"inputs": {"values": 1}, "expected": 1}}},
    ],
)
def test_binding_rejects_wrong_names_or_mutable_parameters(changes: dict[str, Any]) -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    plan = plan_functional_workflow_path(EXAMPLE / "workflow.py", config)
    contract = WorkflowRegressionContract.from_dict(_data(scenarios=[_scenario(**changes)]))
    with pytest.raises(FunctionalWorkflowError):
        validate_regression_binding(contract, plan)


def test_missing_expectations_are_reported_without_passing_stubs(tmp_path: Path) -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    destination = tmp_path / "project"
    generate_functional_kedro_project(
        EXAMPLE / "workflow.py", config, destination, project_root=ROOT
    )
    report = json.loads((destination / "regression-coverage.json").read_text())
    assert report["status"] == "no_expectations"
    assert report["execution_status"] == "not_run"
    assert report["missing_pipeline_expectations"]
    assert len(report["missing_node_expectations"]) == 2
    assert not (destination / "tests").exists()
    assert "No expectations" in (destination / "TESTING.md").read_text()


def test_cli_contract_and_no_execution_claim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "project"
    assert (
        main(
            [
                "generate-workflow",
                str(EXAMPLE / "workflow.py"),
                str(EXAMPLE / "workflow.json"),
                str(destination),
                "--project-root",
                str(ROOT),
                "--regression-contract",
                str(EXAMPLE / "regression.json"),
            ]
        )
        == 0
    )
    assert "Created functional" in capsys.readouterr().out
    report = json.loads((destination / "regression-coverage.json").read_text())
    assert report["pipeline_scenarios"] == 3
    assert report["node_scenarios"] == {"step_0000_prepare_values": 1, "step_0001_summarize": 1}
    assert report["missing_node_expectations"] == []
    assert report["execution_status"] == "not_run"
    assert report["review_status"] == "not_authenticated"
    assert (destination / "tests/test_workflow_regressions.py").exists()


def test_partial_node_coverage_and_invalid_binding_before_publication(tmp_path: Path) -> None:
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    contract = WorkflowRegressionContract.from_dict(_data())
    destination = tmp_path / "partial"
    generate_functional_kedro_project(
        EXAMPLE / "workflow.py",
        config,
        destination,
        project_root=ROOT,
        regression_contract=contract,
    )
    report = json.loads((destination / "regression-coverage.json").read_text())
    assert len(report["missing_node_expectations"]) == 2
    invalid = WorkflowRegressionContract.from_dict(_data(scenarios=[_scenario(inputs={})]))
    with pytest.raises(WorkflowRegressionError):
        generate_functional_kedro_project(
            EXAMPLE / "workflow.py",
            config,
            tmp_path / "invalid",
            project_root=ROOT,
            regression_contract=invalid,
        )
    assert not (tmp_path / "invalid").exists()


def test_generation_does_not_import_source_or_infer_expected_results(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text(
        (EXAMPLE / "workflow.py")
        .read_text(encoding="utf-8")
        .replace("import math", "import math\nimport absent_regression_dependency"),
        encoding="utf-8",
    )
    config = load_functional_workflow_configuration(EXAMPLE / "workflow.json")
    contract = WorkflowRegressionContract.from_dict(
        _data(scenarios=[_scenario(expected={"supplied": [None, True, "é", 999]})])
    )
    destination = tmp_path / "project"
    generate_functional_kedro_project(
        source, config, destination, project_root=ROOT, regression_contract=contract
    )
    metadata = json.loads((destination / "tests/regression_cases.json").read_text())
    assert metadata["contract"]["scenarios"][0]["expected"] == {"supplied": [None, True, "é", 999]}
