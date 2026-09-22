"""Safe orchestration around untrusted semantic planning providers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import SemanticPlanningResponseError, SemanticProviderError
from notebook_to_kedro.semantic.contracts import (
    SemanticPlanningRequest,
    SemanticPlanningResponse,
    SemanticPlanningResult,
    SemanticPlanningTrace,
)
from notebook_to_kedro.semantic.prompting import render_semantic_planning_prompt
from notebook_to_kedro.semantic.providers import SemanticProviderRequest
from notebook_to_kedro.semantic.schemas import SEMANTIC_PLANNING_RESPONSE_JSON_SCHEMA
from notebook_to_kedro.semantic.suggestion_validation import (
    validate_semantic_planning_response,
)

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan
    from notebook_to_kedro.semantic.protocols import SemanticPlanningProvider


@dataclass(frozen=True, slots=True)
class SemanticPlanningFailure:
    """Expected failure that caused deterministic planning fallback."""

    code: str
    message: str

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("code must not be empty")
        if not self.message:
            raise ValueError("message must not be empty")


@dataclass(frozen=True, slots=True)
class SemanticPlanningOutcome:
    """Accepted suggestions or an explicit deterministic fallback."""

    request: SemanticPlanningRequest
    trace: SemanticPlanningTrace
    result: SemanticPlanningResult | None = None
    failure: SemanticPlanningFailure | None = None
    fallback_plan: ConversionPlan | None = None

    def __post_init__(self) -> None:
        if (self.result is None) == (self.failure is None):
            message = "exactly one of result or failure must be provided"
            raise ValueError(message)
        if self.result is not None:
            if self.fallback_plan is not None:
                raise ValueError("a successful outcome must not contain a fallback plan")
            if self.result.request != self.request or self.result.trace != self.trace:
                raise ValueError("result must match the outcome request and trace")
        elif self.fallback_plan != self.request.baseline_plan:
            raise ValueError("a failed outcome must contain the deterministic baseline plan")

    @property
    def used_fallback(self) -> bool:
        """Return whether provider suggestions were rejected or unavailable."""
        return self.failure is not None


def request_semantic_planning(
    request: SemanticPlanningRequest,
    provider: SemanticPlanningProvider,
) -> SemanticPlanningOutcome:
    """Request, parse, and validate suggestions with deterministic fallback."""
    trace = SemanticPlanningTrace(
        request_id=request.request_id,
        prompt_version=request.prompt_version,
        provider_name=provider.provider_name,
        model_name=provider.model_name,
    )
    provider_request = SemanticProviderRequest(
        request_id=request.request_id,
        prompt=render_semantic_planning_prompt(request),
        response_schema=deepcopy(SEMANTIC_PLANNING_RESPONSE_JSON_SCHEMA),
    )

    try:
        response = SemanticPlanningResponse.from_json(provider.complete(provider_request))
        validate_semantic_planning_response(request, response)
    except SemanticProviderError as error:
        return _fallback_outcome(request, trace, code=error.code, message=error.message)
    except SemanticPlanningResponseError as error:
        return _fallback_outcome(
            request,
            trace,
            code="invalid_response",
            message=str(error),
        )

    result = SemanticPlanningResult(request=request, response=response, trace=trace)
    return SemanticPlanningOutcome(request=request, trace=trace, result=result)


def _fallback_outcome(
    request: SemanticPlanningRequest,
    trace: SemanticPlanningTrace,
    *,
    code: str,
    message: str,
) -> SemanticPlanningOutcome:
    return SemanticPlanningOutcome(
        request=request,
        trace=trace,
        failure=SemanticPlanningFailure(code=code, message=message),
        fallback_plan=request.baseline_plan,
    )
