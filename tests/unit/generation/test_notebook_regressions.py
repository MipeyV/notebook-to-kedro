"""Explicit notebook oracles, immutable fixtures and real standalone regression controls."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    NotebookRegressionContract,
    PlanningResult,
    PlanRequest,
    analyze_notebook_path,
    generate_kedro_project,
    load_local_project_configuration,
    load_notebook_regression_contract,
    plan_notebook_path,
    run_local_operation,
)
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import ProjectGenerationError, WorkflowRegressionError
from notebook_to_kedro.generation.kedro.generator import render_kedro_project
from notebook_to_kedro.generation.kedro.notebook_regression_contract import _definitions
from notebook_to_kedro.generation.kedro.profiles import KedroArchitectureProfile

ROOT = Path(__file__).parents[3]
EXAMPLE = ROOT / "examples/procedural_regression"


def _data() -> Any:
    return json.loads((EXAMPLE / "regression.json").read_text(encoding="utf-8"))


def _contract(data: Any = None) -> Any:
    return NotebookRegressionContract.from_dict(
        _data() if data is None else data,
        fixture_texts=tuple(
            (name, (EXAMPLE / "data" / f"{name}.csv").read_text(encoding="utf-8"))
            for name in ("training", "empty")
        ),
    )


def _render(contract: Any = None, profile: Any = None) -> Any:
    path = EXAMPLE / "workflow.ipynb"
    return render_kedro_project(
        plan_notebook_path(path),
        source_facts=analyze_notebook_path(path),
        regression_contract=_contract() if contract is None else contract,
        architecture_profile=profile,
    )[0]


def test_contract_immutable_roundtrip_and_empty_cases() -> None:
    contract = load_notebook_regression_contract(EXAMPLE / "regression.json")
    assert contract == _contract()
    assert contract.sha256 == hashlib.sha256(contract.canonical_json.encode()).hexdigest()
    data = contract.to_dict()
    data["scenarios"].clear()
    assert len(contract.to_dict()["scenarios"]) == 2
    empty = NotebookRegressionContract.from_dict(
        {"schema_version": "1.0", "fixtures": {}, "scenarios": []}
    )
    files = _render(empty)
    assert Path("tests/test_notebook_regressions.py") not in files
    assert "optional-dependencies" not in files[Path("pyproject.toml")]
    report = json.loads(files[Path("regression-coverage.json")])
    assert report["missing_pipeline_outputs"] == ["error", "predictions"]
    assert len(report["missing_node_expectations"]) == 3


def test_empty_notebook_graph_has_an_explicit_empty_gap_report(tmp_path: Path) -> None:
    notebook = json.loads((EXAMPLE / "workflow.ipynb").read_text(encoding="utf-8"))
    notebook["cells"] = []
    path = tmp_path / "empty.ipynb"
    path.write_text(json.dumps(notebook), encoding="utf-8")
    contract = NotebookRegressionContract.from_dict(
        {"schema_version": "1.0", "fixtures": {}, "scenarios": []}
    )
    files, _ = render_kedro_project(
        plan_notebook_path(path),
        source_facts=analyze_notebook_path(path),
        regression_contract=contract,
    )
    report = json.loads(files[Path("regression-coverage.json")])
    assert report["pipeline_scenarios"] == 0
    assert report["missing_node_expectations"] == []
    assert report["missing_pipeline_outputs"] == []
    assert Path("tests/test_notebook_regressions.py") not in files


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {"schema_version": "2.0", "fixtures": {}, "scenarios": []},
        {"schema_version": "1.0", "fixtures": [], "scenarios": []},
        {"schema_version": "1.0", "fixtures": {}, "scenarios": {}},
        {"schema_version": "1.0", "fixtures": {}, "scenarios": [{}] * 101},
        {"schema_version": "1.0", "fixtures": dict.fromkeys(map(str, range(101))), "scenarios": []},
    ],
)
def test_invalid_headers(data: Any) -> None:
    with pytest.raises(WorkflowRegressionError):
        NotebookRegressionContract.from_dict(data)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("path", "../training.csv"),
        ("path", "CON.csv"),
        ("path", 2),
        ("path", "data/training.json"),
        ("sha256", "A" * 64),
        ("sha256", 1),
    ],
)
def test_bad_fixture_declarations(key: Any, value: Any) -> None:
    data = _data()
    data["fixtures"]["training"][key] = value
    with pytest.raises(WorkflowRegressionError):
        _contract(data)


def test_bad_fixture_identifiers_duplicates_and_fields() -> None:
    invalid: Any
    data = _data()
    data["fixtures"]["1bad"] = data["fixtures"].pop("training")
    with pytest.raises(WorkflowRegressionError):
        _contract(data)
    data = _data()
    data["fixtures"]["empty"]["path"] = "DATA/TRAINING.csv"
    with pytest.raises(WorkflowRegressionError):
        _contract(data)
    for invalid in ([], {"path": "training.csv"}):
        data = _data()
        data["fixtures"]["training"] = invalid
        with pytest.raises(WorkflowRegressionError):
            _contract(data)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("id", "BAD"),
        ("inputs", []),
        ("parameters", []),
        ("nodes", []),
        ("extra", True),
        ("expected", {}),
        ("expected", []),
        ("inputs", {"df": []}),
        ("inputs", {"df": "undeclared"}),
        ("nodes", {"task-0000": []}),
        ("nodes", {"task-0000": {"inputs": {}}}),
        ("nodes", {"task-0000": {"inputs": [], "expected": {"x": {"kind": "json", "value": 1}}}}),
    ],
)
def test_invalid_scenarios(key: Any, value: Any) -> None:
    data = _data()
    data["scenarios"][0][key] = value
    with pytest.raises(WorkflowRegressionError):
        _contract(data)


def test_duplicate_scenarios_unused_fixtures_and_bad_case() -> None:
    case: Any
    for case in (None, {"inputs": {}}):
        data = _data()
        data["scenarios"][0] = case
        with pytest.raises(WorkflowRegressionError):
            _contract(data)
    data = _data()
    data["scenarios"][1]["id"] = "baseline"
    with pytest.raises(WorkflowRegressionError):
        _contract(data)
    data = _data()
    data["scenarios"].pop()
    with pytest.raises(WorkflowRegressionError, match="Every declared"):
        _contract(data)


@pytest.mark.parametrize(
    "captures",
    [[], ([],), (("training",),), ((1, "text"),), (), (("training", "text"), ("training", "text"))],
)
def test_invalid_captures(captures: Any) -> None:
    with pytest.raises(WorkflowRegressionError):
        NotebookRegressionContract(json.dumps(_data()), captures)


def test_capture_hash_budget_and_encoding_errors() -> None:
    source: Any
    contract = _contract()
    with pytest.raises(WorkflowRegressionError, match="SHA-256"):
        replace(contract, fixture_texts=(("training", "wrong"), ("empty", "x,y\n")))
    with pytest.raises(WorkflowRegressionError, match="budget"):
        replace(contract, fixture_texts=(("training", "x" * (1024 * 1024 + 1)), ("empty", "")))
    with pytest.raises(WorkflowRegressionError, match="decode"):
        replace(contract, fixture_texts=(("training", "\ud800"), ("empty", "")))
    for source in (12, " " * 65537, '{"x": 1, "x": 2}', "{", '"\\ud800"'):
        with pytest.raises(WorkflowRegressionError):
            NotebookRegressionContract(source)


def test_total_capture_budget() -> None:
    text = "x" * (1024 * 1024)
    definitions = {
        f"f{i}": {"path": f"f{i}.csv", "sha256": hashlib.sha256(text.encode()).hexdigest()}
        for i in range(9)
    }
    data = {
        "schema_version": "1.0",
        "fixtures": definitions,
        "scenarios": [
            {
                "id": "large",
                "inputs": {name: name for name in definitions},
                "parameters": {},
                "expected": {"result": {"kind": "json", "value": 1}},
            }
        ],
    }
    with pytest.raises(WorkflowRegressionError, match="budget"):
        NotebookRegressionContract.from_dict(
            data, fixture_texts=tuple((name, text) for name in definitions)
        )


def test_loading_errors_and_validation_precedes_fixture_reads(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    for raw in (b"x" * 65537, b"\xff", b"{", b'{"schema_version":"1.0"}'):
        path.write_bytes(raw)
        with pytest.raises(WorkflowRegressionError):
            load_notebook_regression_contract(path)
    path.write_text(json.dumps(_data()), encoding="utf-8")
    with pytest.raises(WorkflowRegressionError, match="Cannot read"):
        load_notebook_regression_contract(path)
    data = _data()
    data["scenarios"][0]["expected"] = {}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(WorkflowRegressionError, match="Expectations"):
        load_notebook_regression_contract(path)
    assert _definitions({"schema_version": "1.0", "fixtures": {}, "scenarios": []})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("inputs", {}),
        ("parameters", {"extra": 1}),
        ("expected", {"model": {"kind": "json", "value": 1}}),
        ("nodes", {"unknown": {"inputs": {}, "raises": {"type": "ValueError", "message": "x"}}}),
        ("nodes", {"task-0000": {"inputs": {}, "raises": {"type": "ValueError", "message": "x"}}}),
        (
            "nodes",
            {
                "task-0000": {
                    "inputs": {"df": {"kind": "csv", "fixture": "training"}},
                    "expected": {"X": {"kind": "json", "value": []}},
                }
            },
        ),
    ],
)
def test_binding_rejects_drift(field: Any, value: Any) -> None:
    data = _data()
    data["scenarios"][0][field] = value
    with pytest.raises(WorkflowRegressionError):
        _render(_contract(data))


def test_facts_required_unknown_error_node_and_default_compatibility() -> None:
    path = EXAMPLE / "workflow.ipynb"
    plan = plan_notebook_path(path)
    with pytest.raises(ProjectGenerationError, match="source facts"):
        render_kedro_project(plan, regression_contract=_contract())
    data = _data()
    data["scenarios"][1]["raises"]["node"] = "unknown"
    with pytest.raises(WorkflowRegressionError, match="task ID"):
        _render(_contract(data))
    normal, _ = render_kedro_project(plan)
    assert normal == render_kedro_project(plan, regression_contract=None)[0]
    assert Path("TESTING.md") not in normal


def test_report_preserves_negative_only_gaps() -> None:
    files = _render()
    report = json.loads(files[Path("regression-coverage.json")])
    assert report["execution_status"] == "not_run"
    assert report["review_status"] == "not_authenticated"
    assert report["node_scenarios"] == 3
    assert report["node_exception_scenarios"] == 2
    assert report["missing_node_expectations"] == ["task-0002"]
    assert report["missing_node_positive_expectations"] == ["task-0001", "task-0002"]
    assert report["missing_pipeline_outputs"] == []


def _generate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: Any = None) -> Any:
    workspace = tmp_path / "workspace"
    shutil.copytree(EXAMPLE, workspace)
    monkeypatch.chdir(workspace)
    path = workspace / "workflow.ipynb"
    project = workspace / "project"
    generate_kedro_project(
        plan_notebook_path(path),
        project,
        package_name="procedural_tests",
        source_facts=analyze_notebook_path(path),
        architecture_profile=profile,
        regression_contract=_contract(),
    )
    return project


def _pytest(project: Any, tmp_path: Path) -> Any:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--basetemp=" + str(tmp_path / "runtime")],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


@pytest.mark.parametrize("custom", [False, True])
def test_standalone_suite_passes_then_detects_business_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, custom: Any
) -> None:
    profile = (
        KedroArchitectureProfile.from_dict(
            {
                "schema_version": "1.0",
                "profile_id": "tests",
                "profile_version": "1.0.0",
                "pipeline_name": "training",
                "node_name_prefix": "ml_",
            }
        )
        if custom
        else None
    )
    project = _generate(tmp_path, monkeypatch, profile)
    outcome = _pytest(project, tmp_path)
    assert outcome.returncode == 0, outcome.stdout + outcome.stderr
    assert "5 passed" in outcome.stdout
    pipeline = "training" if custom else "notebook_pipeline"
    source = project / "src/procedural_tests/pipelines" / pipeline / "nodes.py"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "predictions = model.predict(X)", "predictions = model.predict(X) + 1  # mutation"
        ),
        encoding="utf-8",
    )
    outcome = _pytest(project, tmp_path)
    assert outcome.returncode != 0
    assert "1 failed, 4 passed" in outcome.stdout


def _module(project: Any) -> Any:
    path = project / "tests/test_notebook_regressions.py"
    spec = importlib.util.spec_from_file_location("standalone_procedural_checks", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_and_catalog_tampering_cannot_satisfy_expected_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _generate(tmp_path, monkeypatch)
    module = _module(project)
    catalog = project / "conf/base/catalog.yml"
    catalog.write_text(
        "df:\n  type: json.JSONDataset\n  filepath: /outside.json\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="catalog"):
        module.test_pipeline(module.CASES[1], tmp_path, monkeypatch)
    fixture = next((project / "tests/regression_fixtures").iterdir())
    fixture.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        _module(project)


def test_cli_and_local_preview_share_tests_without_executing_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(EXAMPLE, workspace)
    monkeypatch.chdir(workspace)
    config = load_local_project_configuration(workspace / "project.json")
    result = run_local_operation(PlanRequest(config))
    assert isinstance(result, PlanningResult)
    assert any(item.path == "tests/test_notebook_regressions.py" for item in result.files)
    assert not (workspace / "project").exists()
    assert (
        main(
            [
                "generate",
                str(workspace / "workflow.ipynb"),
                str(workspace / "project"),
                "--regression-contract",
                str(workspace / "regression.json"),
            ]
        )
        == 0
    )
    assert (workspace / "project/tests/test_notebook_regressions.py").is_file()


def test_standalone_typed_materialization_and_comparators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _generate(tmp_path, monkeypatch)
    module = _module(project)
    values = [
        {"kind": "json", "value": {"x": [1, True, None]}},
        {"kind": "array", "dtype": "int64", "data": [[1, 2], [3, 4]]},
        {
            "kind": "frame",
            "columns": ["x", "y"],
            "dtypes": ["int64", "float64"],
            "index": ["a", "b"],
            "index_name": "row",
            "column_name": "feature",
            "data": [[1, 1.5], [2, 2.5]],
        },
        {
            "kind": "frame",
            "columns": [],
            "dtypes": [],
            "index": [1, 2],
            "index_name": None,
            "column_name": None,
            "data": [[], []],
        },
        {
            "kind": "series",
            "dtype": "int64",
            "data": [1, 2],
            "index": ["a", "b"],
            "index_name": "row",
            "name": "target",
        },
    ]
    for descriptor in values:
        actual = module._materialize(descriptor)
        module._observe(actual, descriptor)
    module._observe(1.01, {"kind": "number", "value": 1, "abs_tol": 0.02, "rel_tol": 0})
    for actual in (True, float("nan"), 2):
        with pytest.raises(AssertionError):
            module._observe(actual, {"kind": "number", "value": 1, "abs_tol": 0, "rel_tol": 0})
    for descriptor in values[:2]:
        with pytest.raises(AssertionError):
            module._observe(actual=False, expected=descriptor)
    array = importlib.import_module("numpy").array([1, 2], dtype="int32")
    with pytest.raises(AssertionError):
        module._observe(array, {"kind": "array", "dtype": "int64", "data": [1, 2]})
    with pytest.raises(AssertionError):
        module._exception(ValueError("literal.*"), {"type": "ValueError", "message": "literal"})
    with pytest.raises(AssertionError):
        module._exception(KeyError("x"), {"type": "ValueError", "message": "x"})


def test_observation_catalog_preserves_kedro_default_copy_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _generate(tmp_path, monkeypatch)
    module = _module(project)
    catalog = module._catalog(module.CASES[0], tmp_path, monkeypatch)
    array = importlib.import_module("numpy").array([1.0, 2.0])
    catalog.save("predictions", array)
    first = catalog.load("predictions")
    second = catalog.load("predictions")
    assert first is not second
    first[0] = 99
    assert catalog.load("predictions").tolist() == [1.0, 2.0]


def test_generated_fixture_paths_and_regular_files_are_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _generate(tmp_path, monkeypatch)
    module = _module(project)
    definition = module.DATA["contract"]["fixtures"]["training"]
    original = definition["path"]
    definition["path"] = "../outside.csv"
    with pytest.raises(ValueError, match="path"):
        module._fixtures()
    definition["path"] = original
    path = project / "tests" / original
    path.unlink()
    path.mkdir()
    with pytest.raises(ValueError, match="regular files"):
        module._fixtures()


def test_wrong_failure_node_and_node_setup_error_cannot_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _generate(tmp_path, monkeypatch)
    monkeypatch.syspath_prepend(str(project / "src"))
    module = _module(project)
    case = module.CASES[1]
    case["raises"]["node"] = "task-0001"
    with pytest.raises(AssertionError):
        module.test_pipeline(case, tmp_path, monkeypatch)
    node = module.CASES[0]["nodes"]["task-0001"]
    node["inputs"]["X"]["data"] = [["cannot-convert"]]
    node["inputs"]["X"]["index"] = [0]
    node["raises"] = {"type": "ValueError", "message": "unrelated business expectation"}
    with pytest.raises(ValueError, match="cannot-convert"):
        module.test_node("task-0001", node)
    # Do not let generated package imports leak into other tests or generated projects.
    for name in list(sys.modules):
        if name == "procedural_tests" or name.startswith("procedural_tests."):
            sys.modules.pop(name)


def test_no_csv_pipeline_uses_explicit_parameter_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebook = json.loads((EXAMPLE / "workflow.ipynb").read_text(encoding="utf-8"))
    notebook["cells"] = notebook["cells"][:2]
    notebook["cells"][0]["source"] = (
        "from sklearn.model_selection import train_test_split\nvalues = [1, 2, 3, 4]"
    )
    notebook["cells"][1]["source"] = (
        "left, right = train_test_split(values, test_size=0.5, random_state=42, shuffle=False)"
    )
    path = tmp_path / "workflow.ipynb"
    path.write_text(json.dumps(notebook), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    plan = plan_notebook_path(path)
    parameters = {p.name: 0.25 if p.name.endswith("test_size") else 42 for p in plan.parameters}
    assert len(parameters) == 2
    contract = NotebookRegressionContract.from_dict(
        {
            "schema_version": "1.0",
            "fixtures": {},
            "scenarios": [
                {
                    "id": "override",
                    "inputs": {},
                    "parameters": parameters,
                    "expected": {
                        "left": {"kind": "json", "value": [1, 2, 3]},
                        "right": {"kind": "json", "value": [4]},
                    },
                }
            ],
        }
    )
    project = tmp_path / "project"
    generate_kedro_project(
        plan, project, source_facts=analyze_notebook_path(path), regression_contract=contract
    )
    outcome = _pytest(project, tmp_path)
    assert outcome.returncode == 0, outcome.stdout + outcome.stderr
    assert "1 passed" in outcome.stdout
