"""Measured operations preserve behavior; declared effort never invents a time saving."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from notebook_to_kedro import (
    GenerateRequest,
    GenerationResult,
    InspectRequest,
    LocalProjectConfiguration,
    PlanningResult,
    PlanRequest,
    load_effort_declaration,
    measure_local_operation,
    run_local_operation,
    summarize_conversion_measurements,
)
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import LocalOperationError, ProjectGenerationError
from notebook_to_kedro.operations import measurements

ROOT = Path(__file__).parents[2]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    root = tmp_path / "project"
    shutil.copytree(ROOT / "examples/functional_workflow", root)
    workflow = load_effort_declaration(root / "workflow.json")
    workflow["inputs"] = {"values": "input.json"}
    _save(root / "workflow.json", workflow)
    config = LocalProjectConfiguration(
        root,
        Path("workflow.py"),
        "functional",
        workflow_configuration=Path("workflow.json"),
        regression_contract=Path("regression.json"),
    )
    directory = tmp_path / "measurements/attempt-01"
    ticks = iter((100, 2_000_000_100))
    monkeypatch.setattr(time, "perf_counter_ns", lambda: next(ticks))
    settings = tmp_path / "settings.json"
    _save(settings, {**config.to_dict(), "project_root": "project"})
    return SimpleNamespace(
        root=root, config=config, directory=directory, ledger=directory.parent, settings=settings
    )


def _save(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _record(workspace: SimpleNamespace) -> dict[str, Any]:
    measure_local_operation(
        InspectRequest(workspace.config), workspace.directory, case_id="example"
    )
    return summarize_conversion_measurements(workspace.ledger)


def _effort(summary: dict[str, Any], *, manual: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": "1.0",
        "case_id": summary["case_id"],
        "source_sha256": summary["source_sha256"] or "0" * 64,
        "acceptance_criteria": "Same declared outputs and standalone Kedro regression tests",
        "setup_mode": "reuse",
        "method": "manual" if manual else "tool",
        "basis": "measured",
        "outcome": "accepted",
        "operator": "Synthetic test declaration",
        "segments": [
            {"activity": "configuration", "seconds": 10},
            {"activity": "review", "seconds": 50 if manual else 10},
        ],
        "elapsed_seconds": 100 if manual else 30,
    }
    if not manual:
        data["attempts_sha256"] = summary["attempts_sha256"]
    return data


@pytest.mark.parametrize("operation", ["inspect", "plan", "generate"])
def test_timings_do_not_change_results_or_generated_project(
    workspace: SimpleNamespace, operation: str
) -> None:
    requests: dict[str, InspectRequest | PlanRequest | GenerateRequest] = {
        "inspect": InspectRequest(workspace.config),
        "plan": PlanRequest(workspace.config),
        "generate": GenerateRequest(workspace.config, Path("generated")),
    }
    reference = run_local_operation(PlanRequest(workspace.config))
    assert isinstance(reference, PlanningResult)
    result = measure_local_operation(requests[operation], workspace.directory, case_id="example")
    if operation == "generate":
        assert isinstance(result, GenerationResult)
        for item in reference.files:
            assert (workspace.root / "generated" / item.path).read_text() == item.content
    else:
        assert result.to_dict() == run_local_operation(requests[operation]).to_dict()
    summary = summarize_conversion_measurements(workspace.ledger)
    assert summary["machine_seconds_by_operation"][operation] == 2
    assert summary["known_machine_seconds"] == 2
    assert summary["machine_timing_complete"] is True
    assert summary["human_effort"] is None
    assert summary["comparison"]["status"] == "not_established"
    assert summary["comparison"]["human_saved_seconds"] is None
    assert (
        summary["source_sha256"] == hashlib.sha256(workspace.config.source.read_bytes()).hexdigest()
    )
    assert {path.name for path in workspace.directory.iterdir()} == {
        "reservation.json",
        "measurement.json",
    }
    assert "installation" in summary["not_automatically_measured"]
    with pytest.raises(ProjectGenerationError):
        measure_local_operation(requests[operation], workspace.directory, case_id="example")


@pytest.mark.parametrize("outcome", ["blocked", "failed", "interrupted", "unexpected"])
def test_failed_and_interrupted_attempts_remain_in_inventory(
    workspace: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    if outcome == "blocked":
        workspace.config.source.write_text(
            "def workflow(x):\n    if x:\n        return x\n    return 0\n"
        )
        result = measure_local_operation(
            InspectRequest(workspace.config), workspace.directory, case_id="example"
        )
        assert result.to_dict()["status"] == "blocked"
    else:
        if outcome == "failed":
            workspace.config.source.unlink()
            expected: type[BaseException] = LocalOperationError
        else:
            injected = KeyboardInterrupt if outcome == "interrupted" else RuntimeError
            expected = injected

            def fail(_: object) -> Any:
                raise injected("Synthetic interruption")

            monkeypatch.setattr(measurements, "run_local_operation", fail)
        with pytest.raises(expected):
            measure_local_operation(
                InspectRequest(workspace.config), workspace.directory, case_id="example"
            )
    summary = summarize_conversion_measurements(workspace.ledger)
    expected_status = "failed" if outcome == "unexpected" else outcome
    assert summary["attempts"][0]["observation"]["status"] == expected_status
    assert summary["known_machine_seconds"] == 2


@pytest.mark.parametrize("failure", [False, True])
def test_record_failure_never_overwrites_or_masks_original_error(
    workspace: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    *,
    failure: bool,
) -> None:
    reference = run_local_operation(InspectRequest(workspace.config))

    def operation(_: object) -> Any:
        (workspace.directory / "measurement.json").write_text("keep")
        if failure:
            raise RuntimeError("Original operation error")
        return reference

    monkeypatch.setattr(measurements, "run_local_operation", operation)
    with pytest.raises(RuntimeError if failure else LocalOperationError) as error:
        measure_local_operation(
            InspectRequest(workspace.config), workspace.directory, case_id="example"
        )
    assert (workspace.directory / "measurement.json").read_text() == "keep"
    if failure:
        assert str(error.value) == "Original operation error"
        assert error.value.__notes__
        assert "cannot publish measurement" in caplog.text
    else:
        assert "LM002" in str(error.value)


@pytest.mark.parametrize(
    "target", ["source", "settings", "generation", "generation-child", "package"]
)
def test_measurements_cannot_contaminate_protected_inputs_or_output(
    workspace: SimpleNamespace, target: str
) -> None:
    request = GenerateRequest(workspace.config, Path("generated"))
    paths = {
        "source": workspace.config.source,
        "settings": workspace.config.workflow_configuration,
        "generation": request.destination,
        "generation-child": request.destination / "measurement",
        "package": workspace.root / "measurements",
    }
    if target == "package":
        (workspace.root / "__init__.py").write_text("")
    with pytest.raises(LocalOperationError, match="overlaps"):
        measure_local_operation(request, paths[target], case_id="example")
    assert not request.destination.exists()


@pytest.mark.parametrize("case_id", ["", "with spaces", "X", "x" * 65, None])
def test_case_identifiers_are_validated_before_side_effects(
    workspace: SimpleNamespace, case_id: Any
) -> None:
    with pytest.raises(LocalOperationError, match="case_id"):
        measure_local_operation(
            InspectRequest(workspace.config), workspace.directory, case_id=case_id
        )
    assert not workspace.directory.exists()


def test_unsupported_request_is_rejected(workspace: SimpleNamespace) -> None:
    with pytest.raises(LocalOperationError, match="Unsupported"):
        measure_local_operation(None, workspace.directory, case_id="example")  # type: ignore[arg-type]


def test_nested_package_protection_stops_before_application_capture(
    workspace: SimpleNamespace,
) -> None:
    package = workspace.root / "src/example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    source = package / "workflow.py"
    shutil.copyfile(workspace.config.source, source)
    config = replace(workspace.config, source=source)
    with pytest.raises(LocalOperationError, match="overlaps"):
        measure_local_operation(InspectRequest(config), package / "new-report", case_id="example")
    assert not (package / "new-report").exists()


def test_declared_effort_and_elapsed_gain_are_distinct(workspace: SimpleNamespace) -> None:
    summary = _record(workspace)
    human, baseline = _effort(summary), _effort(summary, manual=True)
    report = summarize_conversion_measurements(workspace.ledger, effort=human, baseline=baseline)
    assert report["comparison"] == {
        "status": "operator_declared_measurement",
        "human_saved_seconds": 40,
        "human_saved_percent": 100 * 40 / 60,
        "elapsed_saved_seconds": 70,
    }
    assert report["human_effort"]["human_active_seconds"] == 20
    human["segments"][0]["seconds"] = 999
    assert report["human_effort"]["segments"][0]["seconds"] == 10
    human["segments"][0]["seconds"] = 10
    assert report["known_machine_seconds"] == 2
    assert human == _effort(summary)
    assert (
        summarize_conversion_measurements(workspace.ledger, effort=human)["comparison"]["status"]
        == "not_established"
    )
    assert (
        summarize_conversion_measurements(workspace.ledger, baseline=baseline)["human_effort"]
        is None
    )
    baseline["basis"] = "estimated"
    baseline["segments"] = []
    del baseline["elapsed_seconds"]
    report = summarize_conversion_measurements(workspace.ledger, effort=human, baseline=baseline)
    assert report["comparison"] == {
        "status": "operator_declared_estimate",
        "human_saved_seconds": -20,
        "human_saved_percent": None,
        "elapsed_saved_seconds": None,
    }


@pytest.mark.parametrize(
    "reason", ["in_progress", "unfinished", "changed_source", "source_mismatch"]
)
def test_incomplete_or_noncomparable_work_never_claims_savings(
    workspace: SimpleNamespace, reason: str
) -> None:
    summary = _record(workspace)
    human, baseline = _effort(summary), _effort(summary, manual=True)
    if reason == "in_progress":
        human["outcome"] = "in_progress"
    elif reason == "unfinished":
        (workspace.directory / "measurement.json").unlink()
    elif reason == "changed_source":
        reservation = load_effort_declaration(workspace.directory / "reservation.json")
        reservation["source_before"] = None
        _save(workspace.directory / "reservation.json", reservation)
        observation = load_effort_declaration(workspace.directory / "measurement.json")
        observation["reservation_sha256"] = measurements._digest(reservation)
        _save(workspace.directory / "measurement.json", observation)
    else:
        human["source_sha256"] = baseline["source_sha256"] = "0" * 64
    current = summarize_conversion_measurements(workspace.ledger)
    human["attempts_sha256"] = current["attempts_sha256"]
    report = summarize_conversion_measurements(workspace.ledger, effort=human, baseline=baseline)
    assert report["comparison"]["status"] == "not_established"
    assert report["comparison"]["human_saved_seconds"] is None
    if reason == "unfinished":
        assert report["unfinished_attempts"] == 1
        assert report["machine_timing_complete"] is False


@pytest.mark.parametrize("field", ["case_id", "source_sha256", "setup_mode", "acceptance_criteria"])
def test_baseline_must_use_same_task_and_setup(workspace: SimpleNamespace, field: str) -> None:
    summary = _record(workspace)
    human, baseline = _effort(summary), _effort(summary, manual=True)
    baseline[field] = "first_use" if field == "setup_mode" else "f" * 64
    with pytest.raises(LocalOperationError, match="different case"):
        summarize_conversion_measurements(workspace.ledger, effort=human, baseline=baseline)


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), "12", 10**1000])
def test_invalid_effort_durations_are_refused(workspace: SimpleNamespace, value: Any) -> None:
    summary = _record(workspace)
    human = _effort(summary)
    human["segments"][0]["seconds"] = value
    with pytest.raises(LocalOperationError):
        summarize_conversion_measurements(workspace.ledger, effort=human)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("extra", 1),
        ("schema_version", "2.0"),
        ("basis", "guessed"),
        ("method", "manual"),
        ("operator", ""),
        ("source_sha256", "x"),
        ("segments", {}),
        ("segments", ["bad"]),
        ("segments", [{"activity": "idle", "seconds": 1}]),
        ("attempts_sha256", "invalid"),
    ],
)
def test_invalid_effort_contracts_are_rejected(
    workspace: SimpleNamespace, field: str, value: Any
) -> None:
    summary = _record(workspace)
    human = _effort(summary)
    human[field] = value
    with pytest.raises(LocalOperationError):
        summarize_conversion_measurements(workspace.ledger, effort=human)


def test_effort_cannot_be_reused_after_new_attempt_or_tampered_binding(
    workspace: SimpleNamespace,
) -> None:
    summary = _record(workspace)
    human = _effort(summary)
    human["attempts_sha256"] = "0" * 64
    with pytest.raises(LocalOperationError, match="complete current"):
        summarize_conversion_measurements(workspace.ledger, effort=human)
    observation = load_effort_declaration(workspace.directory / "measurement.json")
    observation["reservation_sha256"] = "0" * 64
    _save(workspace.directory / "measurement.json", observation)
    with pytest.raises(LocalOperationError, match="unbound"):
        summarize_conversion_measurements(workspace.ledger)


@pytest.mark.parametrize(
    "raw", ["[]", '{"x": 1, "x": 2}', '{"x": NaN}', '{"x": 1e999}', "{bad", "\ud800"]
)
def test_strict_measurement_json(tmp_path: Path, raw: str) -> None:
    path = tmp_path / "record.json"
    path.write_bytes(raw.encode("utf-8", errors="surrogatepass"))
    with pytest.raises(LocalOperationError):
        load_effort_declaration(path)


def test_empty_oversize_and_mixed_ledger_are_refused(
    workspace: SimpleNamespace, tmp_path: Path
) -> None:
    with pytest.raises(LocalOperationError):
        summarize_conversion_measurements(tmp_path / "missing")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(LocalOperationError, match="no attempts"):
        summarize_conversion_measurements(empty)
    path = tmp_path / "large.json"
    path.write_bytes(b" " * (measurements._MAX_JSON + 1))
    with pytest.raises(LocalOperationError, match="exceeds"):
        load_effort_declaration(path)
    _record(workspace)
    extra = workspace.ledger / "extra"
    shutil.copytree(workspace.directory, extra)
    data = load_effort_declaration(extra / "reservation.json")
    data["case_id"] = "other"
    _save(extra / "reservation.json", data)
    observation = load_effort_declaration(extra / "measurement.json")
    observation["reservation_sha256"] = measurements._digest(data)
    _save(extra / "measurement.json", observation)
    with pytest.raises(LocalOperationError, match="mixes"):
        summarize_conversion_measurements(workspace.ledger)


def test_cli_keeps_normal_result_and_has_explicit_summary(
    workspace: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "project",
                "inspect",
                str(workspace.settings),
                "--measurement-dir",
                str(workspace.directory),
                "--case-id",
                "example",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "inspected"
    assert main(["project", "measurement-summary", str(workspace.ledger)]) == 0
    summary = json.loads(capsys.readouterr().out)
    effort, baseline = (
        workspace.ledger.parent / "human.json",
        workspace.ledger.parent / "baseline.json",
    )
    _save(effort, _effort(summary))
    _save(baseline, _effort(summary, manual=True))
    assert (
        main(
            [
                "project",
                "measurement-summary",
                str(workspace.ledger),
                "--effort",
                str(effort),
                "--baseline",
                str(baseline),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["comparison"]["human_saved_seconds"] == 40
    assert main(["project", "plan", str(workspace.settings), "--case-id", "example"]) == 1
    assert "must be supplied together" in capsys.readouterr().err
    assert (
        main(
            [
                "project",
                "plan",
                str(workspace.settings),
                "--measurement-dir",
                str(workspace.directory),
            ]
        )
        == 1
    )


def test_cli_measures_plan_generate_and_blocked_inspection(
    workspace: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ticks = iter(range(20))
    monkeypatch.setattr(time, "perf_counter_ns", lambda: next(ticks))
    for name in ("plan", "generate"):
        arguments = ["project", name, str(workspace.settings)]
        if name == "generate":
            arguments.append("generated")
        assert (
            main(
                [
                    *arguments,
                    "--measurement-dir",
                    str(workspace.ledger / name),
                    "--case-id",
                    "example",
                ]
            )
            == 0
        )
        capsys.readouterr()
    workspace.config.source.write_text(
        "def workflow(x):\n    if x:\n        return x\n    return 0\n"
    )
    assert (
        main(
            [
                "project",
                "inspect",
                str(workspace.settings),
                "--measurement-dir",
                str(workspace.directory),
                "--case-id",
                "example",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
