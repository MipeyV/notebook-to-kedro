"""Tests for deterministic assembly of semantic planning suggestions."""

from dataclasses import replace
from pathlib import Path

import pytest

from notebook_to_kedro.exceptions import HybridPlanAssemblyError, SemanticProviderError
from notebook_to_kedro.generation import generate_kedro_project
from notebook_to_kedro.ir import CatalogDataset, ConversionPlan, ParameterValue
from notebook_to_kedro.reporting import render_conversion_report
from notebook_to_kedro.semantic import (
    HYBRID_PLANNER_VERSION,
    FakeSemanticPlanningProvider,
    HybridSemanticPlanner,
    SemanticGroupingResponse,
    SemanticPlanner,
    SemanticPlanningRequest,
    SemanticPlanningResponse,
    SemanticPlanningResult,
    SemanticPlanningTrace,
    SemanticTaskSuggestion,
    assemble_hybrid_plan,
    validate_conversion_plan,
)
from notebook_to_kedro.semantic import hybrid as hybrid_module


def _result(
    request: SemanticPlanningRequest,
    response: SemanticPlanningResponse,
) -> SemanticPlanningResult:
    return SemanticPlanningResult(
        request=request,
        response=response,
        trace=SemanticPlanningTrace(
            request_id=request.request_id,
            prompt_version=request.prompt_version,
            provider_name="fake",
            model_name="semantic-fixture",
        ),
    )


def _suggestion_from_tasks(
    request: SemanticPlanningRequest,
    *indexes: int,
    node_name: str,
) -> SemanticTaskSuggestion:
    tasks = tuple(request.baseline_plan.task_candidates[index] for index in indexes)
    return SemanticTaskSuggestion(
        source_cell_ids=tuple(
            dict.fromkeys(cell_id for task in tasks for cell_id in task.source_cell_ids)
        ),
        statement_ids=tuple(statement_id for task in tasks for statement_id in task.statement_ids),
        node_name=node_name,
        inputs=tuple(dict.fromkeys(name for task in tasks for name in task.inputs)),
        outputs=tuple(dict.fromkeys(name for task in tasks for name in task.outputs)),
        parameter_names=tuple(dict.fromkeys(name for task in tasks for name in task.parameters)),
        pipeline_id="notebook_pipeline",
    )


def test_assemble_hybrid_plan_preserves_an_unchanged_static_plan(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    plan = assemble_hybrid_plan(_result(semantic_request, semantic_response))

    assert plan.planner_version == HYBRID_PLANNER_VERSION
    assert plan.task_candidates == semantic_request.baseline_plan.task_candidates
    assert plan.imports == semantic_request.baseline_plan.imports
    assert plan.catalog_datasets == semantic_request.baseline_plan.catalog_datasets
    assert plan.parameters == semantic_request.baseline_plan.parameters
    provenance = next(diagnostic for diagnostic in plan.diagnostics if diagnostic.code == "SP001")
    assert "provider fake" in provenance.message
    report = render_conversion_report(plan)
    assert "`SP001`" in report
    assert "model semantic-fixture" in report
    validate_conversion_plan(plan)


def test_assemble_hybrid_plan_renames_parameters_and_records_review_notes(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
    tmp_path: Path,
) -> None:
    original = semantic_response.tasks[1]
    renamed = replace(
        original,
        node_name="prepare_customer_data",
        inputs=(),
        outputs=("X", "y"),
        parameter_names=(),
        review_notes=("Confirm the custom business cleanup.",),
    )
    response = replace(
        semantic_response,
        tasks=(semantic_response.tasks[0], renamed, *semantic_response.tasks[2:]),
        review_notes=("Human review is required before release.",),
    )

    plan = assemble_hybrid_plan(_result(semantic_request, response))

    task = plan.task_candidates[1]
    assert task.name == "prepare_customer_data"
    assert task.inputs == original.inputs
    assert task.outputs == original.outputs
    assert task.parameters == ("prepare_customer_data.drop_columns",)
    renamed_parameter = next(
        parameter
        for parameter in plan.parameters
        if parameter.name == "prepare_customer_data.drop_columns"
    )
    assert renamed_parameter.function_argument == "prepare_customer_data_drop_columns"
    assert {diagnostic.code for diagnostic in plan.diagnostics} >= {
        "SP001",
        "SP002",
        "SP003",
        "SP004",
    }

    output_path = tmp_path / "hybrid_project"
    generate_kedro_project(plan, output_path, package_name="hybrid_project")
    nodes = (
        output_path / "src" / "hybrid_project" / "pipelines" / "notebook_pipeline" / "nodes.py"
    ).read_text(encoding="utf-8")
    assert "def prepare_customer_data(df, prepare_customer_data_drop_columns):" in nodes
    assert "columns=prepare_customer_data_drop_columns" in nodes


def test_assemble_hybrid_plan_groups_contiguous_tasks_in_source_order(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    merged = replace(
        _suggestion_from_tasks(
            semantic_request,
            0,
            1,
            node_name="load_and_prepare_data",
        ),
        review_notes=("Two deterministic steps were grouped.",),
    )
    response = replace(
        semantic_response,
        tasks=(*semantic_response.tasks[2:], merged),
    )

    plan = assemble_hybrid_plan(_result(semantic_request, response))

    first = plan.task_candidates[0]
    baseline_first, baseline_second = semantic_request.baseline_plan.task_candidates[:2]
    assert len(plan.task_candidates) == len(semantic_request.baseline_plan.task_candidates) - 1
    assert first.id == baseline_first.id
    assert first.name == "load_and_prepare_data"
    assert first.source_cell_ids == (
        *baseline_first.source_cell_ids,
        *baseline_second.source_cell_ids,
    )
    assert first.statement_ids == (*baseline_first.statement_ids, *baseline_second.statement_ids)
    assert first.inputs == ()
    assert first.outputs == ("iris", "df", "X", "y")
    assert first.source == f"{baseline_first.source}\n{baseline_second.source}"
    assert first.parameters == ("load_and_prepare_data.drop_columns",)
    assert any(
        diagnostic.task_id == first.id and diagnostic.code == "PD002"
        for diagnostic in plan.diagnostics
    )


def test_assemble_hybrid_plan_rejects_partial_static_task_splitting(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    first = semantic_request.baseline_plan.task_candidates[0]
    split_tasks = tuple(
        SemanticTaskSuggestion(
            source_cell_ids=first.source_cell_ids,
            statement_ids=(statement_id,),
            node_name=f"partial_{index}",
            inputs=(),
            outputs=first.outputs,
            parameter_names=(),
            pipeline_id="notebook_pipeline",
        )
        for index, statement_id in enumerate(first.statement_ids)
    )
    response = replace(
        semantic_response,
        tasks=(*split_tasks, *semantic_response.tasks[1:]),
    )

    with pytest.raises(HybridPlanAssemblyError, match="partial task splitting"):
        assemble_hybrid_plan(_result(semantic_request, response))


def test_assemble_hybrid_plan_rejects_noncontiguous_grouping(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    merged = _suggestion_from_tasks(
        semantic_request,
        0,
        2,
        node_name="unsafe_reordering",
    )
    response = replace(
        semantic_response,
        tasks=(merged, semantic_response.tasks[1], *semantic_response.tasks[3:]),
    )

    with pytest.raises(HybridPlanAssemblyError, match="non-contiguous"):
        assemble_hybrid_plan(_result(semantic_request, response))


def test_assemble_hybrid_plan_rejects_unsupported_pipeline_assignment(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    response = replace(
        semantic_response,
        tasks=(
            replace(semantic_response.tasks[0], pipeline_id="data_engineering"),
            *semantic_response.tasks[1:],
        ),
    )

    with pytest.raises(HybridPlanAssemblyError, match="unsupported hybrid pipeline IDs"):
        assemble_hybrid_plan(_result(semantic_request, response))


def test_assemble_hybrid_plan_rejects_conflicting_parameter_suffixes(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    merged = _suggestion_from_tasks(
        semantic_request,
        2,
        3,
        node_name="split_and_train",
    )
    response = replace(
        semantic_response,
        tasks=(*semantic_response.tasks[:2], merged, *semantic_response.tasks[4:]),
    )

    with pytest.raises(HybridPlanAssemblyError, match="conflicting parameter names"):
        assemble_hybrid_plan(_result(semantic_request, response))


def test_assemble_hybrid_plan_rejects_missing_static_parameters(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    extra_parameter = ParameterValue(
        name="unassigned.value",
        value=1,
        function_argument="unassigned_value",
        source_cell_id="cell-0003",
    )
    baseline = replace(
        semantic_request.baseline_plan,
        parameters=(*semantic_request.baseline_plan.parameters, extra_parameter),
    )
    request = replace(semantic_request, baseline_plan=baseline)

    with pytest.raises(HybridPlanAssemblyError, match="did not preserve parameters"):
        assemble_hybrid_plan(_result(request, semantic_response))


def test_assemble_hybrid_plan_wraps_response_and_plan_validation_errors(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    incomplete_response = replace(semantic_response, tasks=())
    with pytest.raises(HybridPlanAssemblyError, match="Cannot assemble hybrid plan"):
        assemble_hybrid_plan(_result(semantic_request, incomplete_response))

    duplicate = CatalogDataset(name="duplicate", type="MemoryDataset", filepath="memory")
    baseline = replace(
        semantic_request.baseline_plan,
        catalog_datasets=(duplicate, duplicate),
    )
    request = replace(semantic_request, baseline_plan=baseline)
    with pytest.raises(HybridPlanAssemblyError, match="duplicate catalog dataset name"):
        assemble_hybrid_plan(_result(request, semantic_response))


def test_assemble_hybrid_plan_rejects_blocked_baseline(
    semantic_request: SemanticPlanningRequest,
) -> None:
    baseline = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path=semantic_request.facts.notebook.path,
        task_candidates=(),
        blocking_diagnostic_codes=("PY002",),
    )
    request = replace(semantic_request, baseline_plan=baseline)
    response = SemanticPlanningResponse(
        schema_version="1.0",
        request_id=request.request_id,
        tasks=(),
    )

    with pytest.raises(HybridPlanAssemblyError, match="blocked deterministic plan"):
        assemble_hybrid_plan(_result(request, response))


def test_hybrid_planner_implements_protocol_and_returns_assembled_plan(
    semantic_request: SemanticPlanningRequest,
    semantic_grouping_response: SemanticGroupingResponse,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = f"planning-{semantic_request.facts.notebook.content_sha256[:16]}"
    response = replace(semantic_grouping_response, request_id=request_id)
    provider = FakeSemanticPlanningProvider(response_json=response.to_json())
    planner: SemanticPlanner = HybridSemanticPlanner(provider)
    monkeypatch.setattr(hybrid_module, "has_semantic_merge_candidates", lambda _request: True)

    plan = planner.create_plan(semantic_request.facts)

    assert plan.planner_version == HYBRID_PLANNER_VERSION
    assert plan.task_candidates == semantic_request.baseline_plan.task_candidates
    assert provider.requests[0].request_id.startswith("planning-")


def test_hybrid_planner_falls_back_on_provider_failure(
    semantic_request: SemanticPlanningRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeSemanticPlanningProvider(
        error=SemanticProviderError("provider_timeout", "request timed out")
    )
    monkeypatch.setattr(hybrid_module, "has_semantic_merge_candidates", lambda _request: True)

    plan = HybridSemanticPlanner(provider).create_plan(semantic_request.facts)

    assert plan.task_candidates == semantic_request.baseline_plan.task_candidates
    assert plan.planner_version == f"{HYBRID_PLANNER_VERSION}-fallback"
    assert plan.diagnostics[-1].code == "SP005"
    assert "provider_timeout" in plan.diagnostics[-1].message


def test_hybrid_planner_falls_back_on_assembly_failure(
    semantic_request: SemanticPlanningRequest,
    semantic_grouping_response: SemanticGroupingResponse,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = f"planning-{semantic_request.facts.notebook.content_sha256[:16]}"
    response = replace(semantic_grouping_response, request_id=request_id)
    provider = FakeSemanticPlanningProvider(response_json=response.to_json())
    monkeypatch.setattr(hybrid_module, "has_semantic_merge_candidates", lambda _request: True)

    def fail_assembly(_result: SemanticPlanningResult) -> ConversionPlan:
        raise HybridPlanAssemblyError("unsupported assembled plan")

    monkeypatch.setattr(hybrid_module, "assemble_hybrid_plan", fail_assembly)

    plan = HybridSemanticPlanner(provider).create_plan(semantic_request.facts)

    assert plan.task_candidates == semantic_request.baseline_plan.task_candidates
    assert plan.planner_version == f"{HYBRID_PLANNER_VERSION}-fallback"
    assert "hybrid_assembly_failed" in plan.diagnostics[-1].message


def test_hybrid_planner_skips_provider_without_merge_candidates(
    semantic_request: SemanticPlanningRequest,
    semantic_grouping_response: SemanticGroupingResponse,
) -> None:
    provider = FakeSemanticPlanningProvider(response_json=semantic_grouping_response.to_json())

    plan = HybridSemanticPlanner(provider).create_plan(semantic_request.facts)

    assert plan == semantic_request.baseline_plan
    assert provider.requests == ()


def test_hybrid_planner_skips_provider_for_blocked_baseline(
    semantic_request: SemanticPlanningRequest,
    semantic_grouping_response: SemanticGroupingResponse,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked = replace(
        semantic_request.baseline_plan,
        task_candidates=(),
        blocking_diagnostic_codes=("PY002",),
    )
    monkeypatch.setattr(hybrid_module, "plan_tasks", lambda _facts: blocked)
    provider = FakeSemanticPlanningProvider(response_json=semantic_grouping_response.to_json())

    plan = HybridSemanticPlanner(provider).create_plan(semantic_request.facts)

    assert plan is blocked
    assert provider.requests == ()
