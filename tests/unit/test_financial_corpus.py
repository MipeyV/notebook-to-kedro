"""Deterministic synthetic records and static conversion boundaries; no model execution."""

from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import nbformat
import pytest

from notebook_to_kedro import (
    PlanningResult,
    PlanRequest,
    analyze_notebook_path,
    audit_conversion_source,
    generate_kedro_project,
    load_local_project_configuration,
    load_notebook_regression_contract,
    plan_notebook_path,
    run_local_operation,
)
from notebook_to_kedro.exceptions import ProjectGenerationError
from notebook_to_kedro.generation.writer import write_project

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "examples/banking_insurance"
CASES = ("credit_default", "insurance_lapse")


@pytest.fixture(scope="module")
def builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "financial_case_builder", ROOT / "tools/build_financial_examples.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generated(builder: ModuleType) -> dict[Path, str]:
    files: dict[Path, str] = builder.build_files()
    return files


def test_committed_artifacts_exactly_match_the_deterministic_generator(
    generated: dict[Path, str],
) -> None:
    assert len(generated) == 27
    for relative, content in generated.items():
        assert (EXAMPLES / relative).read_bytes() == content.encode("utf-8"), relative


def test_same_seed_is_repeatable_and_another_seed_changes_records(
    builder: ModuleType, generated: dict[Path, str]
) -> None:
    assert builder.build_files(42) == generated
    alternate = builder.build_files(43)
    for case in CASES:
        path = Path(case) / "data/portfolio.csv"
        assert alternate[path] != generated[path]
        assert len(list(csv.DictReader(io.StringIO(alternate[path])))) == len(
            list(csv.DictReader(io.StringIO(generated[path])))
        )


@pytest.mark.parametrize("seed", [-1, 2**32, True, 1.5, "42", None])
def test_invalid_seeds_are_rejected_without_writes(builder: ModuleType, seed: Any) -> None:
    with pytest.raises(ValueError, match="unsigned 32-bit"):
        builder.build_files(seed)


@pytest.mark.parametrize("case", CASES)
def test_data_roles_dates_counts_missingness_and_drift_are_explicit(case: str) -> None:
    root = EXAMPLES / case
    raw = (root / "data/portfolio.csv").read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    dictionary = json.loads((root / "dictionary.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(raw).hexdigest() == manifest["portfolio_sha256"]
    assert len(raw) < 1024 * 1024
    assert len(rows) == manifest["rows"]
    assert sum(int(row[manifest["target"]]) for row in rows) == manifest["positive_rows"]
    assert set(dictionary["columns"]) == set(manifest["feature_columns"])
    assert not set(dictionary["excluded_columns"]) & set(manifest["feature_columns"])
    assert set(rows[0]) == set(dictionary["columns"]) | set(dictionary["excluded_columns"])
    identifier = "loan_id" if case == "credit_default" else "policy_id"
    assert len({row[identifier] for row in rows}) == len(rows)
    assert all(row[identifier].startswith("SYN-") for row in rows)
    assert "probability" not in " ".join(rows[0])
    for column in manifest["feature_columns"]:
        missing = sum(row[column] == "" for row in rows)
        assert missing == manifest["missing_values"][column]
        assert 0 < missing < len(rows) // 10
        assert dictionary["columns"][column]["as_of_snapshot"] is True
        assert dictionary["columns"][column]["description"]
    drift = manifest["new_test_category"]
    assert any(row[drift["column"]] == drift["value"] for row in rows)
    assert all(
        int(row["snapshot_month"]) >= 202401
        for row in rows
        if row[drift["column"]] == drift["value"]
    )
    for row in rows:
        snapshot = int(row["snapshot_month"])
        assert int(row["outcome_end_month"]) == snapshot + 100
        assert int(row["outcome_end_month"]) < manifest["observation_cutoff_month"]
        assert row["followup_months"] == "12"
        if row[manifest["target"]] == "1":
            assert snapshot < int(row["event_month"]) <= int(row["outcome_end_month"])
        else:
            assert row["event_month"] == ""
    train = [row for row in rows if int(row["snapshot_month"]) < 202101]
    validation = [row for row in rows if 202201 <= int(row["snapshot_month"]) <= 202212]
    test = [row for row in rows if 202401 <= int(row["snapshot_month"]) <= 202412]
    assert max(int(row["outcome_end_month"]) for row in train) < min(
        int(row["snapshot_month"]) for row in validation
    )
    assert max(int(row["outcome_end_month"]) for row in validation) < min(
        int(row["snapshot_month"]) for row in test
    )
    assert [len(train), len(validation), len(test)] == [
        manifest["counts"][name] for name in ("train_rows", "validation_rows", "test_rows")
    ]
    assert (
        len(rows) - len(train) - len(validation) - len(test) == manifest["counts"]["embargo_rows"]
    )


def _source(path: Path) -> str:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    nbformat.validate(notebook)
    return "\n".join(
        "".join(cell["source"]) if isinstance(cell["source"], list) else str(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )


@pytest.mark.parametrize("case", CASES)
def test_working_notebook_is_fully_accounted_and_previewed_without_execution(case: str) -> None:
    root = EXAMPLES / case
    source = root / "workflow.ipynb"
    tree = ast.parse(_source(source))
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for node in ast.walk(tree)
    )
    plan = plan_notebook_path(source)
    assert not plan.blocking_diagnostic_codes
    assert len(plan.task_candidates) == 10
    assert len(plan.parameters) == 2
    assert audit_conversion_source(analyze_notebook_path(source), plan).complete
    result = run_local_operation(
        PlanRequest(load_local_project_configuration(root / "project.json"))
    )
    assert isinstance(result, PlanningResult)
    data = result.to_dict()
    assert data["execution_status"] == "not_run"
    assert any(item.path == "tests/test_notebook_regressions.py" for item in result.files)
    contract = load_notebook_regression_contract(root / "regression.json")
    scenarios = contract.to_dict()["scenarios"]
    assert len(scenarios) == 5
    assert sum(len(case.get("nodes", {})) for case in scenarios) == 5
    assert set(scenarios[0]["expected"]) == {"cohort_counts", "feature_names"}


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize(
    ("name", "code"),
    [("boundary_assertions.ipynb", "SA002"), ("boundary_catalog_reuse.ipynb", "SA008")],
)
def test_original_boundaries_still_block_publication(
    tmp_path: Path, case: str, name: str, code: str
) -> None:
    source = EXAMPLES / case / name
    plan = plan_notebook_path(source)
    assert set(plan.blocking_diagnostic_codes) == {code}
    output = tmp_path / "blocked"
    with pytest.raises(ProjectGenerationError):
        generate_kedro_project(plan, output, source_facts=analyze_notebook_path(source))
    assert not output.exists()
    if code == "SA002":
        assert ast.dump(ast.parse(_source(source))) == ast.dump(
            ast.parse(_source(source.parent / "workflow.ipynb"))
        )


def test_shared_writer_keeps_existing_destinations_untouched(
    tmp_path: Path, generated: dict[Path, str]
) -> None:
    destination = tmp_path / "cases"
    write_project(destination, generated)
    before = {relative: (destination / relative).read_bytes() for relative in generated}
    with pytest.raises(ProjectGenerationError):
        write_project(destination, generated)
    assert {relative: (destination / relative).read_bytes() for relative in generated} == before


def test_measured_snapshot_is_bound_to_source_data_and_expectations() -> None:
    report = json.loads((EXAMPLES / "observations.json").read_text(encoding="utf-8"))
    assert len(report["cases"]) == 2
    for case in report["cases"]:
        root = EXAMPLES / case["case"]
        for key, relative in (
            ("source_sha256", "workflow.ipynb"),
            ("portfolio_sha256", "data/portfolio.csv"),
            ("regression_sha256", "regression.json"),
        ):
            assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == case[key]
        assert case["status"] == "matched"
        assert {(run["profile"], run["runner"]) for run in case["runs"]} == {
            ("default", "SequentialRunner"),
            ("custom", "SequentialRunner"),
            ("default", "ThreadRunner"),
            ("custom", "ThreadRunner"),
        }
        assert all(run["nodes"] == 10 and run["status"] == "matched" for run in case["runs"])
