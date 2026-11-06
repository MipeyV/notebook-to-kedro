"""Architecture profiles are explicit and shared by CLI review and generation."""

import json
from pathlib import Path

import pytest

from notebook_to_kedro.cli import main

ROOT = Path(__file__).parents[2]
NOTEBOOK = ROOT / "tests/fixtures/notebooks/simple_training.ipynb"
PROFILE = ROOT / "examples/kedro_profiles/team_training.json"


def test_cli_reviews_the_profile_before_generation(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["plan", str(NOTEBOOK), "--architecture-profile", str(PROFILE)]) == 0
    result = capsys.readouterr()
    assert result.err == ""
    assert "example.team-training" in result.out
    assert "ml_split_data" in result.out
    assert "Pipeline directory and registry key: `training`" in result.out


def test_cli_generates_the_reviewed_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "project"
    assert (
        main(["generate", str(NOTEBOOK), str(output), "--architecture-profile", str(PROFILE)]) == 0
    )
    result = capsys.readouterr()
    assert result.err == ""
    assert (output / "src/generated_notebook/pipelines/training/nodes.py").is_file()
    metadata = json.loads((output / "architecture-profile.json").read_text(encoding="utf-8"))
    assert metadata["profile"]["profile_id"] == "example.team-training"


@pytest.mark.parametrize("command", ["plan", "generate"])
def test_invalid_profile_fails_before_notebook_or_output_io(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    args = [command, str(tmp_path / "missing.ipynb")]
    if command == "generate":
        args.append(str(tmp_path / "project"))
    args.extend(["--architecture-profile", str(tmp_path / "missing-profile.json")])
    assert main(args) == 1
    result = capsys.readouterr()
    assert result.out == ""
    assert "Error: Cannot read Kedro profile" in result.err
    assert list(tmp_path.iterdir()) == []
