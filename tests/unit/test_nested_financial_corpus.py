"""Nested examples preserve source/data identity and expose unverified model outputs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from notebook_to_kedro import (
    PlanningResult,
    PlanRequest,
    analyze_notebook_path,
    audit_conversion_source,
    load_local_project_configuration,
    plan_notebook_path,
    run_local_operation,
)
from notebook_to_kedro.exceptions import ProjectGenerationError
from notebook_to_kedro.generation.writer import write_project

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "examples/nested_financial"
CASES = ("credit_pipeline", "lapse_calibrated_vote")


@pytest.fixture(scope="module")
def builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "nested_financial_builder", ROOT / "tools/build_nested_financial_examples.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_authored_assets_are_reproducible_and_existing_targets_are_protected(
    builder: ModuleType, tmp_path: Path
) -> None:
    files = builder.build_files()
    for relative, content in files.items():
        assert (EXAMPLES / relative).read_bytes() == content.encode("utf-8"), relative
    target = tmp_path / "cases"
    write_project(target, files)
    with pytest.raises(ProjectGenerationError):
        write_project(target, files)
    assert all(
        (target / relative).read_bytes() == value.encode() for relative, value in files.items()
    )


def test_baseline_data_drift_is_rejected_before_publication(
    builder: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / "credit_default"
    (baseline / "data").mkdir(parents=True)
    (baseline / "manifest.json").write_bytes(
        (ROOT / "examples/banking_insurance/credit_default/manifest.json").read_bytes()
    )
    (baseline / "data/portfolio.csv").write_text("changed\n", encoding="utf-8")
    monkeypatch.setattr(builder, "BASE", tmp_path)
    with pytest.raises(ValueError, match="Base portfolio identity differs"):
        builder.build_files()


@pytest.mark.parametrize("case", CASES)
def test_nested_cases_reuse_all_original_records_and_dictionary(case: str) -> None:
    root = EXAMPLES / case
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    original = ROOT / "examples/banking_insurance" / manifest["base_case"]
    for path in [*root.glob("data/*.csv"), root / "dictionary.json"]:
        assert path.read_bytes() == (original / path.relative_to(root)).read_bytes()


@pytest.mark.parametrize("case", CASES)
def test_static_preview_keeps_nested_models_memory_only_and_without_an_oracle(case: str) -> None:
    root = EXAMPLES / case
    source = root / "workflow.ipynb"
    plan = plan_notebook_path(source)
    assert len(plan.task_candidates) == 9
    assert len(plan.parameters) == (0 if case == "credit_pipeline" else 2)
    assert audit_conversion_source(analyze_notebook_path(source), plan).complete
    preview = run_local_operation(
        PlanRequest(load_local_project_configuration(root / "project.json"))
    )
    assert isinstance(preview, PlanningResult)
    assert preview.to_dict()["execution_status"] == "not_run"
    report = json.loads(
        next(file.content for file in preview.files if file.path == "regression-coverage.json")
    )
    assert "fitted_model" in report["missing_pipeline_outputs"]
    assert report["pipeline_scenarios"] == report["node_scenarios"] == 5
    assert report["review_status"] == "not_authenticated"


@pytest.mark.parametrize(
    ("case", "filename"),
    [
        ("credit_pipeline", "boundary_fitted_alias.ipynb"),
        ("lapse_calibrated_vote", "boundary_stacking_timeseries.ipynb"),
    ],
)
def test_runtime_boundaries_are_statically_complete(case: str, filename: str) -> None:
    source = EXAMPLES / case / filename
    plan = plan_notebook_path(source)
    assert not plan.blocking_diagnostic_codes
    assert audit_conversion_source(analyze_notebook_path(source), plan).complete


def test_measurements_bind_working_and_failing_source_variants() -> None:
    report = json.loads((EXAMPLES / "observations.json").read_text(encoding="utf-8"))
    for case in report["cases"]:
        root = EXAMPLES / case["case"]
        for key, relative in (
            ("source_sha256", "workflow.ipynb"),
            ("portfolio_sha256", "data/portfolio.csv"),
            ("regression_sha256", "regression.json"),
        ):
            assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == case[key]
        assert {(run["profile"], run["runner"]) for run in case["runs"]} == {
            (profile, runner)
            for profile in ("default", "custom")
            for runner in ("SequentialRunner", "ThreadRunner")
        }
        assert all(run["nodes"] == 9 and run["status"] == "matched" for run in case["runs"])
    assert {item["status"] for item in report["boundaries"]} == {
        "alias_fidelity_gap",
        "preserved_source_failure",
    }
    for boundary in report["boundaries"]:
        path = EXAMPLES / boundary["case"] / boundary["filename"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == boundary["source_sha256"]
