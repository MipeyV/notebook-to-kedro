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


def test_cli_generate_writes_kedro_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "generated"

    exit_code = main(
        [
            "generate",
            str(REFERENCE_NOTEBOOK),
            str(output_dir),
            "--package-name",
            "cli_generated",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert f"Created Kedro project at `{output_dir}`" in captured.out
    assert f"- `{output_dir / 'pyproject.toml'}`" in captured.out
    assert (output_dir / "src" / "cli_generated" / "pipelines" / "notebook_pipeline").is_dir()
    assert (output_dir / "conf" / "base" / "parameters.yml").is_file()


def test_cli_generate_accepts_project_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project_root = REFERENCE_NOTEBOOK.parents[3]
    output_dir = tmp_path / "generated"

    exit_code = main(
        [
            "generate",
            str(REFERENCE_NOTEBOOK),
            str(output_dir),
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert (output_dir / "pyproject.toml").is_file()
    assert "Created Kedro project" in captured.out


def test_cli_plan_reports_load_errors(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["plan", "missing.ipynb"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.startswith("Error: NB001: Cannot read notebook: missing.ipynb")


def test_cli_generate_rejects_existing_output_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "generated"
    output_dir.mkdir()

    exit_code = main(["generate", str(REFERENCE_NOTEBOOK), str(output_dir)])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert f"Error: Destination already exists: {output_dir}" in captured.err
