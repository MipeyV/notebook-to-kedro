"""Read-only source binding for draft, deterministic whole-notebook body batches."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.evaluation.behavioral_artifacts import (
    _is_sha256,
    _json_sha256,
    _object,
    _string,
)
from notebook_to_kedro.evaluation.notebook_body import (
    DEFAULT_NOTEBOOK_BODY_RESPONSE_BYTES,
    NotebookBodyBatchReport,
    prepare_notebook_body_requests,
    validate_notebook_body_batch,
)
from notebook_to_kedro.generation.code.serialization import _unique_object
from notebook_to_kedro.notebook import load_notebook
from notebook_to_kedro.semantic import DeterministicSemanticPlanner

if TYPE_CHECKING:
    from collections.abc import Sequence

    from notebook_to_kedro.evaluation.notebook_body import NotebookBodyRecord
    from notebook_to_kedro.generation.code import NodeCodeRequest
    from notebook_to_kedro.ir import CatalogDataset, ConversionPlan

NOTEBOOK_SOURCE_BINDING_VERSION = "notebook-source-binding-draft-1"
DEFAULT_NOTEBOOK_SOURCE_FILE_BYTES = 16_777_216


@dataclass(frozen=True, slots=True)
class NotebookSourceFile:
    """Project-local file role, resolved relative path and exact byte identity."""

    role: str
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class NotebookSourceBinding:
    """In-memory draft sources, pending review metadata and frozen deterministic requests."""

    schema_version: str
    case_id: str
    plan: ConversionPlan
    request_prefix: str
    requests: tuple[NodeCodeRequest, ...]
    files: tuple[NotebookSourceFile, ...]
    review_json: str
    max_file_bytes: int
    content_sha256: str


@dataclass(frozen=True, slots=True)
class SourceBoundNotebookBodyReport:
    """Static batch checked against current sources, without approval or execution."""

    binding: NotebookSourceBinding
    batch: NotebookBodyBatchReport


def _required_string(value: object, label: str) -> str:
    text = _string(value, label)
    if not text.strip():
        raise ValueError(f"{label} must not be empty")
    return text


def _local_path(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("bound file path escapes project_root")
    return resolved


def _read_file(
    root: Path, path: str | Path, role: str, limit: int
) -> tuple[NotebookSourceFile, bytes]:
    resolved = _local_path(root, path)
    if not resolved.is_file():
        raise ValueError(f"Cannot read bound file: {role} (not a regular file)")
    try:
        with resolved.open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError as error:
        raise ValueError(f"Cannot read bound file: {role}") from error
    if len(data) > limit:
        raise ValueError(f"bound file exceeds max_file_bytes: {role}")
    return NotebookSourceFile(
        role, resolved.relative_to(root).as_posix(), hashlib.sha256(data).hexdigest(), len(data)
    ), data


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-finite contract JSON value: {value}")


def _read_contract(data: bytes) -> dict[str, object]:
    payload = _object(
        json.loads(data, object_pairs_hook=_unique_object, parse_constant=_reject_constant),
        "pilot contract",
    )
    if payload.get("schema_version") != "pilot-draft-1":
        raise ValueError("source binding currently supports only pilot-draft-1")
    review = _object(payload.get("review"), "review")
    if (
        review.get("status") != "pending"
        or review.get("independent_human_review") is not False
        or "reviewed_by" not in review
        or review["reviewed_by"] is not None
    ):
        raise ValueError("draft source binding requires explicitly pending human review")
    _required_string(review.get("provenance"), "review provenance")
    _required_string(review.get("local_benchmark_provider_exposure"), "provider exposure")
    return payload


def _declared_file(
    root: Path, descriptor: dict[str, object], role: str, limit: int
) -> NotebookSourceFile:
    path = _required_string(descriptor.get("path"), f"{role} path")
    if Path(path).is_absolute():
        raise ValueError("contract source paths must be project-relative")
    expected = _string(descriptor.get("sha256"), f"{role} sha256")
    if not _is_sha256(expected):
        raise ValueError(f"invalid declared SHA-256: {role}")
    identity, _ = _read_file(root, path, role, limit)
    if identity.sha256 != expected:
        raise ValueError(f"source hash does not match contract: {role}")
    return identity


def _dataset_files(
    root: Path, contract: dict[str, object], plan: ConversionPlan, limit: int
) -> tuple[NotebookSourceFile, ...]:
    sources = contract.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("contract sources must be a non-empty array")
    catalog = {dataset.name: dataset for dataset in plan.catalog_datasets}
    outputs = {name for task in plan.task_candidates for name in task.outputs}
    names: set[str] = set()
    external: set[str] = set()
    files = []
    for value in sources:
        source = _object(value, "source")
        name = _required_string(source.get("name"), "source name")
        if name in names:
            raise ValueError("duplicate contract source name")
        names.add(name)
        if source.get("kind") == "simulation":
            if (
                source.get("catalog_entry") is not False
                or name not in outputs
                or name in catalog
                or "path" in source
                or "sha256" in source
            ):
                raise ValueError("simulation source must be a task output without a catalog file")
        elif source.get("kind") == "local_csv":
            identity = _declared_file(root, source, f"dataset:{name}", limit)
            dataset = catalog.get(name)
            _validate_catalog_source(root, source, dataset, identity)
            external.add(name)
            files.append(identity)
        else:
            raise ValueError("source binding supports only simulation and local_csv sources")
    if external != set(catalog):
        raise ValueError("contract must bind every catalog dataset")
    return tuple(files)


def _validate_catalog_source(
    root: Path,
    source: dict[str, object],
    dataset: CatalogDataset | None,
    identity: NotebookSourceFile,
) -> None:
    if (
        dataset is None
        or dataset.source_filepath is None
        or source.get("catalog_entry") is not True
        or source.get("catalog_type") != dataset.type
        or source.get("generated_filepath") != dataset.filepath
        or _local_path(root, dataset.source_filepath) != root / identity.path
    ):
        raise ValueError("contract catalog source does not match the plan")


def _binding_sha256(binding: NotebookSourceBinding) -> str:
    payload = asdict(binding)
    del payload["content_sha256"]
    return _json_sha256(payload)


def create_notebook_source_binding(  # noqa: PLR0913
    plan: ConversionPlan,
    *,
    project_root: str | Path,
    contract_path: str | Path,
    expected_catalog_path: str | Path,
    request_prefix: str = "notebook-body",
    max_file_bytes: int = DEFAULT_NOTEBOOK_SOURCE_FILE_BYTES,
) -> NotebookSourceBinding:
    """Bind a pending draft to local bytes and an exactly rebuilt deterministic plan.

    Files are read and rechecked, never executed. Concurrent filesystem changes are not
    locked; this is point-in-time drift detection, not authentication or an OS sandbox.
    The expected catalog and business expectations are hashed, not semantically approved.
    """
    if type(max_file_bytes) is not int or max_file_bytes <= 0:
        raise ValueError("max_file_bytes must be a positive integer")
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ValueError("project_root must be an existing directory")
    requests = prepare_notebook_body_requests(plan, request_prefix=request_prefix)
    contract_file, data = _read_file(root, contract_path, "contract", max_file_bytes)
    contract = _read_contract(data)
    case_id = _required_string(contract.get("case_id"), "case_id")
    notebook_file = _declared_file(
        root, _object(contract.get("notebook"), "notebook"), "notebook", max_file_bytes
    )
    if _local_path(root, plan.notebook_path) != root / notebook_file.path:
        raise ValueError("plan notebook path does not match the contract")
    catalog_file, _ = _read_file(root, expected_catalog_path, "expected_catalog", max_file_bytes)
    files = (
        contract_file,
        notebook_file,
        catalog_file,
        *_dataset_files(root, contract, plan, max_file_bytes),
    )
    loaded = load_notebook(root / notebook_file.path, project_root=root)
    if loaded.content_sha256 != notebook_file.sha256:
        raise ValueError("notebook changed during source binding")
    rebuilt = DeterministicSemanticPlanner().create_plan(analyze_notebook(loaded))
    if rebuilt != plan:
        raise ValueError("plan does not match the deterministic notebook reconstruction")
    for identity in files:
        current, _ = _read_file(root, identity.path, identity.role, max_file_bytes)
        if current != identity:
            raise ValueError(f"bound file changed during source binding: {identity.role}")
    binding = NotebookSourceBinding(
        NOTEBOOK_SOURCE_BINDING_VERSION,
        case_id,
        plan,
        request_prefix,
        requests,
        files,
        json.dumps(contract["review"], sort_keys=True, allow_nan=False),
        max_file_bytes,
        "",
    )
    return replace(binding, content_sha256=_binding_sha256(binding))


def _role_path(binding: NotebookSourceBinding, role: str) -> str:
    matches = [identity.path for identity in binding.files if identity.role == role]
    if len(matches) != 1:
        raise ValueError(f"binding requires exactly one {role} file")
    return matches[0]


def verify_notebook_source_binding(
    binding: NotebookSourceBinding, *, project_root: str | Path
) -> None:
    """Recreate source/plan/request evidence, rejecting stale or internally changed bindings."""
    if binding.schema_version != NOTEBOOK_SOURCE_BINDING_VERSION:
        raise ValueError("unsupported notebook source binding version")
    if _binding_sha256(binding) != binding.content_sha256:
        raise ValueError("notebook source binding content hash mismatch")
    current = create_notebook_source_binding(
        binding.plan,
        project_root=project_root,
        contract_path=_role_path(binding, "contract"),
        expected_catalog_path=_role_path(binding, "expected_catalog"),
        request_prefix=binding.request_prefix,
        max_file_bytes=binding.max_file_bytes,
    )
    if current != binding:
        raise ValueError("notebook source binding changed; create a new explicit binding")


def validate_source_bound_notebook_body_batch(
    binding: NotebookSourceBinding,
    records: Sequence[NotebookBodyRecord],
    *,
    project_root: str | Path,
    max_response_bytes: int = DEFAULT_NOTEBOOK_BODY_RESPONSE_BYTES,
) -> SourceBoundNotebookBodyReport:
    """Check current sources before parsing any response; never contact or execute a provider."""
    verify_notebook_source_binding(binding, project_root=project_root)
    batch = validate_notebook_body_batch(
        binding.plan,
        records,
        request_prefix=binding.request_prefix,
        max_response_bytes=max_response_bytes,
    )
    return SourceBoundNotebookBodyReport(binding, batch)
