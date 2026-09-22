"""Contract tests for versioned semantic planning response fixtures."""

from pathlib import Path

import pytest

from notebook_to_kedro.exceptions import SemanticPlanningResponseError
from notebook_to_kedro.semantic import SemanticPlanningResponse

FIXTURE_DIRECTORY = Path(__file__).parents[1] / "fixtures" / "semantic" / "planning" / "v1"


def test_valid_semantic_planning_response_fixture() -> None:
    response = SemanticPlanningResponse.from_json(
        (FIXTURE_DIRECTORY / "valid_response.json").read_text(encoding="utf-8")
    )

    assert response.schema_version == "1.0"
    assert response.tasks[0].node_name == "prepare_data"


def test_invalid_semantic_planning_response_fixture() -> None:
    payload = (FIXTURE_DIRECTORY / "invalid_extra_field.json").read_text(encoding="utf-8")

    with pytest.raises(SemanticPlanningResponseError, match="untrusted_metadata"):
        SemanticPlanningResponse.from_json(payload)
