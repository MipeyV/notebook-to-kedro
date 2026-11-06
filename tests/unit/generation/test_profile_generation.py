"""Profiles change project organization while preserving executable task contracts."""

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from notebook_to_kedro import (
    DEFAULT_KEDRO_PROFILE,
    generate_kedro_project,
    load_kedro_profile,
    plan_notebook_path,
    render_conversion_report,
)
from notebook_to_kedro.exceptions import KedroProfileError, ProjectGenerationError
from notebook_to_kedro.ir import CatalogDataset

ROOT = Path(__file__).parents[3]
NOTEBOOK = ROOT / "tests/fixtures/notebooks/simple_training.ipynb"
EXAMPLE = ROOT / "examples/kedro_profiles/team_training.json"


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_explicit_default_keeps_existing_files_byte_identical(tmp_path: Path) -> None:
    plan = plan_notebook_path(NOTEBOOK)
    baseline = tmp_path / "baseline"
    explicit = tmp_path / "explicit"
    generate_kedro_project(plan, baseline)
    generate_kedro_project(plan, explicit, architecture_profile=DEFAULT_KEDRO_PROFILE)
    files = _files(explicit)
    manifest = json.loads(files.pop("architecture-profile.json"))
    assert files == _files(baseline)
    assert manifest["profile"] == DEFAULT_KEDRO_PROFILE.to_dict()
    assert manifest["profile_sha256"] == DEFAULT_KEDRO_PROFILE.sha256


def test_custom_profile_preserves_ast_parameters_datasets_and_provenance(tmp_path: Path) -> None:
    plan = plan_notebook_path(NOTEBOOK)
    original = plan_notebook_path(NOTEBOOK)
    profile = load_kedro_profile(EXAMPLE)
    baseline, custom = tmp_path / "baseline", tmp_path / "custom"
    generate_kedro_project(plan, baseline)
    generate_kedro_project(plan, custom, architecture_profile=profile)
    base_nodes = baseline / "src/generated_notebook/pipelines/notebook_pipeline/nodes.py"
    custom_nodes = custom / "src/generated_notebook/pipelines/training/nodes.py"
    baseline_ast = ast.parse(base_nodes.read_text(encoding="utf-8"))
    customized_ast = ast.parse(custom_nodes.read_text(encoding="utf-8"))
    for old, new in zip(baseline_ast.body, customized_ast.body, strict=True):
        if isinstance(old, ast.FunctionDef):
            assert isinstance(new, ast.FunctionDef)
            assert new.name == f"ml_{old.name}"
            new.name = old.name
        assert ast.dump(new) == ast.dump(old)
    assert (custom / "conf/base/parameters.yml").read_bytes() == (
        baseline / "conf/base/parameters.yml"
    ).read_bytes()
    pipeline = (custom_nodes.parent / "pipeline.py").read_text(encoding="utf-8")
    assert "func=nodes.ml_prepare_features" in pipeline
    assert "'df__prepare_features'" in pipeline
    assert "df__ml_prepare_features" not in pipeline
    assert "'prepare_features_drop_columns': 'params:prepare_features.drop_columns'" in pipeline
    manifest = json.loads((custom / "architecture-profile.json").read_text(encoding="utf-8"))
    assert manifest["profile_sha256"] == profile.sha256
    assert manifest["nodes"] == [
        {
            "task_id": task.id,
            "source_name": task.name,
            "generated_name": f"ml_{task.name}",
            "source_cell_ids": list(task.source_cell_ids),
            "statement_ids": list(task.statement_ids),
        }
        for task in plan.task_candidates
    ]
    assert plan == original
    second = tmp_path / "second"
    generate_kedro_project(plan, second, architecture_profile=profile)
    assert _files(second) == _files(custom)


def test_profile_report_reviews_generated_names_without_mutating_plan() -> None:
    plan = plan_notebook_path(NOTEBOOK)
    profile = load_kedro_profile(EXAMPLE)
    baseline = render_conversion_report(plan)
    report = render_conversion_report(plan, architecture_profile=profile)
    assert "## Kedro Architecture Profile" in report
    assert f"`{profile.sha256}`" in report
    assert "`training`" in report
    assert "| `task-0006` | `split_data` | `ml_split_data` | `cell-0006` |" in report
    assert (
        baseline[baseline.index("## Task Candidates") :]
        == report[report.index("## Task Candidates") :]
    )
    empty = replace(plan, task_candidates=(), imports=(), blocking_diagnostic_codes=("PY002",))
    assert "- Status: `blocked`" in render_conversion_report(empty, architecture_profile=profile)


def test_incompatible_profile_fails_before_output_io(tmp_path: Path) -> None:
    plan = plan_notebook_path(NOTEBOOK)
    plan = replace(plan, imports=("import math as ml_load_data",))
    profile = load_kedro_profile(EXAMPLE)
    with pytest.raises(KedroProfileError, match="shadow imports"):
        generate_kedro_project(plan, tmp_path / "project", architecture_profile=profile)
    with pytest.raises(KedroProfileError, match="shadow imports"):
        render_conversion_report(plan, architecture_profile=profile)
    assert list(tmp_path.iterdir()) == []


def test_copied_data_cannot_overwrite_profile_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_bytes(b"value\n1\n")
    plan = replace(
        plan_notebook_path(NOTEBOOK),
        catalog_datasets=(
            CatalogDataset("df", "CSVDataset", "architecture-profile.json", str(source)),
        ),
    )
    with pytest.raises(ProjectGenerationError, match="destinations overlap"):
        generate_kedro_project(
            plan, tmp_path / "project", architecture_profile=DEFAULT_KEDRO_PROFILE
        )
    assert list(tmp_path.iterdir()) == [source]
