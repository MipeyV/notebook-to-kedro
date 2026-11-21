"""Explicit storage binds the latest leaf and leaves source/default generation intact."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    GenerateRequest,
    LocalProjectConfiguration,
    PlanningResult,
    PlanRequest,
    analyze_notebook_path,
    generate_kedro_project,
    load_local_project_configuration,
    load_notebook_regression_contract,
    plan_notebook_path,
    run_local_operation,
)
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import LocalOperationError, ProjectGenerationError
from notebook_to_kedro.generation.kedro.generator import render_kedro_project


def _source(tmp_path: Path, *cells: str) -> Path:
    path = tmp_path / "model.ipynb"
    path.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"language_info": {"name": "python"}},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": f"stage-{i}",
                        "metadata": {},
                        "source": code,
                        "execution_count": None,
                        "outputs": [],
                    }
                    for i, code in enumerate(cells)
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_only_catalog_and_explicit_storage_metadata_change_and_no_model_is_saved(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path, "model = {'coef': 42}", "fitted_model = model")
    facts, plan = analyze_notebook_path(source), plan_notebook_path(source)
    before = facts.to_json()
    plain, copies = render_kedro_project(plan)
    stored, stored_copies = render_kedro_project(
        plan, source_facts=facts, model_output="fitted_model"
    )
    assert copies == stored_copies
    assert all(stored[path] == text for path, text in plain.items())
    assert facts.to_json() == before
    manifest = json.loads(stored[Path("model-output.json")])
    assert manifest["source_sha256"] == facts.notebook.content_sha256
    assert manifest["source_symbol"] == manifest["dataset"] == "fitted_model"
    assert manifest["catalog"] == {
        "type": "kedro_datasets.pickle.PickleDataset",
        "filepath": "data/06_models/model.pkl",
        "backend": "pickle",
        "versioned": True,
    }
    assert manifest["execution_status"] == manifest["reload_validation_status"] == "not_run"
    assert manifest["runtime_type_status"] == "not_verified"
    assert manifest["generated_regressions_validate_storage"] is False
    project = tmp_path / "project"
    generate_kedro_project(plan, project, source_facts=facts, model_output="fitted_model")
    assert not (project / "data").exists()


@pytest.mark.parametrize("symbol", ["model", "missing", "class", "../model", "", True, 4, []])
def test_invalid_unknown_and_consumed_symbols_refuse_publication(
    tmp_path: Path, symbol: Any
) -> None:
    source = _source(tmp_path, "model = {'coef': 1}", "fitted_model = model")
    destination = tmp_path / "blocked"
    with pytest.raises(ProjectGenerationError, match="model_output"):
        generate_kedro_project(
            plan_notebook_path(source),
            destination,
            source_facts=analyze_notebook_path(source),
            model_output=symbol,
        )
    assert not destination.exists()


def test_original_source_facts_are_required(tmp_path: Path) -> None:
    source = _source(tmp_path, "model = {'coef': 1}")
    with pytest.raises(ProjectGenerationError, match="original source facts"):
        generate_kedro_project(
            plan_notebook_path(source), tmp_path / "blocked", model_output="model"
        )
    assert not (tmp_path / "blocked").exists()


def test_reserved_kedro_parameter_dataset_cannot_be_used_as_model_storage(tmp_path: Path) -> None:
    source = _source(tmp_path, "parameters = {'coef': 1}")
    with pytest.raises(ProjectGenerationError, match="reserved parameters"):
        generate_kedro_project(
            plan_notebook_path(source),
            tmp_path / "blocked",
            source_facts=analyze_notebook_path(source),
            model_output="parameters",
        )
    assert not (tmp_path / "blocked").exists()


def test_model_persistence_does_not_bypass_the_fitted_alias_guard(tmp_path: Path) -> None:
    source = (
        Path(__file__).parents[3]
        / "examples/nested_financial/credit_pipeline/boundary_fitted_alias.ipynb"
    )
    with pytest.raises(ProjectGenerationError, match="SA009"):
        generate_kedro_project(
            plan_notebook_path(source),
            tmp_path / "blocked",
            source_facts=analyze_notebook_path(source),
            model_output="fitted_model",
        )
    assert not (tmp_path / "blocked").exists()


@pytest.mark.parametrize("consume_latest", [False, True])
def test_rebound_symbol_selects_latest_version_and_never_an_old_leaf(
    tmp_path: Path, *, consume_latest: bool
) -> None:
    cells = ["model = 1", "model = 2"]
    if consume_latest:
        cells.append("result = model + 1")
    source = _source(tmp_path, *cells)
    facts, plan = analyze_notebook_path(source), plan_notebook_path(source)
    if consume_latest:
        with pytest.raises(ProjectGenerationError, match="latest value"):
            render_kedro_project(plan, source_facts=facts, model_output="model")
    else:
        files, _ = render_kedro_project(plan, source_facts=facts, model_output="model")
        manifest = json.loads(files[Path("model-output.json")])
        assert manifest["dataset"] == "model__" + plan.task_candidates[-1].name
        assert manifest["source_task_id"] == plan.task_candidates[-1].id


def test_ordering_consumers_also_disqualify_a_model_leaf(tmp_path: Path) -> None:
    source = _source(tmp_path, "model = 1", "value = 2")
    plan = plan_notebook_path(source)
    with pytest.raises(ProjectGenerationError, match="generated leaf"):
        render_kedro_project(
            plan,
            source_facts=analyze_notebook_path(source),
            model_output="model",
            order_after={plan.task_candidates[1].id: plan.task_candidates[0].id},
        )


def test_local_settings_roundtrip_and_default_omission(tmp_path: Path) -> None:
    source = _source(tmp_path, "model = {'coef': 42}")
    base = LocalProjectConfiguration(tmp_path, source, "notebook")
    assert "model_output" not in base.to_dict()
    configured = replace(base, model_output="model")
    path = tmp_path / "project.json"
    path.write_text(json.dumps(configured.to_dict()), encoding="utf-8")
    assert load_local_project_configuration(path) == configured


@pytest.mark.parametrize("symbol", ["class", "../model", "", True, [], Path("model")])
def test_local_settings_require_an_identifier(tmp_path: Path, symbol: Any) -> None:
    source = _source(tmp_path, "model = 1")
    with pytest.raises(LocalOperationError, match="model_output"):
        LocalProjectConfiguration(tmp_path, source, "notebook", model_output=symbol)


def test_functional_settings_do_not_silently_claim_persistence_support(tmp_path: Path) -> None:
    source = tmp_path / "workflow.py"
    with pytest.raises(LocalOperationError, match="model_output"):
        LocalProjectConfiguration(tmp_path, source, "functional", model_output="model")


def test_cli_and_local_preview_publish_only_the_explicit_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    example = Path(__file__).parents[3] / "examples/nested_financial/credit_pipeline"
    workspace = tmp_path / "workspace"
    shutil.copytree(example, workspace)
    monkeypatch.chdir(workspace)
    source = workspace / "workflow.ipynb"
    cli_project = workspace / "cli"
    assert main(["generate", str(source), str(cli_project), "--model-output", "fitted_model"]) == 0
    assert "model-output.json" in capsys.readouterr().out
    assert not (cli_project / "data/06_models").exists()
    config = LocalProjectConfiguration(
        workspace,
        source,
        "notebook",
        model_output="fitted_model",
        regression_contract=workspace / "regression.json",
    )
    preview = run_local_operation(PlanRequest(config))
    assert isinstance(preview, PlanningResult)
    assert any(file.path == "model-output.json" for file in preview.files)
    result = run_local_operation(GenerateRequest(config, workspace / "local"))
    assert result.to_dict()["execution_status"] == "not_run"
    assert not (workspace / "local/data/06_models").exists()
    assert json.loads((workspace / "local/regression-coverage.json").read_text(encoding="utf-8"))[
        "missing_pipeline_outputs"
    ]


def test_model_storage_changes_no_business_code_or_supplied_oracles() -> None:
    source = Path(__file__).parents[3] / "examples/nested_financial/credit_pipeline/workflow.ipynb"
    contract = load_notebook_regression_contract(source.with_name("regression.json"))
    facts, plan = analyze_notebook_path(source), plan_notebook_path(source)
    plain, _ = render_kedro_project(plan, source_facts=facts, regression_contract=contract)
    stored, _ = render_kedro_project(
        plan, source_facts=facts, regression_contract=contract, model_output="fitted_model"
    )
    for path in plain:
        if path not in {
            Path("conf/base/catalog.yml"),
            Path("tests/regression_cases.json"),
            Path("tests/test_notebook_regressions.py"),
        }:
            assert stored[path] == plain[path]
    cases = json.loads(stored[Path("tests/regression_cases.json")])
    assert cases["contract"] == json.loads(plain[Path("tests/regression_cases.json")])["contract"]
    assert cases["model_output"]["dataset"] == "fitted_model"
    assert (
        "Regression model catalog declaration changed"
        in stored[Path("tests/test_notebook_regressions.py")]
    )
