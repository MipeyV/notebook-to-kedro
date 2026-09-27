"""Independent reviewed node-code cases and non-executing evaluation metrics."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from string import hexdigits
from typing import TYPE_CHECKING, cast

from notebook_to_kedro.generation.code import NodeCodeRequest, NodeCodeResponse, validate_node_code

if TYPE_CHECKING:
    from collections.abc import Sequence

NODE_CODE_CASE_SCHEMA_VERSION = "1.0"
_SHA256_HEX_LENGTH = 64
_CASE_KEYS = frozenset(
    {
        "schema_version",
        "case_id",
        "notebook_path",
        "source_sha256",
        "review_status",
        "request",
        "reference_response",
        "invalid_examples",
    }
)
_INVALID_EXAMPLE_KEYS = frozenset({"id", "response", "expected_error_contains"})


@dataclass(frozen=True, slots=True)
class InvalidNodeCodeExample:
    """Human-reviewed proposal that the static validator must reject."""

    id: str
    response: NodeCodeResponse
    expected_error_contains: str

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "invalid example id")
        _require_non_empty(self.expected_error_contains, "expected error fragment")


@dataclass(frozen=True, slots=True)
class NodeCodeCase:
    """One independently reviewed source task, reference node and invalid variants."""

    schema_version: str
    case_id: str
    notebook_path: str
    source_sha256: str
    review_status: str
    request: NodeCodeRequest
    reference_response: NodeCodeResponse
    invalid_examples: tuple[InvalidNodeCodeExample, ...]

    def __post_init__(self) -> None:
        if self.schema_version != NODE_CODE_CASE_SCHEMA_VERSION:
            raise ValueError(f"unsupported node code case schema version: {self.schema_version!r}")
        _require_non_empty(self.case_id, "node code case id")
        _require_non_empty(self.notebook_path, "notebook path")
        _require_sha256(self.source_sha256)
        if self.review_status != "approved":
            raise ValueError("node code cases must be explicitly approved")
        if not self.invalid_examples:
            raise ValueError("node code case must contain at least one invalid example")
        _require_unique(
            ("reference", *(item.id for item in self.invalid_examples)), "candidate IDs"
        )
        expected_identity = (
            self.request.schema_version,
            self.request.request_id,
            self.request.task_id,
        )
        responses = (self.reference_response, *(item.response for item in self.invalid_examples))
        if any(
            (response.schema_version, response.request_id, response.task_id) != expected_identity
            for response in responses
        ):
            raise ValueError("all case responses must match the request identity")


@dataclass(frozen=True, slots=True)
class NodeCodeCandidateEvaluation:
    """Independent static dimensions for one reviewed response."""

    candidate_id: str
    expected_valid: bool
    compilation_valid: bool
    static_valid: bool
    reference_ast_match: bool
    expected_outcome_match: bool
    diagnostic_message: str | None = None


@dataclass(frozen=True, slots=True)
class NodeCodeCaseEvaluation:
    """Evaluation of a reference and its reviewed invalid variants."""

    case_id: str
    reference: NodeCodeCandidateEvaluation
    invalid_examples: tuple[NodeCodeCandidateEvaluation, ...]

    @property
    def exact_match(self) -> bool:
        """Return whether every candidate produced its reviewed outcome."""
        return self.reference.expected_outcome_match and all(
            item.expected_outcome_match for item in self.invalid_examples
        )


@dataclass(frozen=True, slots=True)
class NodeCodeCorpusEvaluation:
    """Aggregate reviewed outcomes without model calls or code execution."""

    cases: tuple[NodeCodeCaseEvaluation, ...]

    @property
    def reference_count(self) -> int:
        """Return the number of independently reviewed references."""
        return len(self.cases)

    @property
    def reference_accepted_count(self) -> int:
        """Return references accepted by static validation."""
        return sum(case.reference.static_valid for case in self.cases)

    @property
    def false_rejection_count(self) -> int:
        """Return reviewed references rejected by static validation."""
        return self.reference_count - self.reference_accepted_count

    @property
    def invalid_example_count(self) -> int:
        """Return the number of reviewed invalid proposals."""
        return sum(len(case.invalid_examples) for case in self.cases)

    @property
    def detected_invalid_count(self) -> int:
        """Return invalid proposals rejected with their expected diagnostic fragment."""
        return sum(
            item.expected_outcome_match for case in self.cases for item in case.invalid_examples
        )

    @property
    def missed_invalid_count(self) -> int:
        """Return invalid proposals not rejected as reviewed."""
        return self.invalid_example_count - self.detected_invalid_count

    @property
    def exact_match(self) -> bool:
        """Return whether every reviewed expectation is met."""
        return bool(self.cases) and all(case.exact_match for case in self.cases)


def evaluate_node_code_case(case: NodeCodeCase) -> NodeCodeCaseEvaluation:
    """Evaluate one reviewed case without importing or executing proposed code."""
    reference = _evaluate_candidate(
        case,
        candidate_id="reference",
        response=case.reference_response,
        expected_valid=True,
        expected_error_contains=None,
    )
    invalid = tuple(
        _evaluate_candidate(
            case,
            candidate_id=item.id,
            response=item.response,
            expected_valid=False,
            expected_error_contains=item.expected_error_contains,
        )
        for item in case.invalid_examples
    )
    return NodeCodeCaseEvaluation(case.case_id, reference, invalid)


def evaluate_node_code_corpus(cases: Sequence[NodeCodeCase]) -> NodeCodeCorpusEvaluation:
    """Evaluate unique reviewed cases in caller-provided order."""
    case_ids = tuple(case.case_id for case in cases)
    if not case_ids:
        raise ValueError("node code corpus requires at least one case")
    _require_unique(case_ids, "node code corpus case IDs")
    return NodeCodeCorpusEvaluation(tuple(evaluate_node_code_case(case) for case in cases))


def node_code_case_to_dict(case: NodeCodeCase) -> dict[str, object]:
    """Return a canonical JSON-compatible reviewed case dictionary."""
    return {
        "schema_version": case.schema_version,
        "case_id": case.case_id,
        "notebook_path": case.notebook_path,
        "source_sha256": case.source_sha256,
        "review_status": case.review_status,
        "request": json.loads(case.request.to_json(indent=None)),
        "reference_response": json.loads(case.reference_response.to_json(indent=None)),
        "invalid_examples": [
            {
                "id": item.id,
                "response": json.loads(item.response.to_json(indent=None)),
                "expected_error_contains": item.expected_error_contains,
            }
            for item in case.invalid_examples
        ],
    }


def node_code_case_to_json(case: NodeCodeCase, *, indent: int | None = 2) -> str:
    """Serialize a reviewed node-code case deterministically."""
    return json.dumps(node_code_case_to_dict(case), indent=indent, ensure_ascii=True) + "\n"


def node_code_case_from_dict(payload: object) -> NodeCodeCase:
    """Strictly reconstruct a reviewed case from decoded JSON."""
    data = _object(payload, "node code case")
    _require_exact_keys(data, _CASE_KEYS, "node code case")
    review_status = _string(data["review_status"], "review_status")
    if review_status != "approved":
        raise ValueError("review_status must be 'approved'")
    invalid_value = data["invalid_examples"]
    if not isinstance(invalid_value, list):
        raise ValueError("invalid_examples must be an array")
    return NodeCodeCase(
        schema_version=_string(data["schema_version"], "schema_version"),
        case_id=_string(data["case_id"], "case_id"),
        notebook_path=_string(data["notebook_path"], "notebook_path"),
        source_sha256=_string(data["source_sha256"], "source_sha256"),
        review_status="approved",
        request=_request(data["request"]),
        reference_response=_response(data["reference_response"]),
        invalid_examples=tuple(_invalid_example(item) for item in invalid_value),
    )


def node_code_case_from_json(payload: str) -> NodeCodeCase:
    """Strictly reconstruct a reviewed case from JSON text."""
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid node code case JSON: {error.msg}") from error
    return node_code_case_from_dict(decoded)


def load_node_code_case(path: str | Path) -> NodeCodeCase:
    """Load one reviewed node-code case from disk."""
    case_path = Path(path)
    try:
        payload = case_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read node code case {case_path}: {error}") from error
    return node_code_case_from_json(payload)


def load_node_code_corpus(directory: str | Path) -> tuple[NodeCodeCase, ...]:
    """Load reviewed cases in deterministic filename order."""
    corpus_path = Path(directory)
    paths = tuple(sorted(corpus_path.glob("*.json")))
    if not paths:
        raise ValueError(f"node code corpus contains no JSON cases: {corpus_path}")
    cases = tuple(load_node_code_case(path) for path in paths)
    _require_unique(tuple(case.case_id for case in cases), "node code corpus case IDs")
    return cases


def verify_node_code_case_source(case: NodeCodeCase, *, project_root: str | Path = ".") -> None:
    """Verify notebook bytes and that one code cell exactly contains the reviewed task source."""
    path = Path(project_root).resolve() / case.notebook_path
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot read node code case notebook {path}: {error}") from error
    if hashlib.sha256(content).hexdigest() != case.source_sha256:
        raise ValueError(f"node code case source hash does not match: {case.case_id}")
    try:
        notebook = json.loads(content)
        cells = notebook["cells"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(f"invalid node code case notebook: {case.notebook_path}") from error
    if not isinstance(cells, list):
        raise ValueError(f"invalid node code case notebook: {case.notebook_path}")
    try:
        sources = {
            cell.get("id"): "".join(cell.get("source", ()))
            for cell in cells
            if isinstance(cell, dict)
            and cell.get("cell_type") == "code"
            and isinstance(cell.get("id"), str)
        }
    except TypeError as error:
        raise ValueError(f"invalid node code case notebook: {case.notebook_path}") from error
    if not any(
        sources.get(cell_id) == case.request.raw_source for cell_id in case.request.source_cell_ids
    ):
        raise ValueError(
            f"reviewed source and cell provenance do not match the notebook: {case.case_id}"
        )


def _evaluate_candidate(
    case: NodeCodeCase,
    *,
    candidate_id: str,
    response: NodeCodeResponse,
    expected_valid: bool,
    expected_error_contains: str | None,
) -> NodeCodeCandidateEvaluation:
    source = "\n".join((*response.imports, response.function_code))
    try:
        compile(source, "<reviewed-node-code>", "exec", dont_inherit=True)
    except (SyntaxError, ValueError):
        compilation_valid = False
    else:
        compilation_valid = True
    try:
        candidate_tree = ast.parse(response.function_code)
        reference_tree = ast.parse(case.reference_response.function_code)
    except SyntaxError:
        reference_ast_match = False
    else:
        reference_ast_match = ast.dump(candidate_tree) == ast.dump(reference_tree)
    diagnostic_message = None
    try:
        validate_node_code(case.request, response)
    except ValueError as error:
        static_valid = False
        diagnostic_message = str(error)
    else:
        static_valid = True
    if expected_valid:
        expected_outcome_match = static_valid and compilation_valid and reference_ast_match
    else:
        expected_outcome_match = (
            not static_valid
            and expected_error_contains is not None
            and diagnostic_message is not None
            and expected_error_contains in diagnostic_message
        )
    return NodeCodeCandidateEvaluation(
        candidate_id=candidate_id,
        expected_valid=expected_valid,
        compilation_valid=compilation_valid,
        static_valid=static_valid,
        reference_ast_match=reference_ast_match,
        expected_outcome_match=expected_outcome_match,
        diagnostic_message=diagnostic_message,
    )


def _invalid_example(payload: object) -> InvalidNodeCodeExample:
    data = _object(payload, "invalid node code example")
    _require_exact_keys(data, _INVALID_EXAMPLE_KEYS, "invalid node code example")
    return InvalidNodeCodeExample(
        id=_string(data["id"], "invalid example id"),
        response=_response(data["response"]),
        expected_error_contains=_string(data["expected_error_contains"], "expected_error_contains"),
    )


def _request(payload: object) -> NodeCodeRequest:
    return NodeCodeRequest.from_json(json.dumps(_object(payload, "node code request")))


def _response(payload: object) -> NodeCodeResponse:
    return NodeCodeResponse.from_json(json.dumps(_object(payload, "node code response")))


def _object(payload: object, label: str) -> dict[str, object]:
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise ValueError(f"{label} must be an object with string keys")
    return cast("dict[str, object]", payload)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _require_exact_keys(data: dict[str, object], expected: frozenset[str], label: str) -> None:
    actual = frozenset(data)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(f"invalid {label} fields; missing={missing}, unexpected={unexpected}")


def _require_non_empty(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _require_sha256(value: str) -> None:
    if len(value) != _SHA256_HEX_LENGTH or any(character not in hexdigits for character in value):
        raise ValueError("source_sha256 must be a 64-character hexadecimal digest")
