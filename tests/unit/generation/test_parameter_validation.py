"""Reject misplaced substitutions without executing model proposals or source expressions."""

from dataclasses import replace
from pathlib import Path
from textwrap import indent

import pytest

from notebook_to_kedro.generation.code import (
    FakeNodeCodeProvider,
    NodeCodeRequest,
    NodeCodeResponse,
    request_node_code,
    validate_node_code,
)


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
        parameter_names=("original.drop_columns",),
        parameter_arguments=("columns_to_drop",),
    )


def _response(node_request: NodeCodeRequest, body: str) -> NodeCodeResponse:
    code = (
        f"def {node_request.node_name}({', '.join(node_request.arguments)}):\n"
        + indent(body, "    ")
        + f"\n    return {', '.join(node_request.outputs)}\n"
    )
    return NodeCodeResponse("1.0", node_request.request_id, node_request.task_id, code)


def test_exact_substitution_accepts_custom_argument_and_renamed_task(
    node_request: NodeCodeRequest,
) -> None:
    response = _response(node_request, "X = df.drop(columns=columns_to_drop)\ny = df['target']")
    result = request_node_code(node_request, FakeNodeCodeProvider(response_json=response.to_json()))
    assert result.response == response


@pytest.mark.parametrize(
    "body",
    [
        "X = df.drop(columns=['target'])\ny = df['target']",
        "X = df.drop(columns=[columns_to_drop])\ny = df['target']",
        "X = df.drop(columns=columns_to_drop[0])\ny = df['target']",
        "X = df.drop(columns=list(columns_to_drop))\ny = df['target']",
        "X = df.drop(columns=df)\ny = df['target']",
        "X = df.drop(columns=columns_to_drop)\ny = df[columns_to_drop]",
        "X = df.drop(columns=columns_to_drop)\ny = df['other']",
        "columns_to_drop = ['target']\nX = df.drop(columns=columns_to_drop)\ny = df['target']",
        "X = df.drop(columns=['target'])\ny = df['target']\ncolumns_to_drop",
        "X = df.drop(columns=columns_to_drop)\ny = df['target']\ncolumns_to_drop",
        "y = df['target']\nX = df.drop(columns=columns_to_drop)",
        "X = df.drop(columns=columns_to_drop).copy()\ny = df['target']",
        "if False:\n    X = df.drop(columns=columns_to_drop)\ny = df['target']",
        "'added docstring'\nX = df.drop(columns=columns_to_drop)\ny = df['target']",
    ],
)
def test_parameterized_body_rejects_unplanned_rewrites(
    node_request: NodeCodeRequest, body: str
) -> None:
    with pytest.raises(ValueError, match="exact parameter substitutions"):
        validate_node_code(node_request, _response(node_request, body))


def test_parameter_comparison_ignores_formatting_comments_and_quote_style(
    node_request: NodeCodeRequest,
) -> None:
    body = (
        "# preserved operations\nX = df.drop(\n    columns=(columns_to_drop),\n)\ny = df['target']"
    )
    validate_node_code(node_request, _response(node_request, body))


def test_parameter_comparison_handles_unicode_multiline_and_crlf(
    node_request: NodeCodeRequest,
) -> None:
    source = (
        'note = "caf\u00e9"; X = df.drop(columns=[\r\n'
        '    "cibl\u00e9",\r\n])\r\ny = df["cibl\u00e9"]'
    )
    node_request = replace(node_request, raw_source=source)
    body = 'note = "caf\u00e9"; X = df.drop(columns=columns_to_drop)\ny = df["cibl\u00e9"]'
    validate_node_code(node_request, _response(node_request, body))


@pytest.mark.parametrize("swapped", [False, True])
def test_equal_literals_use_site_specific_arguments(
    node_request: NodeCodeRequest, *, swapped: bool
) -> None:
    node_request = replace(
        node_request,
        raw_source="X = RandomForestClassifier(n_estimators=10, random_state=10)\ny = 10",
        inputs=("RandomForestClassifier",),
        parameter_names=("train.random_state", "train.n_estimators"),
        parameter_arguments=("seed", "count"),
    )
    args = (
        "n_estimators=seed, random_state=count"
        if swapped
        else "n_estimators=count, random_state=seed"
    )
    response = _response(node_request, f"X = RandomForestClassifier({args})\ny = 10")
    if swapped:
        with pytest.raises(ValueError, match="exact parameter substitutions"):
            validate_node_code(node_request, response)
    else:
        validate_node_code(node_request, response)


@pytest.mark.parametrize(
    ("source", "body", "parameter"),
    [
        ("X = df.fillna({'x': 0})", "X = df.fillna(argument)", "fillna_values"),
        ("X = df.fillna(value=0.5)", "X = df.fillna(value=argument)", "fillna_values"),
        ("X = df.drop(columns='x')", "X = df.drop(columns=argument)", "drop_columns"),
        ("X = df.drop(columns=('x', 'y'))", "X = df.drop(columns=argument)", "drop_columns"),
    ],
)
def test_whole_literal_replacement_preserves_call_style(
    node_request: NodeCodeRequest, source: str, body: str, parameter: str
) -> None:
    node_request = replace(
        node_request,
        raw_source=source,
        outputs=("X",),
        parameter_names=(f"prepare.{parameter}",),
        parameter_arguments=("argument",),
    )
    validate_node_code(node_request, _response(node_request, body))


@pytest.mark.parametrize(
    "source",
    [
        "X = df\ny = df['target']",
        "X = df.drop(columns=['target'])\ny = df.drop(columns=['other'])",
    ],
)
def test_missing_or_repeated_parameter_sites_fail_validation(
    node_request: NodeCodeRequest, source: str
) -> None:
    response = _response(node_request, "X = df.drop(columns=columns_to_drop)\ny = df['target']")
    with pytest.raises(
        ValueError, match="Invalid node code: parameter evidence requires exactly one"
    ):
        validate_node_code(replace(node_request, raw_source=source), response)


def test_ambiguous_parameter_names_fail_validation(node_request: NodeCodeRequest) -> None:
    node_request = replace(
        node_request,
        parameter_names=("first.drop_columns", "second.drop_columns"),
        parameter_arguments=("first_columns", "second_columns"),
    )
    with pytest.raises(ValueError, match="Invalid node code: ambiguous parameter suffixes"):
        validate_node_code(node_request, _response(node_request, "X = df\ny = df"))


@pytest.mark.parametrize("untrusted_source", [False, True])
def test_parameter_validation_never_executes_source_or_proposal(
    node_request: NodeCodeRequest, tmp_path: Path, *, untrusted_source: bool
) -> None:
    marker = tmp_path / "never-created"
    effect = f"open({str(marker)!r}, 'w').close()"
    if untrusted_source:
        node_request = replace(
            node_request, raw_source=f"X = df.drop(columns={effect})\ny = df['target']"
        )
        body = "X = df.drop(columns=columns_to_drop)\ny = df['target']"
        message = "malformed node or string"
    else:
        body = f"X = df.drop(columns=columns_to_drop)\ny = df['target']\n{effect}"
        message = "exact parameter substitutions"
    with pytest.raises(ValueError, match=message):
        request_node_code(
            node_request,
            FakeNodeCodeProvider(response_json=_response(node_request, body).to_json()),
        )
    assert not marker.exists()


def test_assertion_block_guard_remains_stricter_than_parameter_replacement(
    node_request: NodeCodeRequest,
) -> None:
    node_request = replace(
        node_request,
        raw_source=(
            "if True:\n    X = df.drop(columns=['target'])\n    assert len(X) > 0\ny = df['target']"
        ),
    )
    body = (
        "if True:\n    X = df.drop(columns=columns_to_drop)\n"
        "    assert len(X) > 0\ny = df['target']"
    )
    with pytest.raises(ValueError, match="assertions and their enclosing statements"):
        validate_node_code(node_request, _response(node_request, body))
