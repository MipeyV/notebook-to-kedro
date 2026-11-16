"""Installed synthetic pair, retained failures and adversarial artifact comparisons."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import pytest

from notebook_to_kedro import (
    FunctionalWorkflowConfiguration,
    capture_workflow_provenance,
    generate_functional_kedro_project,
)

ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools/run_workflow_trial.py"
SPEC = importlib.util.spec_from_file_location("workflow_trial_tool", TOOL)
assert SPEC is not None
assert SPEC.loader is not None
TRIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRIAL)
FIGURES = (
    "forecasts",
    "residuals",
    "per_horizon",
    "prices",
    "returns",
    "rolling_volatility",
    "correlations",
)


def _run(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        env=TRIAL.environment(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _prepare(tmp_path: Path, injection: str = "") -> SimpleNamespace:
    source, project, trial = (tmp_path / name for name in ("source", "project", "trial"))
    shutil.copytree(
        ROOT / "tests/fixtures/workflow_trial", source, ignore=shutil.ignore_patterns("__pycache__")
    )
    runtime = source / "src/trial_app/runtime.py"
    runtime.write_text(
        runtime.read_text().replace("# FAILURE_INJECTION", injection), encoding="utf-8"
    )
    for arguments in (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Synthetic trial",
        ),
    ):
        _run(["git", "-C", str(source), *arguments], tmp_path)
    candidate: dict[str, Any] = {
        "estimator": "naive",
        "strategy": "one_step",
        "phase": "validation",
        "seed": 42,
        "output": "artifacts/validation_trial",
    }
    settings = {
        "schema_version": "1.7",
        "entrypoint": "workflow",
        "inputs": {},
        "parameters": {"candidate": candidate},
        "outputs": {"result": "memory"},
        "source_package": "src/trial_app",
        "application_project": {"pyproject": "pyproject.toml", "files": ["uv.lock"]},
        "file_inputs": {
            "market_path": {"path": "market.json", "sidecars": []},
            "protocol_path": {"path": "protocol.json", "sidecars": []},
        },
        "artifact_destinations": {
            "run": {"parameter": "candidate", "key": "output", "path": candidate["output"]}
        },
    }
    config = FunctionalWorkflowConfiguration.from_dict(settings)
    entry = source / "src/trial_app/workflow.py"
    generate_functional_kedro_project(
        entry, config, project, project_root=source, package_name="trial_generated"
    )
    for directory in (project / "application", project):
        _run(
            [
                sys.executable,
                "-I",
                "-c",
                "from hatchling.build import build_editable; build_editable('dist')",
            ],
            directory,
        )
    venv = tmp_path / "venv"
    _run(
        [
            sys.executable,
            "-I",
            "-m",
            "venv",
            "--copies" if os.name == "nt" else "--symlinks",
            "--without-pip",
            str(venv),
        ],
        tmp_path,
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    site = (
        venv / "Lib/site-packages"
        if os.name == "nt"
        else venv / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    )
    (site / "locked-runtime.pth").write_text(sysconfig.get_path("purelib") + "\n", encoding="utf-8")
    uv = shutil.which("uv")
    assert uv is not None
    wheels = [
        str(next((directory / "dist").glob("*.whl")))
        for directory in (project / "application", project)
    ]
    _run(
        [uv, "pip", "install", "--no-index", "--no-deps", "--python", str(python), *wheels],
        tmp_path,
    )
    report_path = capture_workflow_provenance(
        entry,
        config,
        project,
        tmp_path / "provenance",
        project_root=source,
        python_executable=python,
    )[0]
    report = TRIAL.read_json(report_path)
    trial.mkdir()
    shutil.copyfile(report_path, trial / "workflow-provenance.json")
    plan = {
        "document_kind": "local_validation_trial_proposal",
        "candidate": candidate,
        "source_root": str(source),
        "generated_project": str(project),
        "selected_python": str(python),
        "provenance": {"frozen_copy": "workflow-provenance.json", **TRIAL.identity(report_path)},
        "publication_inventory": report["generation"],
        "source_bindings": report["source"]["copies"],
        "input_bindings": {
            "data/01_raw/market_path/market.json": "market.json",
            "data/01_raw/protocol_path/protocol.json": "protocol.json",
        },
        "environment": report["environment"],
        "source_git": report["source"]["git"],
        "protocol": TRIAL.read_json(source / "protocol.json"),
        "execution": {
            "timeout_seconds_per_process": 60,
            "automatic_retries": 0,
            "reference": {
                "cwd": str(trial / "reference"),
                "candidate": candidate,
                "calls": [
                    f"trial_app.runtime.{name}"
                    for name in ("load_market", "load_protocol", "run_benchmark")
                ],
                "inputs": {
                    "market_path": str(project / "data/01_raw/market_path/market.json"),
                    "protocol_path": str(project / "data/01_raw/protocol_path/protocol.json"),
                },
                "artifact_destination": str(trial / "reference" / candidate["output"]),
            },
            "generated": {
                "cwd": str(project),
                "registry": "trial_generated.pipeline_registry.register_pipelines()['__default__']",
                "artifact_destination": str(project / candidate["output"]),
            },
        },
        "expectations": {
            "numeric_tolerance": {"absolute": 0, "relative": 0, "non_finite": "reject"},
            "result_type": "trial_app.runtime.BenchmarkResult",
            "required_files": [
                "protocol.json",
                "metrics.json",
                "run.json",
                "predictions.parquet",
                *[
                    f"figures/{name}.{extension}"
                    for name in FIGURES
                    for extension in ("json", "html")
                ],
            ],
            "predictions_columns": [
                "origin",
                "target_start",
                "target_timestamp",
                "asset",
                "horizon",
                "target",
                "actual",
                "predicted",
            ],
            "metric_keys": ["mae", "rmse", "mae/h1/value", "rmse/h1/value"],
            "allowed_contextual_metadata_differences": ["git_commit", "git_dirty"],
        },
    }
    definition, consent = trial / "trial-definition.json", trial / "synthetic-consent.json"
    _save(definition, plan)
    _consent(definition, consent)
    return SimpleNamespace(
        source=source,
        project=project,
        trial=trial,
        python=python,
        definition=definition,
        consent=consent,
        plan=plan,
    )


def _consent(definition: Path, consent: Path) -> None:
    _save(
        consent,
        {
            "authorization": "execute_validation_pair",
            "reviewed_by": "trusted synthetic fixture only; no real-project approval",
            "definition_sha256": TRIAL.identity(definition)["sha256"],
            "harness_sha256": TRIAL.identity(TOOL)["sha256"],
            "provenance_sha256": TRIAL.read_json(definition)["provenance"]["sha256"],
        },
    )


@pytest.fixture(scope="module")
def completed(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    case = _prepare(tmp_path_factory.mktemp("paired-trial"))
    result = _run(
        [
            str(case.python),
            "-I",
            str(TOOL),
            str(case.definition),
            "--execute",
            "--consent",
            str(case.consent),
        ],
        ROOT,
    )
    assert '"status": "matched_scoped_expectations"' in result.stdout
    return case


@pytest.mark.integration
def test_installed_synthetic_pair_preserves_observations_and_provenance(
    completed: SimpleNamespace,
) -> None:
    result = TRIAL.read_json(completed.trial / "attempt/result.json")
    assert result["postflight"] == "protected_identities_match"
    assert len(result["invocations"]) == 2
    assert result["definition"] == TRIAL.identity(completed.definition)
    assert len(result["artifact_inventories"]["generated"]) == 18
    observation = TRIAL.read_json(completed.trial / "attempt/generated.observation.json")
    assert observation["metrics"] == {
        "mae": 2 / 3,
        "rmse": math.sqrt(2 / 3),
        "mae/h1/value": 2 / 3,
        "rmse/h1/value": math.sqrt(2 / 3),
    }
    assert observation["metadata"]["trace"] == ["market", "protocol", "benchmark"]
    assert all(
        Path(item["path"]).is_relative_to(completed.project)
        for item in observation["imports"].values()
    )
    again = subprocess.run(
        [
            str(completed.python),
            "-I",
            str(TOOL),
            str(completed.definition),
            "--execute",
            "--consent",
            str(completed.consent),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert again.returncode != 0
    assert "FileExistsError" in again.stderr
    assert TRIAL.read_json(completed.trial / "attempt/result.json") == result


@pytest.fixture
def comparison(completed: SimpleNamespace, tmp_path: Path) -> SimpleNamespace:
    plan = copy.deepcopy(completed.plan)
    plan["_definition_directory"] = str(completed.trial)
    observations = {}
    for mode in ("reference", "generated"):
        root = tmp_path / mode
        shutil.copytree(Path(plan["execution"][mode]["artifact_destination"]), root)
        plan["execution"][mode]["artifact_destination"] = str(root)
        observations[mode] = TRIAL.read_json(completed.trial / f"attempt/{mode}.observation.json")
        observations[mode]["directory"] = str(root)
    return SimpleNamespace(plan=plan, observations=observations, root=tmp_path / "generated")


@pytest.mark.integration
@pytest.mark.parametrize(
    "change",
    [
        "prediction",
        "metric",
        "row",
        "column",
        "dtype",
        "missing",
        "unexpected",
        "fingerprint",
        "both_test",
        "nonfinite",
        "memory",
        "source_map",
        "packages",
        "runtime",
        "empty_figure",
        "malformed_figure",
        "ambient_git",
    ],
)
def test_artifact_comparator_rejects_independent_negative_controls(
    comparison: SimpleNamespace, change: str
) -> None:
    root, observations = comparison.root, comparison.observations
    table = pd.read_parquet(root / "predictions.parquet")
    table_changes = {
        "prediction": lambda: table.assign(predicted=table.predicted.add((1, 0, 0))),
        "row": lambda: table.iloc[::-1],
        "column": lambda: table[list(reversed(table.columns))],
        "dtype": lambda: table.astype({"horizon": "int32"}),
    }
    if change in table_changes:
        table_changes[change]().to_parquet(root / "predictions.parquet", index=False)
    elif change == "missing":
        (root / "metrics.json").unlink()
    elif change == "unexpected":
        (root / "unexpected.txt").write_text("unexpected")
    elif change in {"empty_figure", "malformed_figure"}:
        (root / "figures/forecasts.json").write_text("" if change == "empty_figure" else "{oops")
    elif change == "memory":
        observations["generated"]["metrics"]["mae"] = 999
    elif change == "runtime":
        observations["generated"]["runtime"]["python"] = "0.0.0"
    else:
        modes = ("reference", "generated") if change == "both_test" else ("generated",)
        for mode in modes:
            mode_root = Path(comparison.plan["execution"][mode]["artifact_destination"])
            name = "metrics.json" if change in {"metric", "nonfinite"} else "run.json"
            value = TRIAL.read_json(mode_root / name)
            replacements = {
                "metric": ("mae", value.get("mae", 0) + 1),
                "nonfinite": ("mae", float("inf")),
                "fingerprint": ("dataset_fingerprint", "f" * 64),
                "both_test": ("phase", "test"),
                "source_map": ("source_sha256", {}),
                "packages": ("packages", {**value.get("packages", {}), "pandas": "0.0.0"}),
                "ambient_git": ("git_commit", "0" * 40),
            }
            key, replacement = replacements[change]
            value[key] = replacement
            _save(mode_root / name, value)
            observations[mode]["metrics" if name == "metrics.json" else "metadata"] = value
    assert TRIAL.compare_artifacts(comparison.plan, observations)["status"] == "comparison_mismatch"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("injection", "timeout"),
    [
        ("print('x' * 100000); raise RuntimeError('synthetic benchmark failure')", False),
        ("import time; time.sleep(5)", True),
    ],
)
def test_execution_failure_or_timeout_stops_pair_and_retains_attempt(
    tmp_path: Path, injection: str, *, timeout: bool
) -> None:
    case = _prepare(tmp_path, injection)
    if timeout:
        case.plan["execution"]["timeout_seconds_per_process"] = 1
        _save(case.definition, case.plan)
        _consent(case.definition, case.consent)
    result = subprocess.run(
        [
            str(case.python),
            "-I",
            str(TOOL),
            str(case.definition),
            "--execute",
            "--consent",
            str(case.consent),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 1
    evidence = TRIAL.read_json(case.trial / "attempt/result.json")
    assert evidence["status"] == ("timeout" if timeout else "execution_failed")
    assert len(evidence["invocations"]) == 1
    assert evidence["artifact_inventories"]["generated"] == {"status": "absent"}
    assert (case.trial / "attempt/reservation.json").is_file()
    assert (case.trial / "attempt/reference.stderr.log").stat().st_size <= TRIAL.MAX_LOG
    if not timeout:
        assert "protocol.json" in evidence["artifact_inventories"]["reference"]
        assert evidence["invocations"][0]["stdout_truncated"] is True


@pytest.mark.integration
def test_consent_and_frozen_byte_drift_block_execution_before_benchmark(tmp_path: Path) -> None:
    case = _prepare(tmp_path)
    preflight = _run([str(case.python), "-I", str(TOOL), str(case.definition)], ROOT)
    assert '"benchmark_execution": "not_run"' in preflight.stdout
    original_consent = TRIAL.read_json(case.consent)
    for field, replacement in (
        ("harness_sha256", "0" * 64),
        ("definition_sha256", "0" * 64),
        ("provenance_sha256", "0" * 64),
        ("reviewed_by", ""),
        ("authorization", "not_approved"),
    ):
        _save(case.consent, {**original_consent, field: replacement})
        result = subprocess.run(
            [
                str(case.python),
                "-I",
                str(TOOL),
                str(case.definition),
                "--execute",
                "--consent",
                str(case.consent),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert not (case.trial / "attempt").exists()
    _consent(case.definition, case.consent)
    (case.project / "conf/base/parameters.yml").write_text("{}")
    result = subprocess.run(
        [
            str(case.python),
            "-I",
            str(TOOL),
            str(case.definition),
            "--execute",
            "--consent",
            str(case.consent),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    evidence = TRIAL.read_json(case.trial / "attempt/result.json")
    assert evidence["status"] == "postflight_failed"
    assert evidence["invocations"] == []
    assert not (case.project / case.plan["candidate"]["output"]).exists()
