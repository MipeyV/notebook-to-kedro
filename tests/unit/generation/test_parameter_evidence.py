"""Exact parameter locations, types, ambiguity rejection, and V1 compatibility."""

from dataclasses import asdict, replace
from pathlib import Path

import pytest

from notebook_to_kedro import plan_notebook_path
from notebook_to_kedro.evaluation import load_planning_corpus
from notebook_to_kedro.generation.code import (
    NODE_CODE_PARAMETER_EVIDENCE_VERSION,
    NodeCodeRequest,
    OllamaNodeCodeProvider,
    build_node_code_request,
    build_parameter_evidence,
)
from notebook_to_kedro.generation.kedro import render_node_function
from notebook_to_kedro.ir import TaskCandidate

ROOT = Path(__file__).parents[3]


@pytest.fixture
def node_request() -> NodeCodeRequest:
    return NodeCodeRequest(
        schema_version="1.0",
        request_id="parameters-1",
        task_id="task-1",
        node_name="prepare",
        raw_source='X = df.drop(columns=["target"])\ny = df["target"]',
        source_cell_ids=("cell-1",),
        statement_ids=("stmt-1", "stmt-2"),
        inputs=("df",),
        outputs=("X", "y"),
        parameter_names=("prepare.drop_columns",),
        parameter_arguments=("columns_to_drop",),
    )


def test_evidence_selects_whole_list_not_target_selection(node_request: NodeCodeRequest) -> None:
    (item,) = build_parameter_evidence(node_request)

    assert NODE_CODE_PARAMETER_EVIDENCE_VERSION == "1.0"
    assert asdict(item) == {
        "parameter_name": "prepare.drop_columns",
        "function_argument": "columns_to_drop",
        "source_expression": '["target"]',
        "value_type": "list",
        "start_offset": node_request.raw_source.index('["target"]'),
        "end_offset": node_request.raw_source.index('["target"]') + len('["target"]'),
    }
    rewritten = (
        node_request.raw_source[: item.start_offset]
        + item.function_argument
        + node_request.raw_source[item.end_offset :]
    )
    assert rewritten == 'X = df.drop(columns=columns_to_drop)\ny = df["target"]'


def test_evidence_tracks_multiline_unicode_and_crlf_offsets(node_request: NodeCodeRequest) -> None:
    source = (
        'note = "caf\u00e9"; X = df.drop(columns=[\r\n'
        '    "cibl\u00e9",\r\n])\r\ny = df["cibl\u00e9"]'
    )
    request = replace(node_request, raw_source=source)
    (item,) = build_parameter_evidence(request)

    assert item.source_expression == '[\r\n    "cibl\u00e9",\r\n]'
    assert source[item.start_offset : item.end_offset] == item.source_expression
    task = TaskCandidate(
        id=request.task_id,
        name=request.node_name,
        source_cell_ids=request.source_cell_ids,
        statement_ids=request.statement_ids,
        inputs=request.inputs,
        outputs=request.outputs,
        source=source,
        parameters=request.parameter_names,
    )
    code = render_node_function(task)
    assert 'note = "caf\u00e9"; X = df.drop(columns=prepare_drop_columns)' in code
    assert 'y = df["cibl\u00e9"]' in code


@pytest.mark.parametrize(
    ("source", "suffix", "expression", "value_type"),
    [
        ('df = df.fillna({"x": 0})', "fillna_values", '{"x": 0}', "dict"),
        ("df = df.fillna(value=0.5)", "fillna_values", "0.5", "float"),
        ("df = df.drop(columns=('x', 'y'))", "drop_columns", "('x', 'y')", "tuple"),
        ("df = df.drop(columns='x')", "drop_columns", "'x'", "str"),
        ("scaler = StandardScaler(with_mean=False)", "with_mean", "False", "bool"),
        ("model = RandomForestClassifier(random_state=-1)", "random_state", "-1", "int"),
    ],
)
def test_evidence_preserves_literal_types(
    node_request: NodeCodeRequest, source: str, suffix: str, expression: str, value_type: str
) -> None:
    request = replace(
        node_request,
        raw_source=source,
        parameter_names=(f"prepare.{suffix}",),
        parameter_arguments=("argument",),
    )
    (item,) = build_parameter_evidence(request)

    assert item.source_expression == expression
    assert item.value_type == value_type
    assert item.function_argument == "argument"


def test_evidence_is_sorted_by_source_not_parameter_order(node_request: NodeCodeRequest) -> None:
    source = "model = RandomForestClassifier(n_estimators=10, random_state=10)\nother = 10"
    request = replace(
        node_request,
        raw_source=source,
        parameter_names=("prepare.random_state", "prepare.n_estimators"),
        parameter_arguments=("seed", "count"),
    )
    items = build_parameter_evidence(request)

    assert tuple(item.function_argument for item in items) == ("count", "seed")
    assert items[0].start_offset < items[1].start_offset
    assert items[0].source_expression == items[1].source_expression == "10"
    assert items[-1].end_offset < source.index("other")


def test_renderer_uses_parameter_identity_when_task_is_renamed(
    node_request: NodeCodeRequest,
) -> None:
    task = TaskCandidate(
        id=node_request.task_id,
        name="merged_task",
        source_cell_ids=node_request.source_cell_ids,
        statement_ids=node_request.statement_ids,
        inputs=node_request.inputs,
        outputs=node_request.outputs,
        source=node_request.raw_source,
        parameters=node_request.parameter_names,
    )
    code = render_node_function(task)

    assert "def merged_task(df, prepare_drop_columns):" in code
    assert "df.drop(columns=prepare_drop_columns)" in code
    assert "merged_task_drop_columns" not in code


@pytest.mark.parametrize(
    "source",
    [
        "X = df\ny = df['target']",
        "X = df.drop(columns=['target'])\ny = df.drop(columns=['other'])",
        "X = unsupported(columns=['target'])",
    ],
)
def test_missing_or_ambiguous_locations_fail_closed(
    node_request: NodeCodeRequest, source: str
) -> None:
    with pytest.raises(ValueError, match="exactly one source expression"):
        build_parameter_evidence(replace(node_request, raw_source=source))


def test_ambiguous_parameter_suffixes_are_rejected(node_request: NodeCodeRequest) -> None:
    request = replace(
        node_request,
        parameter_names=("first.drop_columns", "second.drop_columns"),
        parameter_arguments=("first_columns", "second_columns"),
    )
    with pytest.raises(ValueError, match="ambiguous parameter suffixes"):
        build_parameter_evidence(request)


def test_nonliteral_expression_is_not_evaluated(
    node_request: NodeCodeRequest, tmp_path: Path
) -> None:
    marker = tmp_path / "never-created"
    source = f"X = df.drop(columns=open({str(marker)!r}, 'w'))"
    with pytest.raises(ValueError, match="malformed node or string"):
        build_parameter_evidence(replace(node_request, raw_source=source))
    assert not marker.exists()


def test_no_parameters_need_no_substitutions(node_request: NodeCodeRequest) -> None:
    assert (
        build_parameter_evidence(replace(node_request, parameter_names=(), parameter_arguments=()))
        == ()
    )


def test_ambiguous_evidence_fails_before_http(node_request: NodeCodeRequest) -> None:
    provider = OllamaNodeCodeProvider(
        "not-downloaded-model", base_url="http://localhost:1", include_parameter_evidence=True
    )
    with pytest.raises(ValueError, match="exactly one source expression"):
        provider.complete(replace(node_request, raw_source="X = df"))


def test_all_v1_parameter_locations_match_generator() -> None:
    corpus = load_planning_corpus(ROOT / "tests/fixtures/evaluation/planning/v1")
    task_count = 0
    parameter_count = 0
    for case in corpus:
        plan = plan_notebook_path(ROOT / case.notebook_path, project_root=ROOT)
        for task in plan.task_candidates:
            request = build_node_code_request(plan, task.id, request_id=f"{case.case_id}:{task.id}")
            items = build_parameter_evidence(request)
            task_count += 1
            parameter_count += len(items)
            assert {item.parameter_name for item in items} == set(task.parameters)
            expected_source = task.source
            for item in reversed(items):
                assert task.source[item.start_offset : item.end_offset] == item.source_expression
                expected_source = (
                    expected_source[: item.start_offset]
                    + item.function_argument
                    + expected_source[item.end_offset :]
                )
            assert all(line in render_node_function(task) for line in expected_source.splitlines())
    assert task_count == 26
    assert parameter_count > 0
