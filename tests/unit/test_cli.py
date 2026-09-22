"""Unit tests for the command-line interface."""

import json
from pathlib import Path

import pytest

from notebook_to_kedro.cli import main
from notebook_to_kedro.ir import ConversionPlan
from notebook_to_kedro.semantic import PlannerMode, plan_tasks

REFERENCE_NOTEBOOK = Path(__file__).parents[1] / "fixtures" / "notebooks" / "simple_training.ipynb"
ROOT = Path(__file__).parents[2]
PLANNING_CORPUS = Path(__file__).parents[1] / "fixtures" / "evaluation" / "planning" / "v1"


def _blocked_plan(*_args: object, **_kwargs: object) -> ConversionPlan:
    return ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/model.ipynb",
        task_candidates=(),
        blocking_diagnostic_codes=("PY002",),
    )


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


def test_cli_generate_reports_blocked_plans(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "generated"

    monkeypatch.setattr("notebook_to_kedro.cli.plan_notebook_path", _blocked_plan)

    exit_code = main(["generate", str(REFERENCE_NOTEBOOK), str(output_dir)])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Error: Invalid conversion plan: blocking diagnostics are present: PY002" in captured.err
    assert not output_dir.exists()


def test_cli_forwards_hybrid_planner_settings(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    received: dict[str, object] = {}

    def recording_plan(*_args: object, **kwargs: object) -> ConversionPlan:
        received.update(kwargs)
        return ConversionPlan(
            schema_version="1.0",
            planner_version="test-hybrid",
            notebook_path="notebooks/model.ipynb",
            task_candidates=(),
        )

    monkeypatch.setattr("notebook_to_kedro.cli.plan_notebook_path", recording_plan)

    exit_code = main(
        [
            "plan",
            str(REFERENCE_NOTEBOOK),
            "--planner",
            "hybrid",
            "--ollama-model",
            "qwen2.5-coder:7b",
            "--ollama-base-url",
            "http://127.0.0.1:11435",
            "--ollama-timeout",
            "45",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert received["planner"] is PlannerMode.HYBRID
    assert received["ollama_model"] == "qwen2.5-coder:7b"
    assert received["ollama_base_url"] == "http://127.0.0.1:11435"
    assert received["ollama_timeout_seconds"] == 45


def test_cli_reports_missing_hybrid_model(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["plan", str(REFERENCE_NOTEBOOK), "--planner", "hybrid"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Error: Hybrid planner mode requires a downloaded local model" in captured.err


def test_cli_rejects_unknown_planner(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["plan", str(REFERENCE_NOTEBOOK), "--planner", "remote"])

    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "invalid PlannerMode value: 'remote'" in captured.err


def test_cli_benchmark_writes_deterministic_report(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "benchmark",
            str(PLANNING_CORPUS),
            "--project-root",
            str(ROOT),
            "--planners",
            "deterministic",
            "deterministic",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert [case["case_id"] for case in payload["corpus_cases"]] == [
        "file-backed-training",
        "pandas-preprocessing-training",
        "scaled-training",
        "simple-training",
    ]
    assert len(payload["planners"]) == 1
    assert payload["planners"][0]["planner_name"] == "deterministic"
    assert payload["planners"][0]["summary"]["exact_match_rate"] == 1.0


def test_cli_benchmark_builds_selected_hybrid_planner(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[PlannerMode | str, dict[str, object]]] = []

    def recording_factory(
        mode: PlannerMode | str = PlannerMode.DETERMINISTIC, **kwargs: object
    ) -> object:
        calls.append((mode, kwargs))
        return _DeterministicPlanner()

    class _DeterministicPlanner:
        def create_plan(self, facts):  # type: ignore[no-untyped-def]
            return plan_tasks(facts)

    monkeypatch.setattr("notebook_to_kedro.cli.create_semantic_planner", recording_factory)

    exit_code = main(
        [
            "benchmark",
            str(PLANNING_CORPUS),
            "--project-root",
            str(ROOT),
            "--planners",
            "deterministic",
            "hybrid",
            "--ollama-model",
            "local-model",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert [call[0] for call in calls] == [PlannerMode.DETERMINISTIC, PlannerMode.HYBRID]
    assert calls[0][1]["ollama_model"] is None
    assert calls[1][1]["ollama_model"] == "local-model"
    payload = json.loads(captured.out)
    assert [planner["planner_name"] for planner in payload["planners"]] == [
        "deterministic",
        "hybrid:local-model",
    ]


def test_cli_benchmark_reports_invalid_corpus(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["benchmark", "missing-corpus"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Error: planning corpus contains no JSON cases" in captured.err


def test_cli_benchmark_rejects_ollama_settings_without_hybrid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "benchmark",
            str(PLANNING_CORPUS),
            "--ollama-model",
            "local-model",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Error: Ollama settings require planner mode 'hybrid'" in captured.err
