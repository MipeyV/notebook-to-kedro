"""Real trusted synthetic notebook validation through the explicit runtime boundary."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from notebook_to_kedro import (
    GeneratedValidationRequest,
    GenerateRequest,
    generate_project,
    load_local_project_configuration,
    prepare_generated_validation,
    run_generated_validation,
)

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[2]


@pytest.fixture
def delivered(tmp_path: Path) -> GeneratedValidationRequest:
    root = tmp_path / "model"
    shutil.copytree(ROOT / "examples/model_reload", root)
    config = load_local_project_configuration(root / "project.json")
    generate_project(GenerateRequest(config, root / "generated/project"))
    return GeneratedValidationRequest(
        config, root / "generated/project", Path(sys.executable), root / "generated/validation", 60
    )


def test_real_private_validation_includes_model_reload_and_preserves_generation(
    delivered: GeneratedValidationRequest,
) -> None:
    plan = prepare_generated_validation(delivered)
    result = run_generated_validation(delivered, approved_sha256=plan.sha256).to_dict()
    assert result["status"] == "passed", (
        result,
        (delivered.output / "tests.log").read_text(errors="replace"),
    )
    assert isinstance(result["tests"], dict)
    assert result["tests"]["passed"] >= 1
    assert (
        "test_model_reload"
        in (delivered.output / "project/tests/test_notebook_regressions.py").read_text()
    )
    assert all(
        result[key]
        for key in (
            "original_unchanged",
            "snapshot_unchanged",
            "inputs_unchanged",
            "python_unchanged",
        )
    )
    assert (
        json.loads((delivered.project / "regression-coverage.json").read_text())["execution_status"]
        == "not_run"
    )
    assert not (delivered.project / "data/06_models").exists()


def test_cli_stdin_cancellation_produces_terminal_report(
    delivered: GeneratedValidationRequest,
) -> None:
    plan = prepare_generated_validation(delivered)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "notebook_to_kedro.cli",
            "project",
            "validate",
            str(delivered.configuration.project_root / "project.json"),
            str(delivered.project),
            "--python",
            str(delivered.python),
            "--output",
            str(delivered.output),
            "--timeout",
            "60",
            "--approved-sha256",
            plan.sha256,
            "--cancellable-stdin",
        ],
        input="cancel\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "canceled"
    assert payload["tests"] is None
    assert (delivered.output / "report.json").is_file()
