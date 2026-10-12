"""Human-declared review evidence and explicit offline contract promotion."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from notebook_to_kedro.evaluation.behavioral_artifacts import (
    _boolean,
    _exact_keys,
    _integer,
    _json_sha256,
    _object,
    _optional_string,
    _to_json,
    write_json_exclusive,
)
from notebook_to_kedro.evaluation.notebook_artifacts import (
    NotebookPipelineArtifact,
    _array,
    _digest,
    _limit,
    load_notebook_pipeline_artifact,
    notebook_pipeline_artifact_to_dict,
)
from notebook_to_kedro.evaluation.notebook_runtime import require_notebook_runtime_compatibility
from notebook_to_kedro.evaluation.notebook_sources import (
    NotebookSourceFile,
    _read_file,
    _reject_constant,
    _required_string,
)
from notebook_to_kedro.generation.code.serialization import _unique_object

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from notebook_to_kedro.evaluation.notebook_runtime import NotebookRuntimeIdentity
    from notebook_to_kedro.evaluation.notebook_sources import NotebookSourceBinding

NOTEBOOK_HUMAN_REVIEW_VERSION = "notebook-human-review-1"
REVIEWED_NOTEBOOK_CONTRACT_VERSION = "reviewed-notebook-contract-1"
NOTEBOOK_REVIEW_SECTIONS = (
    "source_catalog",
    "hand_expectations",
    "structure_learning",
    "oracle_sensitivity_execution",
)
DEFAULT_NOTEBOOK_REVIEW_BYTES = 16_777_216
_EVIDENCE_ROLE = "human_review_evidence"
_DECISION_FIELDS = frozenset(
    {
        "reviewer_id",
        "reviewer_kind",
        "independent_human_review",
        "review_date",
        "reviewed_revision",
        "decision",
        "checks",
        "corrections",
        "evidence_reference",
        "evidence_path",
    }
)


@dataclass(frozen=True, slots=True)
class NotebookReviewCheck:
    """One explicitly completed worksheet section and reviewer-supplied notes."""

    section: str
    completed: bool
    notes: str


@dataclass(frozen=True, slots=True)
class NotebookHumanReview:
    """A hashed declaration, never proof that the named person is human or independent."""

    schema_version: str
    baseline_artifact_sha256: str
    source_binding_sha256: str
    expectations_sha256: str
    fixture_author_ids: tuple[str, ...]
    reviewer_id: str | None
    reviewer_kind: Literal["human", "model"] | None
    independent_human_review: bool
    review_date: str | None
    reviewed_revision: str | None
    decision: Literal["pending", "approved", "changes_requested"]
    checks: tuple[NotebookReviewCheck, ...]
    corrections: str | None
    evidence_reference: str | None
    evidence_file: NotebookSourceFile | None
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ReviewedNotebookContract:
    """Operator-accepted review of a frozen reference; original draft evidence is unchanged."""

    schema_version: str
    baseline: NotebookPipelineArtifact
    review: NotebookHumanReview
    operator_id: str
    content_sha256: str


def _seal(payload: dict[str, object]) -> dict[str, object]:
    normalized = _object(json.loads(_to_json(payload)), "review JSON")
    normalized.pop("content_sha256", None)
    return {**normalized, "content_sha256": _json_sha256(normalized)}


def _integrity(data: dict[str, object], version: str) -> None:
    if data["schema_version"] != version:
        raise ValueError("unsupported notebook review version")
    if _digest(data["content_sha256"], "content_sha256") != _seal(data)["content_sha256"]:
        raise ValueError("notebook review integrity mismatch")


def _optional_text(value: object, label: str) -> str | None:
    text = _optional_string(value, label)
    return None if text is None else _required_string(text, label)


def _evidence(value: object) -> NotebookSourceFile | None:
    if value is None:
        return None
    data = _object(value, "evidence file")
    _exact_keys(data, frozenset(NotebookSourceFile.__dataclass_fields__), "evidence file")
    path = _required_string(data["path"], "evidence path")
    size = _integer(data["size_bytes"], "evidence size_bytes")
    if data["role"] != _EVIDENCE_ROLE or Path(path).is_absolute() or size <= 0:
        raise ValueError("review evidence requires a non-empty project-relative file")
    return NotebookSourceFile(
        _EVIDENCE_ROLE, path, _digest(data["sha256"], "evidence sha256"), size
    )


def _review_from_dict(value: object) -> NotebookHumanReview:
    data = _object(value, "human review")
    _exact_keys(data, frozenset(NotebookHumanReview.__dataclass_fields__), "human review")
    _integrity(data, NOTEBOOK_HUMAN_REVIEW_VERSION)
    authors = tuple(
        _required_string(item, "fixture author")
        for item in _array(data["fixture_author_ids"], "fixture_author_ids")
    )
    if not authors or len({item.strip().casefold() for item in authors}) != len(authors):
        raise ValueError("fixture author identities must be non-empty and unique")
    decision = data["decision"]
    kind = data["reviewer_kind"]
    if decision not in ("pending", "approved", "changes_requested") or kind not in (
        None,
        "human",
        "model",
    ):
        raise ValueError("unsupported review decision or reviewer kind")
    checks = []
    for item in _array(data["checks"], "review checks"):
        row = _object(item, "review check")
        _exact_keys(row, frozenset(NotebookReviewCheck.__dataclass_fields__), "review check")
        completed = _boolean(row["completed"], "completed")
        notes = row["notes"]
        if not isinstance(notes, str) or (completed and not notes.strip()):
            raise ValueError("completed review checks require non-empty notes")
        checks.append(
            NotebookReviewCheck(_required_string(row["section"], "section"), completed, notes)
        )
    if tuple(item.section for item in checks) != NOTEBOOK_REVIEW_SECTIONS:
        raise ValueError("review section inventory mismatch")
    reviewed_date = _optional_text(data["review_date"], "review_date")
    if reviewed_date is not None and date.fromisoformat(reviewed_date).isoformat() != reviewed_date:
        raise ValueError("review_date must use YYYY-MM-DD")
    revision = _optional_text(data["reviewed_revision"], "reviewed_revision")
    if revision is not None and re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("reviewed_revision must be a full lowercase Git SHA1")
    return NotebookHumanReview(
        NOTEBOOK_HUMAN_REVIEW_VERSION,
        _digest(data["baseline_artifact_sha256"], "baseline_artifact_sha256"),
        _digest(data["source_binding_sha256"], "source_binding_sha256"),
        _digest(data["expectations_sha256"], "expectations_sha256"),
        authors,
        _optional_text(data["reviewer_id"], "reviewer_id"),
        kind,
        _boolean(data["independent_human_review"], "independent_human_review"),
        reviewed_date,
        revision,
        decision,
        tuple(checks),
        _optional_text(data["corrections"], "corrections"),
        _optional_text(data["evidence_reference"], "evidence_reference"),
        _evidence(data["evidence_file"]),
        cast("str", data["content_sha256"]),
    )


def notebook_human_review_to_dict(review: NotebookHumanReview) -> dict[str, object]:
    """Validate and serialize a declaration without approving it or refreshing its digest."""
    payload = _object(json.loads(_to_json(asdict(review))), "human review")
    _review_from_dict(payload)
    return payload


def _baseline(artifact: NotebookPipelineArtifact) -> dict[str, object]:
    payload = notebook_pipeline_artifact_to_dict(artifact)
    run = artifact.run
    produced = {name for task in run.capture.binding.plan.task_candidates for name in task.outputs}
    if (
        artifact.comparison.status != "matched"
        or not run.capture.complete
        or {item.dataset for item in run.observations} != produced
    ):
        raise ValueError(
            "review reference requires a matched complete pipeline and every planned output"
        )
    require_notebook_runtime_compatibility(
        cast("NotebookRuntimeIdentity", run.runtime_before),
        cast("NotebookRuntimeIdentity", run.runtime_after),
        cast("NotebookRuntimeIdentity", run.runtime_before),
    )
    return payload


def prepare_notebook_human_review(
    artifact: NotebookPipelineArtifact, *, fixture_author_ids: Sequence[str]
) -> NotebookHumanReview:
    """Prepare an unchecked pending request tied to the complete reference and expectations."""
    payload = _baseline(artifact)
    review = NotebookHumanReview(
        schema_version=NOTEBOOK_HUMAN_REVIEW_VERSION,
        baseline_artifact_sha256=cast("str", payload["content_sha256"]),
        source_binding_sha256=artifact.run.capture.binding.content_sha256,
        expectations_sha256=artifact.comparison.expectations_sha256,
        fixture_author_ids=tuple(fixture_author_ids),
        reviewer_id=None,
        reviewer_kind=None,
        independent_human_review=False,
        review_date=None,
        reviewed_revision=None,
        decision="pending",
        checks=tuple(
            NotebookReviewCheck(section, completed=False, notes="")
            for section in NOTEBOOK_REVIEW_SECTIONS
        ),
        corrections=None,
        evidence_reference=None,
        evidence_file=None,
        content_sha256="",
    )
    return _review_from_dict(_seal(asdict(review)))


def record_notebook_human_review(
    request: NotebookHumanReview, decision: Mapping[str, object], *, project_root: str | Path
) -> NotebookHumanReview:
    """Record caller-supplied declarations and proof bytes, never infer approval from scores."""
    payload = notebook_human_review_to_dict(request)
    if request.decision != "pending":
        raise ValueError("a recorded review cannot be amended; prepare a new request")
    fields = dict(decision)
    _exact_keys(fields, _DECISION_FIELDS, "review decision")
    path = fields.pop("evidence_path")
    evidence = None
    if path is not None:
        name = _required_string(path, "evidence_path")
        if Path(name).is_absolute():
            raise ValueError("review evidence_path must be project-relative")
        evidence, _ = _read_file(
            Path(project_root).resolve(), name, _EVIDENCE_ROLE, DEFAULT_NOTEBOOK_REVIEW_BYTES
        )
    payload.update(fields)
    payload["evidence_file"] = None if evidence is None else asdict(evidence)
    return _review_from_dict(_seal(payload))


def _verify_evidence(review: NotebookHumanReview, project_root: str | Path, limit: int) -> None:
    if review.evidence_file is not None:
        current, _ = _read_file(
            Path(project_root).resolve(), review.evidence_file.path, _EVIDENCE_ROLE, limit
        )
        if current != review.evidence_file:
            raise ValueError("human review evidence file changed")


def _read_json(path: str | Path, limit: int) -> dict[str, object]:
    _limit(limit)
    source = Path(path)
    if not source.is_file():
        raise ValueError("review JSON must be a regular file")
    with source.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("notebook review exceeds max_file_bytes")
    return _object(
        json.loads(data, object_pairs_hook=_unique_object, parse_constant=_reject_constant),
        "review JSON",
    )


def _write_json(path: str | Path, payload: dict[str, object], limit: int) -> Path:
    _limit(limit)
    if len(_to_json(payload).encode("utf-8")) > limit:
        raise ValueError("notebook review exceeds max_file_bytes")
    write_json_exclusive(path, payload)
    return Path(path)


def write_notebook_human_review(
    path: str | Path,
    review: NotebookHumanReview,
    *,
    max_file_bytes: int = DEFAULT_NOTEBOOK_REVIEW_BYTES,
) -> Path:
    """Publish a pending or recorded declaration exclusively, never replace existing evidence."""
    return _write_json(path, notebook_human_review_to_dict(review), max_file_bytes)


def load_notebook_human_review(
    path: str | Path,
    *,
    project_root: str | Path,
    max_file_bytes: int = DEFAULT_NOTEBOOK_REVIEW_BYTES,
) -> NotebookHumanReview:
    """Inspect declarations and local proof bytes without granting approval or executing code."""
    review = _review_from_dict(_read_json(path, max_file_bytes))
    _verify_evidence(review, project_root, max_file_bytes)
    return review


def _review_gate(artifact: NotebookPipelineArtifact, review: NotebookHumanReview) -> None:
    baseline = _baseline(artifact)
    notebook_human_review_to_dict(review)
    if (
        review.baseline_artifact_sha256,
        review.source_binding_sha256,
        review.expectations_sha256,
    ) != (
        baseline["content_sha256"],
        artifact.run.capture.binding.content_sha256,
        artifact.comparison.expectations_sha256,
    ):
        raise ValueError("review does not match the exact reference, sources and expectations")
    if (
        review.decision != "approved"
        or review.reviewer_kind != "human"
        or review.independent_human_review is not True
    ):
        raise ValueError("promotion requires an explicitly approved independent human declaration")
    if any(
        value is None
        for value in (
            review.reviewer_id,
            review.review_date,
            review.reviewed_revision,
            review.corrections,
            review.evidence_reference,
            review.evidence_file,
        )
    ) or not all(check.completed for check in review.checks):
        raise ValueError(
            "promotion requires complete reviewer metadata, proof and every worksheet section"
        )
    reviewer = cast("str", review.reviewer_id).strip().casefold()
    if reviewer in {author.strip().casefold() for author in review.fixture_author_ids}:
        raise ValueError("reviewer must not be a declared fixture author")


def _contract(
    artifact: NotebookPipelineArtifact, review: NotebookHumanReview, operator_id: str
) -> ReviewedNotebookContract:
    _review_gate(artifact, review)
    operator = _required_string(operator_id, "operator_id")
    payload = _seal(
        {
            "schema_version": REVIEWED_NOTEBOOK_CONTRACT_VERSION,
            "baseline_artifact_sha256": review.baseline_artifact_sha256,
            "review": notebook_human_review_to_dict(review),
            "operator_id": operator,
        }
    )
    return ReviewedNotebookContract(
        REVIEWED_NOTEBOOK_CONTRACT_VERSION,
        artifact,
        review,
        operator,
        cast("str", payload["content_sha256"]),
    )


def promote_notebook_pipeline_artifact(  # noqa: PLR0913
    baseline_path: str | Path,
    binding: NotebookSourceBinding,
    capture_directory: str | Path,
    review_path: str | Path,
    *,
    project_root: str | Path,
    operator_id: str,
    accept_human_review_evidence: bool = False,
) -> ReviewedNotebookContract:
    """Verify external declarations after explicit operator acceptance; no code/model execution."""
    if accept_human_review_evidence is not True:
        raise ValueError(
            "promotion requires accept_human_review_evidence=True; identity is not authenticated"
        )
    artifact = load_notebook_pipeline_artifact(
        baseline_path, binding, capture_directory, project_root=project_root
    )
    review = load_notebook_human_review(review_path, project_root=project_root)
    return _contract(artifact, review, operator_id)


def reviewed_notebook_contract_to_dict(contract: ReviewedNotebookContract) -> dict[str, object]:
    """Serialize operator acceptance without rewriting the draft reference or its identities."""
    checked = _contract(contract.baseline, contract.review, contract.operator_id)
    if contract != checked:
        raise ValueError("reviewed notebook contract version or integrity mismatch")
    return {
        "schema_version": contract.schema_version,
        "baseline_artifact_sha256": contract.review.baseline_artifact_sha256,
        "review": notebook_human_review_to_dict(contract.review),
        "operator_id": contract.operator_id,
        "content_sha256": contract.content_sha256,
    }


def write_reviewed_notebook_contract(
    path: str | Path,
    contract: ReviewedNotebookContract,
    *,
    max_file_bytes: int = DEFAULT_NOTEBOOK_REVIEW_BYTES,
) -> Path:
    """Publish a bounded reference wrapper exclusively without modifying any draft evidence."""
    return _write_json(path, reviewed_notebook_contract_to_dict(contract), max_file_bytes)


def load_reviewed_notebook_contract(  # noqa: PLR0913
    path: str | Path,
    baseline_path: str | Path,
    binding: NotebookSourceBinding,
    capture_directory: str | Path,
    *,
    project_root: str | Path,
    max_file_bytes: int = DEFAULT_NOTEBOOK_REVIEW_BYTES,
) -> ReviewedNotebookContract:
    """Recheck stored operator acceptance, current sources/reference and proof without execution."""
    data = _read_json(path, max_file_bytes)
    _exact_keys(
        data,
        frozenset(
            {
                "schema_version",
                "baseline_artifact_sha256",
                "review",
                "operator_id",
                "content_sha256",
            }
        ),
        "reviewed contract",
    )
    _integrity(data, REVIEWED_NOTEBOOK_CONTRACT_VERSION)
    review = _review_from_dict(data["review"])
    _verify_evidence(review, project_root, max_file_bytes)
    artifact = load_notebook_pipeline_artifact(
        baseline_path, binding, capture_directory, project_root=project_root
    )
    contract = _contract(artifact, review, _required_string(data["operator_id"], "operator_id"))
    if _json_sha256(reviewed_notebook_contract_to_dict(contract)) != _json_sha256(data):
        raise ValueError("reviewed contract reference or content mismatch")
    return contract
