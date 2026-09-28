"""Validated proposal execution joined with deterministic behavioral comparison."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from string import hexdigits
from typing import TYPE_CHECKING

from notebook_to_kedro.evaluation.behavioral_comparison import (
    BehavioralCaseComparison,
    behavioral_case_comparison_to_dict,
    compare_behavioral_result,
)
from notebook_to_kedro.evaluation.behavioral_execution import (
    BehavioralExecutionResult,
    behavioral_execution_result_to_dict,
    execute_behavioral_proposal,
)

if TYPE_CHECKING:
    from notebook_to_kedro.evaluation.behavioral import BehavioralCase
    from notebook_to_kedro.evaluation.behavioral_execution import BehavioralExecutionConfig
    from notebook_to_kedro.evaluation.node_code_corpus import NodeCodeCase
    from notebook_to_kedro.generation.code import NodeCodeResponse

BEHAVIORAL_PROPOSAL_EVALUATION_SCHEMA_VERSION = "1.0"
_SHA256_HEX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class BehavioralProposalEvaluation:
    """Traceable execution and comparison outcome for one validated proposal."""

    schema_version: str
    case_id: str
    node_code_case_id: str
    request_id: str
    task_id: str
    response_sha256: str
    execution: BehavioralExecutionResult
    comparison: BehavioralCaseComparison

    def __post_init__(self) -> None:
        if self.schema_version != BEHAVIORAL_PROPOSAL_EVALUATION_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported proposal evaluation schema version: {self.schema_version!r}"
            )
        if any(
            not value.strip()
            for value in (self.case_id, self.node_code_case_id, self.request_id, self.task_id)
        ):
            raise ValueError("proposal evaluation IDs must not be empty")
        if len(self.response_sha256) != _SHA256_HEX_LENGTH or any(
            character not in hexdigits for character in self.response_sha256
        ):
            raise ValueError("response_sha256 must be a SHA-256 hexadecimal digest")
        if not isinstance(self.execution, BehavioralExecutionResult):
            raise ValueError("execution must use BehavioralExecutionResult")
        if not isinstance(self.comparison, BehavioralCaseComparison):
            raise ValueError("comparison must use BehavioralCaseComparison")
        expected_identity = (self.case_id, self.node_code_case_id)
        if (self.execution.case_id, self.execution.node_code_case_id) != expected_identity:
            raise ValueError("proposal execution identity does not match evaluation")
        if (self.comparison.case_id, self.comparison.node_code_case_id) != expected_identity:
            raise ValueError("proposal comparison identity does not match evaluation")
        if self.comparison.execution_status != self.execution.status:
            raise ValueError("proposal execution and comparison statuses do not match")

    @property
    def matched(self) -> bool:
        """Return whether the proposal matches the reviewed behavioral expectation."""
        return self.comparison.status == "matched"


def evaluate_behavioral_proposal(
    case: BehavioralCase,
    node_code_case: NodeCodeCase,
    proposal: NodeCodeResponse,
    *,
    allow_untrusted_code_execution: bool = False,
    config: BehavioralExecutionConfig | None = None,
) -> BehavioralProposalEvaluation:
    """Validate, isolate, execute and compare one node-code proposal."""
    execution = execute_behavioral_proposal(
        case,
        node_code_case,
        proposal,
        allow_untrusted_code_execution=allow_untrusted_code_execution,
        config=config,
    )
    comparison = compare_behavioral_result(case, execution)
    return BehavioralProposalEvaluation(
        schema_version=BEHAVIORAL_PROPOSAL_EVALUATION_SCHEMA_VERSION,
        case_id=case.case_id,
        node_code_case_id=case.node_code_case_id,
        request_id=proposal.request_id,
        task_id=proposal.task_id,
        response_sha256=_response_sha256(proposal),
        execution=execution,
        comparison=comparison,
    )


def behavioral_proposal_evaluation_to_dict(
    evaluation: BehavioralProposalEvaluation,
) -> dict[str, object]:
    """Return one proposal evaluation as a canonical JSON-compatible dictionary."""
    return {
        "schema_version": evaluation.schema_version,
        "case_id": evaluation.case_id,
        "node_code_case_id": evaluation.node_code_case_id,
        "request_id": evaluation.request_id,
        "task_id": evaluation.task_id,
        "response_sha256": evaluation.response_sha256,
        "execution": behavioral_execution_result_to_dict(evaluation.execution),
        "comparison": behavioral_case_comparison_to_dict(evaluation.comparison),
    }


def behavioral_proposal_evaluation_to_json(
    evaluation: BehavioralProposalEvaluation, *, indent: int | None = 2
) -> str:
    """Serialize one proposal evaluation deterministically."""
    return (
        json.dumps(
            behavioral_proposal_evaluation_to_dict(evaluation),
            indent=indent,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )


def _response_sha256(proposal: NodeCodeResponse) -> str:
    payload = proposal.to_json(indent=None).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
