"""Tests for semantic provider transport and the deterministic fake."""

import pytest

from notebook_to_kedro.exceptions import SemanticProviderError
from notebook_to_kedro.semantic import (
    FakeSemanticPlanningProvider,
    SemanticPlanningProvider,
    SemanticProviderRequest,
)


def _provider_request(**overrides: object) -> SemanticProviderRequest:
    values: dict[str, object] = {
        "request_id": "request-0001",
        "prompt": "Return JSON.",
        "response_schema": {"type": "object"},
    }
    values.update(overrides)
    return SemanticProviderRequest(**values)  # type: ignore[arg-type]


def test_fake_provider_implements_protocol_and_records_requests() -> None:
    provider: SemanticPlanningProvider = FakeSemanticPlanningProvider(response_json='{"ok":true}')
    request = _provider_request()

    assert provider.complete(request) == '{"ok":true}'
    assert isinstance(provider, FakeSemanticPlanningProvider)
    assert provider.provider_name == "fake"
    assert provider.model_name == "fixed-response"
    assert provider.requests == (request,)


def test_fake_provider_raises_configured_error_after_recording() -> None:
    error = SemanticProviderError("provider_timeout", "request exceeded its deadline")
    provider = FakeSemanticPlanningProvider(error=error, model_name="timeout-simulator")
    request = _provider_request()

    with pytest.raises(SemanticProviderError) as error_info:
        provider.complete(request)

    assert error_info.value is error
    assert provider.requests == (request,)
    assert str(error) == "provider_timeout: request exceeded its deadline"
    assert error.code == "provider_timeout"
    assert error.message == "request exceeded its deadline"


@pytest.mark.parametrize(
    ("response_json", "error"),
    [(None, None), ("{}", SemanticProviderError("failed", "expected failure"))],
)
def test_fake_provider_requires_exactly_one_behavior(
    response_json: str | None,
    error: SemanticProviderError | None,
) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        FakeSemanticPlanningProvider(response_json=response_json, error=error)


def test_fake_provider_rejects_an_empty_model_name() -> None:
    with pytest.raises(ValueError, match="model_name must not be empty"):
        FakeSemanticPlanningProvider(response_json="{}", model_name="")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"request_id": ""}, "request_id must not be empty"),
        ({"prompt": ""}, "prompt must not be empty"),
        ({"response_schema": {}}, "response_schema must not be empty"),
    ],
)
def test_provider_request_rejects_empty_fields(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _provider_request(**changes)


@pytest.mark.parametrize(
    ("code", "message", "expected"),
    [("", "failure", "code must not be empty"), ("failed", "", "message must not be empty")],
)
def test_provider_error_rejects_empty_fields(code: str, message: str, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        SemanticProviderError(code, message)
