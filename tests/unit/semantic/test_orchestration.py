"""Tests for safe semantic provider orchestration and fallback."""

from dataclasses import replace

import pytest

from notebook_to_kedro.exceptions import SemanticProviderError
from notebook_to_kedro.semantic import (
    FakeSemanticPlanningProvider,
    SemanticGroupingResponse,
    SemanticPlanningFailure,
    SemanticPlanningOutcome,
    SemanticPlanningRequest,
    SemanticPlanningResponse,
    SemanticPlanningResult,
    SemanticPlanningTrace,
    SemanticProviderRequest,
    request_semantic_planning,
    semantic_grouping_response_schema,
)


class _UnexpectedFailureProvider:
    provider_name = "broken"
    model_name = "broken-model"

    def complete(self, request: SemanticProviderRequest) -> str:
        raise RuntimeError(request.request_id)


def test_orchestration_accepts_and_traces_a_valid_response(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
    semantic_grouping_response: SemanticGroupingResponse,
) -> None:
    provider = FakeSemanticPlanningProvider(
        response_json=semantic_grouping_response.to_json(), model_name="semantic-fixture"
    )

    outcome = request_semantic_planning(semantic_request, provider)

    assert outcome.result is not None
    assert outcome.result.response == replace(semantic_response, review_notes=())
    assert outcome.trace.provider_name == "fake"
    assert outcome.trace.model_name == "semantic-fixture"
    assert outcome.failure is None
    assert outcome.fallback_plan is None
    assert outcome.used_fallback is False
    assert len(provider.requests) == 1
    provider_request = provider.requests[0]
    assert provider_request.request_id == semantic_request.request_id
    assert provider_request.response_schema == semantic_grouping_response_schema(semantic_request)
    assert semantic_request.request_id in provider_request.prompt
    assert "Compact planning evidence JSON:" in provider_request.prompt


def test_orchestration_falls_back_on_provider_failure(
    semantic_request: SemanticPlanningRequest,
) -> None:
    provider = FakeSemanticPlanningProvider(
        error=SemanticProviderError("provider_timeout", "request timed out")
    )

    outcome = request_semantic_planning(semantic_request, provider)

    assert outcome.result is None
    assert outcome.failure == SemanticPlanningFailure("provider_timeout", "request timed out")
    assert outcome.fallback_plan == semantic_request.baseline_plan
    assert outcome.used_fallback is True


@pytest.mark.parametrize(
    "response_json",
    [
        "not-json",
        SemanticGroupingResponse(
            schema_version="1.0",
            request_id="another-request",
            groups=(),
        ).to_json(),
    ],
)
def test_orchestration_falls_back_on_invalid_responses(
    semantic_request: SemanticPlanningRequest,
    response_json: str,
) -> None:
    provider = FakeSemanticPlanningProvider(response_json=response_json)

    outcome = request_semantic_planning(semantic_request, provider)

    assert outcome.result is None
    assert outcome.failure is not None
    assert outcome.failure.code == "invalid_response"
    assert "grouping response" in outcome.failure.message
    assert outcome.fallback_plan == semantic_request.baseline_plan


def test_orchestration_does_not_mask_unexpected_provider_errors(
    semantic_request: SemanticPlanningRequest,
) -> None:
    with pytest.raises(RuntimeError, match=semantic_request.request_id):
        request_semantic_planning(semantic_request, _UnexpectedFailureProvider())


def test_orchestration_rejects_an_unsupported_prompt_before_provider_call(
    semantic_request: SemanticPlanningRequest,
    semantic_grouping_response: SemanticGroupingResponse,
) -> None:
    provider = FakeSemanticPlanningProvider(response_json=semantic_grouping_response.to_json())
    request = replace(semantic_request, prompt_version="planning-unsupported")

    with pytest.raises(ValueError, match="unsupported semantic planning prompt version"):
        request_semantic_planning(request, provider)

    assert provider.requests == ()


@pytest.mark.parametrize(
    ("code", "message", "expected"),
    [("", "failure", "code must not be empty"), ("failed", "", "message must not be empty")],
)
def test_planning_failure_rejects_empty_fields(code: str, message: str, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        SemanticPlanningFailure(code, message)


def test_outcome_requires_exactly_one_result_or_failure(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    trace = _trace(semantic_request)
    result = SemanticPlanningResult(semantic_request, semantic_response, trace)
    failure = SemanticPlanningFailure("failed", "expected failure")

    with pytest.raises(ValueError, match="exactly one"):
        SemanticPlanningOutcome(semantic_request, trace)
    with pytest.raises(ValueError, match="exactly one"):
        SemanticPlanningOutcome(
            semantic_request,
            trace,
            result=result,
            failure=failure,
        )


def test_successful_outcome_rejects_fallback_or_mismatched_result(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
) -> None:
    trace = _trace(semantic_request)
    result = SemanticPlanningResult(semantic_request, semantic_response, trace)

    with pytest.raises(ValueError, match="must not contain a fallback plan"):
        SemanticPlanningOutcome(
            semantic_request,
            trace,
            result=result,
            fallback_plan=semantic_request.baseline_plan,
        )

    other_request = replace(semantic_request, request_id="other-request")
    with pytest.raises(ValueError, match="result must match"):
        SemanticPlanningOutcome(other_request, trace, result=result)


def test_failed_outcome_requires_the_baseline_fallback(
    semantic_request: SemanticPlanningRequest,
) -> None:
    failure = SemanticPlanningFailure("failed", "expected failure")

    with pytest.raises(ValueError, match="deterministic baseline plan"):
        SemanticPlanningOutcome(
            semantic_request,
            _trace(semantic_request),
            failure=failure,
        )


def _trace(request: SemanticPlanningRequest) -> SemanticPlanningTrace:
    return SemanticPlanningTrace(
        request_id=request.request_id,
        prompt_version=request.prompt_version,
        provider_name="fake",
        model_name="fixed-response",
    )
