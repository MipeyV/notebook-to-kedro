"""Offline checks for fixed-case preparation, publication and honest journey evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).parents[2]


@pytest.fixture
def journey() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "financial_journey", ROOT / "tools/check_financial_journey.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("case", ["credit_pipeline", "lapse_calibrated_vote"])
@pytest.mark.parametrize("custom", [False, True])
def test_prepared_settings_use_shared_operations_and_preserve_original_assets(
    journey: ModuleType, tmp_path: Path, case: str, *, custom: bool
) -> None:
    capture = tmp_path / "capture"
    capture.mkdir()
    (capture / "probe.csv").write_text("x\n1.0\n", encoding="utf-8")
    reference = {
        "oracle_basis": "captured_original_source",
        "independent_scientific_oracle": False,
        "model_checks": [
            {
                "id": "reload-predict",
                "scenario": "baseline",
                "method": "predict",
                "input": {"kind": "csv", "fixture": "model-probe"},
                "expected": {"kind": "array", "dtype": "int64", "data": [0]},
                "abs_tol": 0,
                "rel_tol": 0,
            }
        ],
    }
    source_before = journey._source_files(case)
    workspace = journey._prepare_workspace(tmp_path, case, reference, custom=custom)
    project = journey._convert(tmp_path, workspace, case)
    assert journey._source_files(case) == source_before
    assert all(
        (workspace / path).read_bytes() == text.encode() for path, text in source_before.items()
    )
    cases = json.loads((project / "tests/regression_cases.json").read_text(encoding="utf-8"))
    assert cases["contract"]["model_checks"] == reference["model_checks"]
    gaps = json.loads((project / "regression-coverage.json").read_text(encoding="utf-8"))
    assert gaps["model_reload_status"] == "not_run"
    assert "fitted_model" in gaps["missing_pipeline_outputs"]
    summary = json.loads(
        (tmp_path / "effort-comparison/measurement-summary.json").read_text(encoding="utf-8")
    )
    assert summary["human_effort"] is None
    assert summary["baseline"] is None
    assert len(summary["attempts"]) == 3
    assert summary["machine_timing_complete"] is True
    declaration = json.loads(
        (tmp_path / "effort-comparison/tool-effort.json").read_text(encoding="utf-8")
    )
    assert declaration["outcome"] == "in_progress"
    assert declaration["segments"] == []
    assert (project / "tests/_model_reload_worker.py").is_file()
    assert (project / "architecture-profile.json").is_file() is custom


@pytest.mark.parametrize("tamper", [None, "count", "message", "error", "skip", "wrong_test"])
def test_false_oracle_evidence_requires_both_actual_reload_failures(
    journey: ModuleType, tmp_path: Path, tamper: str | None
) -> None:
    cases = [
        '<testcase name="test_model_reload[reload-predict]">'
        '<failure message="Fresh model reload failed: mismatch"/></testcase>',
        '<testcase name="test_model_reload[reload-predict-proba]">'
        '<failure message="Fresh model reload failed: mismatch"/></testcase>',
    ]
    if tamper == "count":
        cases.pop()
    text = "<testsuites><testsuite>" + "".join(cases) + "</testsuite></testsuites>"
    replacements = {
        "message": ("Fresh model reload failed", "ImportError"),
        "error": ("<failure", "<error"),
        "skip": ("<failure", "<skipped"),
        "wrong_test": ("test_model_reload[reload-predict]", "test_unrelated"),
    }
    if tamper in replacements:
        text = text.replace(*replacements[tamper])
    report = tmp_path / "pytest.xml"
    report.write_text(text, encoding="utf-8")
    if tamper is None:
        journey._validate_negative_report(report)
    else:
        with pytest.raises(RuntimeError, match="both fresh reload"):
            journey._validate_negative_report(report)


def test_batch_failure_keeps_unattempted_cases_and_protects_existing_evidence(
    journey: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def fail(directory: Path, case: str, *, custom: bool) -> None:
        calls.append((directory, case, custom))
        raise RuntimeError("Simulated installation refusal")

    monkeypatch.setattr(journey, "check_case", fail)
    output = tmp_path / "journey"
    monkeypatch.setattr(sys, "argv", ["check", str(output)])
    with pytest.raises(RuntimeError, match="installation refusal"):
        journey.main()
    before = (output / "journey-summary.json").read_bytes()
    report = json.loads(before)
    assert [case["status"] for case in report["cases"]] == [
        "failed",
        "not_run",
        "not_run",
        "not_run",
    ]
    assert report["human_savings"] is None
    with pytest.raises(FileExistsError):
        journey.main()
    assert len(calls) == 1
    assert (output / "journey-summary.json").read_bytes() == before


def test_unknown_source_cannot_be_executed(journey: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Only the two committed"):
        journey.check_case(tmp_path / "blocked", "arbitrary-source", custom=False)
    assert not (tmp_path / "blocked").exists()


def test_source_capture_failure_is_retained_without_claiming_generation(
    journey: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrap = journey._bootstrap()

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Reference failed")

    monkeypatch.setattr(bootstrap, "_command", fail)
    monkeypatch.setattr(journey, "_bootstrap", lambda: bootstrap)
    directory = tmp_path / "case"
    with pytest.raises(RuntimeError, match="Reference failed"):
        journey.check_case(directory, "credit_pipeline", custom=False)
    evidence = json.loads((directory / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["status"] == "failed"
    assert evidence["human_savings"] is None
    assert evidence["error"]["message"] == "Reference failed"
    assert not (directory / "workspace/project").exists()
    assert not (directory / "venv").exists()


def test_observed_journeys_bind_unchanged_sources_and_preserve_oracle_gaps() -> None:
    root = ROOT / "examples/nested_financial"
    report = json.loads((root / "journey-observations.json").read_text(encoding="utf-8"))
    assert report["human_savings"] is None
    assert report["human_effort"] is None
    assert report["independent_scientific_oracle"] is False
    assert {(run["case"], run["profile"]) for run in report["runs"]} == {
        (case, profile)
        for case in ("credit_pipeline", "lapse_calibrated_vote")
        for profile in ("default", "custom")
    }
    for case, reference in report["references"].items():
        for key, relative in (
            ("source_sha256", "workflow.ipynb"),
            ("portfolio_sha256", "data/portfolio.csv"),
            ("original_regression_sha256", "regression.json"),
        ):
            assert (
                hashlib.sha256((root / case / relative).read_bytes()).hexdigest() == reference[key]
            )
        assert reference["oracle_basis"] == "captured_original_source"
        assert reference["probe_cohort"] == "validation"
        assert {check["method"] for check in reference["model_checks"]} == {
            "predict",
            "predict_proba",
        }
    for run in report["runs"]:
        assert run["status"] == "passed"
        assert run["passed_tests"] == 12
        assert run["false_oracle_control"] == "rejected_after_storage"
        assert "fitted_model" in run["missing_pipeline_outputs"]
        assert run["generation_execution_status"] == "not_run"
