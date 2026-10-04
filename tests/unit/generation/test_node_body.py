import ast
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from notebook_to_kedro.evaluation import load_node_code_corpus
from notebook_to_kedro.generation.code import (
    NODE_BODY_ASSEMBLY_VERSION,
    NODE_BODY_RESPONSE_JSON_SCHEMA,
    NODE_BODY_SCHEMA_VERSION,
    NodeBodyResponse,
    NodeCodeRequest,
    NodeCodeResponse,
    assemble_node_body,
)


@pytest.fixture
def node_request() -> NodeCodeRequest:
    return NodeCodeRequest(
        schema_version="1.0",
        request_id="body-1",
        task_id="task-1",
        node_name="scale",
        raw_source="scaled = values\nscaled",
        source_cell_ids=("cell-1",),
        statement_ids=("cell-1-stmt-0", "cell-1-stmt-1"),
        inputs=("values",),
        outputs=("scaled",),
    )


@pytest.fixture
def response(node_request: NodeCodeRequest) -> NodeBodyResponse:
    return NodeBodyResponse(
        NODE_BODY_SCHEMA_VERSION,
        node_request.request_id,
        node_request.task_id,
        node_request.raw_source,
        ("Execution still requires explicit consent.",),
    )


def test_body_contract_roundtrip_schema_and_immutability(response: NodeBodyResponse) -> None:
    assert NODE_BODY_SCHEMA_VERSION == "1.0"
    assert NODE_BODY_ASSEMBLY_VERSION == "node-body-assembly-v1"
    assert NodeBodyResponse.from_json(response.to_json()) == response
    assert NodeBodyResponse.from_json(response.to_json(indent=None)) == response
    assert response.to_json() == response.to_json()
    assert NODE_BODY_RESPONSE_JSON_SCHEMA["additionalProperties"] is False
    required = NODE_BODY_RESPONSE_JSON_SCHEMA["required"]
    properties = NODE_BODY_RESPONSE_JSON_SCHEMA["properties"]
    assert isinstance(required, list)
    assert isinstance(properties, dict)
    assert set(required) == set(properties) == set(json.loads(response.to_json()))
    assert properties["schema_version"]["const"] == response.schema_version
    assert properties["body_code"]["pattern"] == r"\S"
    assert properties["review_notes"]["uniqueItems"] is True
    with pytest.raises(FrozenInstanceError):
        response.body_code = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="fields"):
        NodeCodeResponse.from_json(response.to_json())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("request_id", " "),
        ("task_id", ""),
        ("body_code", "\n\t"),
        ("review_notes", ("",)),
        ("review_notes", ("note", "note")),
    ],
)
def test_body_contract_rejects_invalid_values(
    response: NodeBodyResponse, field: str, value: object
) -> None:
    with pytest.raises(ValueError, match=field):
        replace(response, **{field: value})  # type: ignore[arg-type]


@pytest.mark.parametrize("payload", ["not-json", "[]", "{}", '{"task_id":"a","task_id":"b"}'])
def test_body_decoder_rejects_invalid_objects(payload: str) -> None:
    with pytest.raises(ValueError, match=r"Expecting|fields|duplicate"):
        NodeBodyResponse.from_json(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("body_code", 1),
        ("review_notes", "note"),
        ("review_notes", [1]),
        ("imports", []),
        ("function_code", "def scale(values): pass"),
        ("extra", True),
    ],
)
def test_body_decoder_rejects_extra_fields_and_types(
    response: NodeBodyResponse, field: str, value: object
) -> None:
    data = json.loads(response.to_json())
    data[field] = value
    with pytest.raises(ValueError, match=r"must|fields"):
        NodeBodyResponse.from_json(json.dumps(data))


def test_body_decoder_requires_review_notes(response: NodeBodyResponse) -> None:
    data = json.loads(response.to_json())
    del data["review_notes"]
    with pytest.raises(ValueError, match="fields"):
        NodeBodyResponse.from_json(json.dumps(data))


@pytest.mark.parametrize("field", ["request_id", "task_id"])
def test_assembly_rejects_identity_mismatch(
    node_request: NodeCodeRequest, response: NodeBodyResponse, field: str
) -> None:
    with pytest.raises(ValueError, match="identity"):
        assemble_node_body(node_request, replace(response, **{field: "other"}))  # type: ignore[arg-type]


@pytest.mark.parametrize("outputs", [(), ("scaled",), ("scaled", "values")])
def test_assembly_adds_exact_interface_and_return(
    node_request: NodeCodeRequest, response: NodeBodyResponse, outputs: tuple[str, ...]
) -> None:
    request = replace(node_request, outputs=outputs)
    assembled = assemble_node_body(request, response)
    function = ast.parse(assembled.function_code).body[0]
    assert isinstance(function, ast.FunctionDef)
    assert function.name == request.node_name
    assert tuple(arg.arg for arg in function.args.args) == request.arguments
    assert ast.dump(ast.Module(body=function.body[:-1], type_ignores=[])) == ast.dump(
        ast.parse(response.body_code)
    )
    output = ", ".join(outputs) if outputs else "None"
    assert ast.dump(function.body[-1]) == ast.dump(ast.parse(f"return {output}").body[0])
    assert assembled.imports == ()
    assert assembled.review_notes == response.review_notes
    assert assembled.request_id == request.request_id
    assert assembled.task_id == request.task_id
    assert assemble_node_body(request, response) == assembled


@pytest.mark.parametrize(
    "body",
    [
        "scaled = values\nassert scaled > 0, 'positive'\nscaled",
        "scaled = values\nprint(scaled)\nscaled",
        'scaled = "first\\nsecond"\r\nscaled',
        'scaled = """first\n    second\nthird"""\nscaled',
        "scaled = 'caf\u00e9'\nscaled",
        "scaled = values\nif values:\n    scaled = sum(values)",
        "scaled = values\nfor value in values:\n    scaled += value",
    ],
)
def test_assembly_preserves_values_statements_and_multiline_strings(
    node_request: NodeCodeRequest, response: NodeBodyResponse, body: str
) -> None:
    result = assemble_node_body(
        replace(node_request, raw_source=body), replace(response, body_code=body)
    )
    function = ast.parse(result.function_code).body[0]
    assert isinstance(function, ast.FunctionDef)
    assert ast.dump(ast.Module(body=function.body[:-1], type_ignores=[])) == ast.dump(
        ast.parse(body)
    )


def test_assembly_normalizes_comments_and_formatting(
    node_request: NodeCodeRequest, response: NodeBodyResponse
) -> None:
    assembled = assemble_node_body(
        node_request, replace(response, body_code="# retained operations\nscaled=(values); scaled")
    )
    assert (
        assembled.function_code
        == "def scale(values):\n    scaled = values\n    scaled\n    return scaled\n"
    )


@pytest.mark.parametrize(
    "body",
    [
        "scaled = values",  # Omission of the notebook display expression.
        "scaled = values\nscaled\nscaled",
        "scaled\nscaled = values",
        "scaled = values + 1\nscaled",
        "scaled = values\nprint(scaled)\nscaled",
    ],
)
def test_assembly_does_not_repair_omitted_added_or_changed_statements(
    node_request: NodeCodeRequest, response: NodeBodyResponse, body: str
) -> None:
    with pytest.raises(ValueError, match="preserve source AST"):
        assemble_node_body(node_request, replace(response, body_code=body))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("# no statements", "contain statements"),
        ("scaled = (", "Invalid node body"),
        ("break", "Invalid node code"),
        ("def scale(values):\n    scaled = values", "nested"),
        ("import math\nscaled = values\nscaled", "unsupported"),
        ("scaled = values\nscaled\nreturn scaled", "terminal return"),
        ("if values:\n    return values\nscaled = values\nscaled", "terminal return"),
        ("scaled = (lambda: values)()\nscaled", "unsupported"),
        ("scaled = mystery(values)\nscaled", "unknown global"),
    ],
)
def test_assembly_rejects_invalid_bodies(
    node_request: NodeCodeRequest, response: NodeBodyResponse, body: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        assemble_node_body(node_request, replace(response, body_code=body))


@pytest.mark.parametrize(
    ("permissions", "body", "expected"),
    [
        (
            ("import math", "import unused_dependency"),
            "scaled = math.sqrt(values)",
            ("import math",),
        ),
        (("import xml.etree",), "scaled = xml.etree", ("import xml.etree",)),
        (("import math as maths",), "scaled = maths.sqrt(values)", ("import math as maths",)),
        (
            ("from math import sqrt as root",),
            "scaled = root(values)",
            ("from math import sqrt as root",),
        ),
        (("from math import sqrt",), "scaled = sqrt(values)", ("from math import sqrt",)),
        (("import math, os",), "scaled = math.sqrt(values)", ("import math, os",)),
        (("import math",), "scaled = [math.sqrt(x) for x in values]", ("import math",)),
        (
            ("import math",),
            "scaled = [[math.sqrt(x) for x in row] for row in values]",
            ("import math",),
        ),
        (("import math",), "math = values\nscaled = math", ()),
        (("import values",), "scaled = values", ()),
        (
            ("from custom_module import sum",),
            "scaled = sum(values)",
            ("from custom_module import sum",),
        ),
        (
            ("from math import sqrt as z", "import math as a"),
            "scaled = z(values) + a.pi",
            ("from math import sqrt as z", "import math as a"),
        ),
    ],
)
def test_assembly_selects_only_referenced_allowed_imports_in_request_order(
    node_request: NodeCodeRequest,
    response: NodeBodyResponse,
    permissions: tuple[str, ...],
    body: str,
    expected: tuple[str, ...],
) -> None:
    result = assemble_node_body(
        replace(node_request, raw_source=body, allowed_imports=permissions),
        replace(response, body_code=body),
    )
    assert result.imports == expected


@pytest.mark.parametrize(
    "permissions",
    [("x = 1",), ("from math import *",), ("from .math import sqrt",), ("import (",)],
)
def test_assembly_rejects_invalid_permissions_even_when_unused(
    node_request: NodeCodeRequest, response: NodeBodyResponse, permissions: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match="Invalid node body"):
        assemble_node_body(replace(node_request, allowed_imports=permissions), response)


def test_assembly_rejects_ambiguous_import_bindings(
    node_request: NodeCodeRequest, response: NodeBodyResponse
) -> None:
    body = "scaled = math(values)"
    request = replace(
        node_request,
        raw_source=body,
        allowed_imports=("import math", "from math import sqrt as math"),
    )
    with pytest.raises(ValueError, match="collision"):
        assemble_node_body(request, replace(response, body_code=body))


def test_assembly_requires_exact_parameter_substitution() -> None:
    root = Path(__file__).parents[2] / "fixtures/generation/code/v1"
    request = NodeCodeRequest.from_json((root / "request.json").read_text(encoding="utf-8"))
    response = NodeBodyResponse(
        "1.0",
        request.request_id,
        request.task_id,
        'X = df.drop(columns=prepare_features_drop_columns)\ny = df["target"]',
    )
    result = assemble_node_body(request, response)
    reference = NodeCodeResponse.from_json((root / "response.json").read_text(encoding="utf-8"))
    assert ast.dump(ast.parse(result.function_code)) == ast.dump(ast.parse(reference.function_code))
    for body in (request.raw_source, response.body_code.replace('df["target"]', 'df["other"]')):
        with pytest.raises(ValueError, match="preserve source AST"):
            assemble_node_body(request, replace(response, body_code=body))


def test_assembly_does_not_execute_imports_or_body(
    node_request: NodeCodeRequest, response: NodeBodyResponse, tmp_path: Path
) -> None:
    marker = tmp_path / "must-not-exist"
    body = f"open({str(marker)!r}, 'w').close()\nscaled = unavailable_module(values)"
    result = assemble_node_body(
        replace(node_request, raw_source=body, allowed_imports=("import unavailable_module",)),
        replace(response, body_code=body),
    )
    assert result.imports == ("import unavailable_module",)
    assert not marker.exists()
    with pytest.raises(ValueError, match="preserve source AST"):
        assemble_node_body(
            node_request,
            replace(
                response, body_code=f"open({str(marker)!r}, 'w').close()\n" + response.body_code
            ),
        )
    assert not marker.exists()


def test_assembly_accepts_all_eight_reviewed_reference_bodies() -> None:
    nodes = load_node_code_corpus(Path("tests/fixtures/evaluation/node_code/v2"))
    assert len(nodes) == 8
    for node in nodes:
        function = ast.parse(node.reference_response.function_code).body[0]
        assert isinstance(function, ast.FunctionDef)
        body = ast.unparse(ast.Module(body=function.body[:-1], type_ignores=[]))
        response = NodeBodyResponse("1.0", node.request.request_id, node.request.task_id, body)
        result = assemble_node_body(node.request, response)
        assert ast.dump(ast.parse(result.function_code)) == ast.dump(
            ast.parse(node.reference_response.function_code)
        )
        assert result.imports == node.reference_response.imports
