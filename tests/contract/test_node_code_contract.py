"""Versioned node code fixtures stay compatible with the offline contract."""

from pathlib import Path

from notebook_to_kedro.generation.code import (
    FakeNodeCodeProvider,
    NodeCodeRequest,
    request_node_code,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/generation/code/v1"


def test_versioned_node_code_fixture() -> None:
    request = NodeCodeRequest.from_json((FIXTURES / "request.json").read_text(encoding="utf-8"))
    provider = FakeNodeCodeProvider(
        response_json=(FIXTURES / "response.json").read_text(encoding="utf-8")
    )

    result = request_node_code(request, provider)

    assert result.request.arguments == ("df", "prepare_features_drop_columns")
    assert result.request.outputs == ("X", "y")
    assert result.response.task_id == "task-0005"
    assert result.response.review_notes
