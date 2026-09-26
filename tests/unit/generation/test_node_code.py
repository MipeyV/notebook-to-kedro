"""Offline contract and validation checks for untrusted node code proposals."""

import ast
import json
from dataclasses import replace
from pathlib import Path
from textwrap import indent

import pytest

from notebook_to_kedro import plan_notebook_path
from notebook_to_kedro.evaluation import load_planning_corpus
from notebook_to_kedro.generation import generate_kedro_project
from notebook_to_kedro.generation.code import (
    NODE_CODE_RESPONSE_JSON_SCHEMA,
    FakeNodeCodeProvider,
    NodeCodeProvider,
    NodeCodeRequest,
    NodeCodeResponse,
    build_node_code_request,
    request_node_code,
    validate_node_code,
)


@pytest.fixture
def node_request() -> NodeCodeRequest:
    return NodeCodeRequest(
        schema_version="1.0",
        request_id="code-1",
        task_id="task-1",
        node_name="scale",
        raw_source="scaled = values * 2",
        source_cell_ids=("cell-1",),
        statement_ids=("cell-1-stmt-0",),
        inputs=("values",),
        outputs=("scaled",),
        parameter_names=("scale.factor",),
        parameter_arguments=("scale_factor",),
        allowed_imports=("import math", "from math import sqrt as root"),
    )


@pytest.fixture
def response() -> NodeCodeResponse:
    return NodeCodeResponse(
        schema_version="1.0",
        request_id="code-1",
        task_id="task-1",
        function_code=(
            "def scale(values, scale_factor):\n"
            "    scaled = values * scale_factor\n    return scaled\n"
        ),
    )


def test_contract_round_trips_and_response_schema(
    node_request: NodeCodeRequest, response: NodeCodeResponse
) -> None:
    assert NodeCodeRequest.from_json(node_request.to_json()) == node_request
    assert NodeCodeResponse.from_json(response.to_json(indent=None)) == response
    assert node_request.to_json() == node_request.to_json()
    required = NODE_CODE_RESPONSE_JSON_SCHEMA["required"]
    assert isinstance(required, list)
    assert set(required) == set(json.loads(response.to_json()))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "2.0", "schema_version"),
        ("request_id", " ", "must not be empty"),
        ("task_id", "", "must not be empty"),
        ("raw_source", "", "required"),
        ("source_cell_ids", (), "required"),
        ("statement_ids", (), "required"),
        ("source_cell_ids", ("a", "a"), "unique"),
        ("allowed_imports", (" ",), "non-empty"),
        ("node_name", "for", "identifiers"),
        ("node_name", "_private", "public"),
        ("inputs", ("not-valid",), "identifiers"),
        ("parameter_arguments", ("values",), "function arguments"),
        ("parameter_arguments", (), "matching lengths"),
    ],
)
def test_request_rejects_invalid_contract(
    node_request: NodeCodeRequest, field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(node_request, **{field: value})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("request_id", ""),
        ("task_id", " "),
        ("function_code", " "),
        ("imports", ("import math", "import math")),
        ("review_notes", ("",)),
    ],
)
def test_response_rejects_invalid_contract(
    response: NodeCodeResponse, field: str, value: object
) -> None:
    with pytest.raises(ValueError, match=field):
        replace(response, **{field: value})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "[]",
        "{}",
        '{"request_id":"a","request_id":"b"}',
    ],
)
def test_both_decoders_reject_malformed_objects(payload: str) -> None:
    for contract in (NodeCodeRequest, NodeCodeResponse):
        with pytest.raises(ValueError, match=r"Expecting|fields|duplicate"):
            contract.from_json(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_id", 1),
        ("imports", "import math"),
        ("review_notes", [1]),
        ("extra", True),
    ],
)
def test_response_decoder_checks_types_and_unknown_fields(
    response: NodeCodeResponse, field: str, value: object
) -> None:
    data = json.loads(response.to_json())
    data[field] = value
    with pytest.raises(ValueError, match=r"must|fields"):
        NodeCodeResponse.from_json(json.dumps(data))


def test_request_builder_preserves_plan_provenance_and_parameter_mapping() -> None:
    path = Path(__file__).parents[2] / "fixtures/notebooks/simple_training.ipynb"
    plan = plan_notebook_path(path)
    task = plan.task_candidates[1]
    node_request = build_node_code_request(plan, task.id, request_id="code-1")
    assert node_request.raw_source == task.source
    assert node_request.source_cell_ids == task.source_cell_ids
    assert node_request.statement_ids == task.statement_ids
    assert node_request.parameter_names == task.parameters
    assert node_request.arguments == ("df", "prepare_features_drop_columns")
    assert node_request.allowed_imports == plan.imports
    with pytest.raises(ValueError, match="unknown task"):
        build_node_code_request(plan, "missing", request_id="code-1")
    with pytest.raises(ValueError, match="blocking"):
        build_node_code_request(
            replace(plan, blocking_diagnostic_codes=("PY002",)), task.id, request_id="code-1"
        )


def test_service_accepts_valid_code_and_records_application_provenance(
    node_request: NodeCodeRequest, response: NodeCodeResponse
) -> None:
    provider: NodeCodeProvider = FakeNodeCodeProvider(response_json=response.to_json())
    result = request_node_code(node_request, provider)
    assert result.request == node_request
    assert result.response == response
    assert result.provider_name == "fake"
    assert result.model_name == "fixed-response"
    assert isinstance(provider, FakeNodeCodeProvider)
    assert provider.requests == (node_request,)


def test_service_propagates_provider_and_validation_errors(
    node_request: NodeCodeRequest, response: NodeCodeResponse
) -> None:
    error = RuntimeError("offline")
    provider = FakeNodeCodeProvider(error=error)
    with pytest.raises(RuntimeError) as captured:
        request_node_code(node_request, provider)
    assert captured.value is error
    assert provider.requests == (node_request,)
    for payload in ("not-json", replace(response, request_id="other").to_json()):
        with pytest.raises(ValueError, match=r"Expecting|identity"):
            request_node_code(node_request, FakeNodeCodeProvider(response_json=payload))


def test_fake_provider_rejects_ambiguous_configuration() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        FakeNodeCodeProvider()
    with pytest.raises(ValueError, match="exactly one"):
        FakeNodeCodeProvider(response_json="{}", error=RuntimeError())
    with pytest.raises(ValueError, match="model_name"):
        FakeNodeCodeProvider(response_json="{}", model_name=" ")


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("def scale(:", "Invalid node code"),
        ("scaled = 1", "exactly one"),
        ("async def scale(values, scale_factor):\n    return scaled", "synchronous"),
        ("def other(values, scale_factor):\n    return scaled", "function name"),
        ("def scale(scale_factor, values):\n    return scaled", "signature"),
        ("def scale(values, scale_factor=2):\n    return scaled", "signature"),
        ("def scale(values, /, scale_factor):\n    return scaled", "signature"),
        ("def scale(values, *, scale_factor):\n    return scaled", "signature"),
        ("def scale(values, scale_factor, *args):\n    return scaled", "signature"),
        ("def scale(values, scale_factor, **kwargs):\n    return scaled", "signature"),
        ("@decorator\ndef scale(values, scale_factor):\n    return scaled", "decorators"),
        ("def scale(values: int, scale_factor):\n    return scaled", "annotations"),
        ("def scale(values, scale_factor) -> int:\n    return scaled", "annotations"),
        ("def scale(values, scale_factor):\n    import math\n    return scaled", "unsupported"),
        ("def scale(values, scale_factor):\n    global scaled\n    return scaled", "unsupported"),
        (
            "def scale(values, scale_factor):\n    def helper():\n        pass\n    return scaled",
            "nested",
        ),
        ("def scale(values, scale_factor):\n    yield values\n    return scaled", "unsupported"),
        ("def scale(values, scale_factor):\n    pass", "terminal return"),
        (
            "def scale(values, scale_factor):\n"
            "    if values:\n        return values\n    return scaled",
            "terminal return",
        ),
        ("def scale(values, scale_factor):\n    return values", "ordered output"),
        (
            "def scale(values, scale_factor):\n    scaled = mystery(values)\n    return scaled",
            "unknown global",
        ),
        (
            "def scale(values, scale_factor):\n"
            "    scaled = [missing(x) for x in values]\n    return scaled",
            "unknown global",
        ),
        ("def scale(values, scale_factor):\n    break\n    return scaled", "Invalid node code"),
        (
            "print('side effect')\ndef scale(values, scale_factor):\n    return scaled",
            "exactly one",
        ),
    ],
)
def test_validator_rejects_invalid_function(
    node_request: NodeCodeRequest, response: NodeCodeResponse, code: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_node_code(node_request, replace(response, function_code=code))


@pytest.mark.parametrize(
    ("original", "proposed"),
    [
        ("scaled = values * 2\nassert scaled > 0", "scaled = values * 2"),
        ("scaled = values * 2\nassert scaled > 0", "scaled = values * 2\nassert scaled >= 0"),
        ("scaled = values * 2\nassert scaled > 0", "scaled = values * 2\nassert True"),
        (
            "scaled = values * 2\nassert scaled > 0, 'positive'",
            "scaled = values * 2\nassert scaled > 0, 'different'",
        ),
        (
            "scaled = values * 2\nassert scaled > 0, 'positive'",
            "scaled = values * 2\nassert scaled > 0",
        ),
        (
            "scaled = values * 2\nassert scaled > 0\nscaled",
            "scaled = values * 2\nscaled\nassert scaled > 0",
        ),
        (
            "scaled = values * 2\nassert scaled > 0",
            "scaled = values * 2\nassert scaled > 0\nassert scaled > 0",
        ),
        (
            "scaled = values * 2\nassert scaled > 0",
            "scaled = values * 2\nif False:\n    assert scaled > 0",
        ),
        (
            "scaled = values * 2\nif values:\n    assert scaled > 0",
            "scaled = values * 2\nif not values:\n    assert scaled > 0",
        ),
        (
            "scaled = values * 2\nassert scaled > 0",
            "scaled = values * 2\ntry:\n    assert scaled > 0\nexcept AssertionError:\n    pass",
        ),
        (
            "scaled = values * 2\nassert scaled > 0\nassert values > 0",
            "scaled = values * 2\nassert values > 0\nassert scaled > 0",
        ),
        ("scaled = values * 2", "scaled = values * 2\nassert scaled > 0"),
        (
            "scaled = values\nif values:\n    scaled = values * 2\n    assert scaled > 0",
            "scaled = values\nif values:\n"
            "    scaled = values * scale_factor\n    assert scaled > 0",
        ),
    ],
)
def test_validator_rejects_changed_assertion_blocks(
    node_request: NodeCodeRequest, response: NodeCodeResponse, original: str, proposed: str
) -> None:
    code = "def scale(values, scale_factor):\n" + indent(proposed, "    ") + "\n    return scaled"
    with pytest.raises(ValueError, match="assertions and their enclosing statements"):
        validate_node_code(
            replace(node_request, raw_source=original), replace(response, function_code=code)
        )


@pytest.mark.parametrize(
    "body",
    [
        "scaled = values * 2\nassert scaled > 0, 'positive'",
        "scaled = values\nif values:\n    assert values > 0\n    scaled = values * 2",
        "scaled = values\nfor value in values:\n    assert value > 0",
        "scaled = values\nassert values >= 1.0\nvalues",
    ],
)
def test_validator_preserves_assertions_without_executing_them(
    node_request: NodeCodeRequest, response: NodeCodeResponse, body: str
) -> None:
    code = "def scale(values, scale_factor):\n" + indent(body, "    ") + "\n    return scaled"
    validate_node_code(
        replace(node_request, raw_source=body), replace(response, function_code=code)
    )


def test_assertion_comparison_ignores_comments_and_formatting(
    node_request: NodeCodeRequest, response: NodeCodeResponse
) -> None:
    original = "scaled = values * 2\nassert scaled > 0, 'positive'"
    code = (
        "def scale(values, scale_factor):\n"
        "    scaled = values * 2\n"
        '    assert (scaled > 0), "positive"  # preserved check\n'
        "    return scaled\n"
    )
    validate_node_code(
        replace(node_request, raw_source=original), replace(response, function_code=code)
    )


def test_invalid_original_source_is_rejected(
    node_request: NodeCodeRequest, response: NodeCodeResponse
) -> None:
    with pytest.raises(ValueError, match="Invalid node code"):
        validate_node_code(replace(node_request, raw_source="assert ("), response)


def test_allowed_import_cannot_be_duplicated_inside_function(
    node_request: NodeCodeRequest, response: NodeCodeResponse
) -> None:
    code = (
        "def scale(values, scale_factor):\n    import math\n    scaled = values\n    return scaled"
    )
    with pytest.raises(ValueError, match="unsupported nested scope, import"):
        validate_node_code(
            node_request, replace(response, imports=("import math",), function_code=code)
        )


@pytest.mark.parametrize(
    ("imports", "message"),
    [
        (("import os",), "unauthorized"),
        (("import math; print('side effect')",), "exactly one import"),
        (("from math import *",), "wildcard"),
        (("from .math import sqrt",), "relative"),
    ],
)
def test_validator_rejects_invalid_imports(
    node_request: NodeCodeRequest,
    response: NodeCodeResponse,
    imports: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_node_code(node_request, replace(response, imports=imports))


def test_validator_rejects_import_binding_collisions(
    node_request: NodeCodeRequest, response: NodeCodeResponse
) -> None:
    for imports in (("import math as scale",), ("import math", "from math import sqrt as math")):
        with pytest.raises(ValueError, match="collision"):
            validate_node_code(
                replace(node_request, allowed_imports=imports), replace(response, imports=imports)
            )


@pytest.mark.parametrize(
    ("imports", "expression"),
    [
        (("import math",), "math.sqrt(values)"),
        (("from math import sqrt as root",), "root(values)"),
        (("from math import sqrt",), "sqrt(values)"),
        (("import math as maths",), "maths.sqrt(values)"),
        ((), "[x * scale_factor for x in values]"),
        ((), "sum(values) * scale_factor"),
    ],
)
def test_validator_accepts_imports_builtins_and_comprehension_scopes(
    node_request: NodeCodeRequest,
    response: NodeCodeResponse,
    imports: tuple[str, ...],
    expression: str,
) -> None:
    code = f"def scale(values, scale_factor):\n    scaled = {expression}\n    return scaled"
    validate_node_code(
        replace(node_request, allowed_imports=imports),
        replace(response, imports=imports, function_code=code),
    )


def test_contract_accepts_existing_v1_generated_nodes(tmp_path: Path) -> None:
    corpus = Path(__file__).parents[2] / "fixtures/evaluation/planning/v1"
    for case in load_planning_corpus(corpus):
        plan = plan_notebook_path(case.notebook_path)
        destination = tmp_path / case.case_id
        generate_kedro_project(plan, destination)
        source = (
            destination / "src/generated_notebook/pipelines/notebook_pipeline/nodes.py"
        ).read_text(encoding="utf-8")
        functions = {
            node.name: node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
        }
        for task in plan.task_candidates:
            request = build_node_code_request(plan, task.id, request_id=f"code-{task.id}")
            code = ast.get_source_segment(source, functions[task.name])
            assert code is not None
            response = NodeCodeResponse("1.0", request.request_id, task.id, code, plan.imports)
            validate_node_code(request, response)


@pytest.mark.parametrize(
    ("outputs", "code"),
    [
        ((), "def scale(values, scale_factor):\n    return None"),
        ((), "def scale(values, scale_factor):\n    return"),
        (
            ("values", "scale_factor"),
            "def scale(values, scale_factor):\n    return values, scale_factor",
        ),
    ],
)
def test_validator_accepts_zero_or_multiple_outputs(
    node_request: NodeCodeRequest, response: NodeCodeResponse, outputs: tuple[str, ...], code: str
) -> None:
    validate_node_code(
        replace(node_request, outputs=outputs), replace(response, function_code=code)
    )


def test_validation_does_not_import_or_execute_code(
    node_request: NodeCodeRequest, response: NodeCodeResponse, tmp_path: Path
) -> None:
    target = tmp_path / "must-not-exist"
    code = (
        f"def scale(values, scale_factor):\n    open({str(target)!r}, 'w')\n"
        "    scaled = values\n    return scaled"
    )
    request_node_code(
        node_request,
        FakeNodeCodeProvider(response_json=replace(response, function_code=code).to_json()),
    )
    assert not target.exists()
