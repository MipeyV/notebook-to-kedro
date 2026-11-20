"""Offline checks for the trusted bootstrap harness; no network or package installation."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).parents[2]


@pytest.fixture
def bootstrap() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "bootstrap_check", ROOT / "tools/check_generated_bootstrap.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _observations(*, mutation: bool) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "mutation_applied": mutation,
        "runner_completed": True,
        "observations": {
            "predictions": [1.0, 2.0, 5.0, 10.0] if mutation else [0.0, 1.0, 4.0, 9.0],
            "error": 0.0,
        },
        "status": "observation_mismatch" if mutation else "matched",
    }


@pytest.mark.parametrize("mutation", [False, True])
def test_expected_cli_observations_are_explicit(
    bootstrap: ModuleType, tmp_path: Path, *, mutation: bool
) -> None:
    path = tmp_path / "observations.json"
    data = _observations(mutation=mutation)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert bootstrap._check_observation_report(path, mutation=mutation) == data


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("runner_completed", False),
        ("runner_completed", 1),
        ("mutation_applied", False),
        ("status", "matched"),
        ("status", "setup_failed"),
        ("observations", {"predictions": [0.0, 1.0, 4.0, 9.0], "error": 0.0}),
        ("observations", {"predictions": [1.0, 2.0, 5.0, 10.0], "error": 1.0}),
    ],
)
def test_setup_errors_and_unrelated_drift_cannot_satisfy_negative_control(
    bootstrap: ModuleType, tmp_path: Path, key: str, value: Any
) -> None:
    data = _observations(mutation=True)
    data[key] = value
    path = tmp_path / "observations.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Unexpected independent"):
        bootstrap._check_observation_report(path, mutation=True)


def test_missing_report_is_not_a_successful_negative_control(
    bootstrap: ModuleType, tmp_path: Path
) -> None:
    with pytest.raises(FileNotFoundError):
        bootstrap._check_observation_report(tmp_path / "missing.json", mutation=True)


@pytest.mark.parametrize(
    ("code", "expected", "passes"), [(0, 0, True), (1, 1, True), (2, 1, False), (1, 0, False)]
)
def test_process_outcomes_require_the_declared_exit_status(
    bootstrap: ModuleType, tmp_path: Path, code: int, expected: int, *, passes: bool
) -> None:
    stages: list[dict[str, Any]] = []
    args = [sys.executable, "-I", "-c", f"raise SystemExit({code})"]
    if passes:
        bootstrap._command(
            args, tmp_path, tmp_path / "stage.log", stages, expected_returncode=expected
        )
    else:
        with pytest.raises(RuntimeError, match="Command failed"):
            bootstrap._command(
                args, tmp_path, tmp_path / "stage.log", stages, expected_returncode=expected
            )
    assert stages[0]["returncode"] == code
    assert stages[0]["status"] == ("passed" if passes else "failed")


def test_child_environment_excludes_source_and_pytest_overrides(
    bootstrap: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = ("PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")
    for name in names:
        monkeypatch.setenv(name, "untrusted-override")
    result = bootstrap._environment()
    assert not set(names) & result.keys()
    assert result["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert result["DO_NOT_TRACK"] == "1"


def test_main_keeps_four_functional_variants_and_adds_two_procedural_variants(
    bootstrap: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(
        bootstrap,
        "_check_case",
        lambda path, suffix, profile: calls.append(
            (path.name, suffix, None if profile is None else profile.pipeline_name)
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        "_check_procedural_case",
        lambda path, profile: calls.append(
            (path.name, "procedural", None if profile is None else profile.pipeline_name)
        ),
    )
    monkeypatch.setattr(sys, "argv", ["check", str(tmp_path / "evidence")])
    bootstrap.main()
    assert calls == [
        ("py-default", ".py", None),
        ("py-custom", ".py", "training"),
        ("ipynb-default", ".ipynb", None),
        ("ipynb-custom", ".ipynb", "training"),
        ("procedural-default", "procedural", None),
        ("procedural-custom", "procedural", "training"),
    ]
    with pytest.raises(FileExistsError):
        bootstrap.main()
    assert len(calls) == 6


def test_failed_installation_retains_procedural_failure_evidence_and_restores_cwd(
    bootstrap: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Simulated installation failure")

    monkeypatch.setattr(bootstrap, "_install_and_test", fail)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="Simulated installation"):
        bootstrap._check_procedural_case(tmp_path / "case", None)
    assert Path.cwd() == tmp_path
    evidence = json.loads((tmp_path / "case/evidence.json").read_text(encoding="utf-8"))
    assert evidence["status"] == "failed"
    assert evidence["error"]["type"] == "RuntimeError"
    assert evidence["fixtures"]["training"]["sha256"]
    assert evidence["contract_sha256"]
    assert not (tmp_path / "case/venv").exists()


@pytest.mark.parametrize("tamper", ["none", "input", "source"])
def test_procedural_postflight_rejects_input_and_source_changes(
    bootstrap: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str
) -> None:
    def simulate_install(
        directory: Path, project: Path, evidence: dict[str, Any], **_kwargs: Any
    ) -> Path:
        runtime = directory / "installed-project"
        for name in ("conf", "data"):
            shutil.copytree(project / name, runtime / name)
        if tamper == "input":
            (runtime / "data/01_raw/training.csv").write_text("changed", encoding="utf-8")
        if tamper == "source":
            (project / "pyproject.toml").write_text("changed", encoding="utf-8")
        evidence["passed_tests"] = 5
        return runtime

    monkeypatch.setattr(bootstrap, "_install_and_test", simulate_install)
    monkeypatch.setattr(bootstrap, "_command", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        bootstrap,
        "_observe_procedural_cli",
        lambda *_args, mutation: _observations(mutation=mutation),
    )
    if tamper == "none":
        evidence = bootstrap._check_procedural_case(tmp_path / "case", None)
        assert evidence["status"] == "passed"
        assert evidence["regression_gaps"]["missing_node_positive_expectations"] == [
            "task-0001",
            "task-0002",
        ]
    else:
        with pytest.raises(RuntimeError, match="changed"):
            bootstrap._check_procedural_case(tmp_path / "case", None)
        evidence = json.loads((tmp_path / "case/evidence.json").read_text(encoding="utf-8"))
        assert evidence["status"] == "failed"
