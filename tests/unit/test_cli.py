"""Unit tests for the command-line interface."""

from pathlib import Path

import pytest

from notebook_to_kedro.cli import main

REFERENCE_NOTEBOOK = Path(__file__).parents[1] / "fixtures" / "notebooks" / "simple_training.ipynb"


def test_cli_plan_writes_conversion_report(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["plan", str(REFERENCE_NOTEBOOK)])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.startswith("# Notebook to Kedro Conversion Report\n")
    assert "- Status: `ready`" in captured.out
    assert (
        "| `split_data` | `cell-0006` | `X`, `y` | `X_train`, `X_test`, `y_train`, `y_test` |"
    ) in captured.out
    assert "| `split_data.test_size` | `0.2` | `split_data_test_size` | `cell-0006` |" in (
        captured.out
    )


def test_cli_plan_accepts_project_root(capsys: pytest.CaptureFixture[str]) -> None:
    project_root = REFERENCE_NOTEBOOK.parents[3]

    exit_code = main(["plan", str(REFERENCE_NOTEBOOK), "--project-root", str(project_root)])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "- Notebook: `tests/fixtures/notebooks/simple_training.ipynb`" in captured.out


def test_cli_requires_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "missing command" in captured.err
