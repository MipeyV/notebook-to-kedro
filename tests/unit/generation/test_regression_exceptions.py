"""Explicit exception outcomes stay narrow, immutable and independent of source execution."""

from __future__ import annotations

import ast
import hashlib
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
from notebook_to_kedro.exceptions import WorkflowRegressionError
from notebook_to_kedro.generation.kedro.regression_contract import validate_regression_binding
from notebook_to_kedro.generation.kedro.regression_outcomes import (
    EXCEPTION_NAMES,
    validate_outcome,
)

EXAMPLE = Path(__file__).parents[3] / "examples/functional_control_flow"


def _case() -> dict[str, Any]:
    return {
        "id": "strict_missing",
        "inputs": {"raw_values": [1.0, None]},
        "parameters": {"missing_policy": "error", "lower": 0.0, "upper": 5.0},
        "raises": {
            "type": "ValueError",
            "message": "Missing observation",
            "node": "step_0000_clean_values",
        },
    }


def _data(case: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "1.2", "storage": "inline", "scenarios": [case]}


@pytest.mark.parametrize("name", sorted(EXCEPTION_NAMES))
def test_concrete_builtin_types_and_empty_literal_messages(name: str) -> None:
    case = _case()
    case["raises"].update(type=name, message="")
    case["nodes"] = {
        "step_0000_clean_values": {
            "inputs": {"raw_values": [None], "missing_policy": "error"},
            "raises": {"type": name, "message": ""},
        }
    }
    contract = WorkflowRegressionContract.from_dict(_data(case))
    case["raises"]["message"] = "changed input"
    assert contract.resolved_dict()["scenarios"][0]["raises"]["message"] == ""
    exported = contract.to_dict()
    exported["scenarios"][0]["raises"]["message"] = "changed export"
    assert contract.to_dict()["scenarios"][0]["raises"]["message"] == ""


@pytest.mark.parametrize(
    "expectation",
    [
        None,
        {},
        {"type": "ValueError", "message": "x"},
        {"type": "ValueError", "message": "x", "node": "n", "extra": True},
        {"type": [], "message": "x", "node": "n"},
        {"type": "Exception", "message": "x", "node": "n"},
        {"type": "SystemExit", "message": "x", "node": "n"},
        {"type": "module.CustomError", "message": "x", "node": "n"},
        {"type": "ValueError", "message": 1, "node": "n"},
        {"type": "ValueError", "message": "é" * 2049, "node": "n"},
        {"type": "ValueError", "message": "x", "node": None},
        {"type": "ValueError", "message": "x", "node": ""},
    ],
)
def test_invalid_exception_declarations_are_rejected(expectation: object) -> None:
    case = _case()
    case["raises"] = expectation
    with pytest.raises(WorkflowRegressionError, match="Exception expectations"):
        WorkflowRegressionContract.from_dict(_data(case))


def test_utf8_message_boundary_and_feature_gate() -> None:
    case = _case()
    case["raises"]["message"] = "é" * 2048
    WorkflowRegressionContract.from_dict(_data(case))
    with pytest.raises(WorkflowRegressionError, match="Exception expectations"):
        validate_outcome(case, pipeline=True, exceptions=False)


@pytest.mark.parametrize("both", [False, True])
@pytest.mark.parametrize("node", [False, True])
def test_exactly_one_outcome_is_required(*, both: bool, node: bool) -> None:
    case = _case()
    outcome = {"inputs": {}, "expected": 1} if node else case
    if both:
        outcome.update(expected=1, raises={"type": "ValueError", "message": "x"})
    else:
        outcome.pop("expected" if node else "raises")
    if node:
        case["nodes"] = {"step_0000_clean_values": outcome}
    with pytest.raises(WorkflowRegressionError, match="exactly one"):
        WorkflowRegressionContract.from_dict(_data(case))


def test_node_expectations_cannot_declare_a_second_owner() -> None:
    case = _case()
    case["nodes"] = {"step_0000_clean_values": {"inputs": {}, "raises": case["raises"]}}
    with pytest.raises(WorkflowRegressionError, match="Exception expectations"):
        WorkflowRegressionContract.from_dict(_data(case))


@pytest.mark.parametrize(
    "changes",
    [
        {"storage": None},
        {"storage": "unknown"},
        {"storage": "fixtures"},
        {"extra": 1},
        {"schema_version": "1.0"},
        {"schema_version": "1.1"},
    ],
)
def test_storage_and_version_must_be_explicit(changes: dict[str, Any]) -> None:
    with pytest.raises(WorkflowRegressionError):
        WorkflowRegressionContract.from_dict({**_data(_case()), **changes})
    data = _data(_case())
    data.pop("storage")
    with pytest.raises(WorkflowRegressionError):
        WorkflowRegressionContract.from_dict(data)


@pytest.mark.parametrize("version", ["1.0", "1.1"])
def test_old_formats_do_not_accept_raises(version: str) -> None:
    data = {"schema_version": version, "scenarios": [_case()]}
    with pytest.raises(WorkflowRegressionError):
        WorkflowRegressionContract.from_dict(data)


def test_exception_owner_is_bound_to_unprefixed_plan_step() -> None:
    plan = plan_functional_workflow_path(
        EXAMPLE / "workflow.py",
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
    )
    case = _case()
    validate_regression_binding(WorkflowRegressionContract.from_dict(_data(case)), plan)
    case["raises"]["node"] = "ml_step_0000_clean_values"
    with pytest.raises(WorkflowRegressionError, match="known unprefixed node"):
        validate_regression_binding(WorkflowRegressionContract.from_dict(_data(case)), plan)


def test_fixture_exception_snapshot_and_hash_checks(tmp_path: Path) -> None:
    case = _case()
    content = json.dumps(case, ensure_ascii=False).encode()
    fixture = tmp_path / "case.json"
    fixture.write_bytes(content)
    data = {
        "schema_version": "1.2",
        "storage": "fixtures",
        "scenarios": [{"path": "case.json", "sha256": hashlib.sha256(content).hexdigest()}],
    }
    manifest = tmp_path / "regression.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    contract = load_workflow_regression_contract(manifest)
    assert contract.to_dict() == data
    assert contract.resolved_dict() == _data(case)
    fixture.write_text("{}", encoding="utf-8")
    assert contract.resolved_dict() == _data(case)
    with pytest.raises(WorkflowRegressionError, match="SHA-256"):
        load_workflow_regression_contract(manifest)


@pytest.mark.parametrize("fixtures", [False, True])
def test_generation_delivers_explicit_outcomes_without_running_application_code(
    tmp_path: Path, *, fixtures: bool
) -> None:
    data = load_workflow_regression_contract(EXAMPLE / "regression-exceptions.json").to_dict()
    failure = data["scenarios"][-1]
    failure["nodes"] = {
        "step_0000_clean_values": {
            "inputs": {"raw_values": [None], "missing_policy": "error"},
            "raises": {"type": "ValueError", "message": "Missing observation"},
        }
    }
    captures: tuple[str, ...] = ()
    if fixtures:
        captures = tuple(json.dumps(case) for case in data["scenarios"])
        declaration = {
            "schema_version": "1.2",
            "storage": "fixtures",
            "scenarios": [
                {"path": f"case_{i}.json", "sha256": hashlib.sha256(text.encode()).hexdigest()}
                for i, text in enumerate(captures)
            ],
        }
    else:
        declaration = data
    contract = WorkflowRegressionContract.from_dict(declaration, fixture_jsons=captures)
    project = tmp_path / "project"
    generate_functional_kedro_project(
        EXAMPLE / "workflow.py",
        load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
        project,
        project_root=EXAMPLE.parents[1],
        regression_contract=contract,
    )
    module = (project / "tests/test_workflow_regressions.py").read_text(encoding="utf-8")
    tree = ast.parse(module)
    functions = {
        node.name: ast.unparse(node) for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert (
        "_check_pipeline(pipeline, catalog, scenario, monkeypatch)"
        in functions["test_pipeline_scenario"]
    )
    assert (
        "assert type(error) is _EXCEPTION_TYPES[expectation['type']]"
        in functions["_assert_exception"]
    )
    assert "notebook_to_kedro" not in module
    metadata = json.loads((project / "tests/regression_cases.json").read_text())
    emitted = metadata["contract"]
    assert emitted["schema_version"] == "1.2"
    assert emitted["storage"] == ("fixtures" if fixtures else "inline")
    if fixtures:
        for reference, source in zip(emitted["scenarios"], captures, strict=True):
            assert (project / "tests" / reference["path"]).read_bytes() == source.encode()
        assert "contract.get('storage') != 'fixtures'" in functions["_fixture_cases"]
    else:
        assert emitted == data
    report = json.loads((project / "regression-coverage.json").read_text())
    assert report["pipeline_scenarios"] == 5
    assert report["pipeline_exception_scenarios"] == 2
    assert report["node_exception_scenarios"] == {
        "step_0000_clean_values": 1,
        "step_0001_winsorize": 0,
        "step_0002_summarize": 0,
    }
    assert report["execution_status"] == "not_run"
    assert report["review_status"] == "not_authenticated"
    assert "declared node function" in (project / "TESTING.md").read_text()
