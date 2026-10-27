"""Offline reviewed campaign envelopes and exclusive, all-slot response accounting."""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.evaluation.behavioral_artifacts import (
    _integer,
    _json_sha256,
    _number,
    _to_json,
)
from notebook_to_kedro.evaluation.notebook_artifacts import _limit
from notebook_to_kedro.evaluation.notebook_body import DEFAULT_NOTEBOOK_BODY_RESPONSE_BYTES
from notebook_to_kedro.evaluation.notebook_capture import (
    DEFAULT_NOTEBOOK_CAPTURE_FILE_BYTES,
    _read,
    _write,
    create_notebook_body_capture,
    load_notebook_body_capture,
    record_notebook_body_response,
    reserve_notebook_body_request,
)
from notebook_to_kedro.evaluation.notebook_ollama import (
    notebook_ollama_controls_to_dict,
    require_notebook_ollama_compatibility,
)
from notebook_to_kedro.evaluation.notebook_review import (
    load_reviewed_notebook_contract,
    reviewed_notebook_contract_to_dict,
)
from notebook_to_kedro.generation.code import (
    NODE_BODY_ASSEMBLY_VERSION,
    NODE_BODY_SCHEMA_VERSION,
    NODE_CODE_PARAMETER_EVIDENCE_VERSION,
    NODE_CODE_VALIDATOR_VERSION,
)
from notebook_to_kedro.generation.code.body_prompting import (
    NODE_BODY_PROMPT_VERSION,
    render_node_body_prompt,
)
from notebook_to_kedro.generation.code.schemas import NODE_BODY_RESPONSE_JSON_SCHEMA

if TYPE_CHECKING:
    from notebook_to_kedro.evaluation.notebook_body import NotebookBodyRecord
    from notebook_to_kedro.evaluation.notebook_capture import NotebookBodyCapture
    from notebook_to_kedro.evaluation.notebook_ollama import NotebookOllamaControls
    from notebook_to_kedro.evaluation.notebook_sources import NotebookSourceBinding

NOTEBOOK_CAMPAIGN_VERSION = "notebook-campaign-draft-1"
DEFAULT_NOTEBOOK_CAMPAIGN_BYTES = 33_554_432


@dataclass(frozen=True, slots=True)
class NotebookCampaignInputs:
    """External evidence locations, reverified on each operation; never serialized as authority."""

    binding: NotebookSourceBinding
    reviewed_contract_path: str | Path
    baseline_path: str | Path
    reference_capture_directory: str | Path
    project_root: str | Path


@dataclass(frozen=True, slots=True)
class NotebookCampaignRequest:
    """One exact task request and canonical proposed chat body, not evidence of dispatch."""

    request_id: str
    task_id: str
    source_request_sha256: str
    chat_body_json: str
    chat_body_sha256: str


@dataclass(frozen=True, slots=True)
class NotebookCampaign:
    """Frozen reviewed evidence, requested transport controls and a single pipeline denominator."""

    schema_version: str
    reviewed_contract_sha256: str
    reference_artifact_sha256: str
    source_binding_sha256: str
    ollama_controls_sha256: str
    execution_configuration_sha256: str
    expectations_sha256: str
    prompt_version: str
    body_schema_version: str
    body_assembly_version: str
    parameter_evidence_version: str
    validator_version: str
    base_url: str
    provider_timeout_seconds: float
    max_response_bytes: int
    max_request_bytes: int
    max_capture_file_bytes: int
    pipeline_attempt_budget: int
    requests: tuple[NotebookCampaignRequest, ...]
    content_sha256: str


@dataclass(frozen=True, slots=True)
class NotebookCampaignCapture:
    """Every planned slot, including unrequested and unfinished reservations; no runtime score."""

    campaign: NotebookCampaign
    capture: NotebookBodyCapture


def _payload(campaign: NotebookCampaign) -> dict[str, object]:
    return asdict(campaign)


def prepare_notebook_campaign(  # noqa: PLR0913
    inputs: NotebookCampaignInputs,
    controls: NotebookOllamaControls,
    *,
    provider_timeout_seconds: float = 120.0,
    max_response_bytes: int = DEFAULT_NOTEBOOK_BODY_RESPONSE_BYTES,
    max_request_bytes: int = 16_777_216,
    max_capture_file_bytes: int = DEFAULT_NOTEBOOK_CAPTURE_FILE_BYTES,
) -> NotebookCampaign:
    """Reverify reviewed reference and metadata, then freeze requests without HTTP or workers."""
    timeout = _number(provider_timeout_seconds, "provider_timeout_seconds")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("provider_timeout_seconds must be positive and finite")
    for limit in (max_response_bytes, max_request_bytes, max_capture_file_bytes):
        _limit(limit)
    if max_capture_file_bytes > DEFAULT_NOTEBOOK_CAPTURE_FILE_BYTES:
        raise ValueError("campaign capture files cannot exceed the 16 MiB hard limit")
    if max_response_bytes > max_capture_file_bytes:
        raise ValueError("max_response_bytes cannot exceed max_capture_file_bytes")
    contract = load_reviewed_notebook_contract(
        inputs.reviewed_contract_path,
        inputs.baseline_path,
        inputs.binding,
        inputs.reference_capture_directory,
        project_root=inputs.project_root,
    )
    reviewed_notebook_contract_to_dict(contract)
    notebook_ollama_controls_to_dict(controls)
    require_notebook_ollama_compatibility(controls, controls, controls)
    if controls.requested.num_ctx is None or controls.requested.num_predict is None:
        raise ValueError("campaign requires explicit num_ctx and num_predict budgets")
    requests = []
    for request in inputs.binding.requests:
        body = _to_json(
            {
                "model": controls.model_name,
                "messages": [{"role": "user", "content": render_node_body_prompt(request)}],
                "format": NODE_BODY_RESPONSE_JSON_SCHEMA,
                "options": controls.requested.to_options(),
                "stream": False,
                "think": False,
            }
        )
        raw = body.encode("utf-8")
        if len(raw) > max_request_bytes:
            raise ValueError("campaign chat body exceeds max_request_bytes")
        requests.append(
            NotebookCampaignRequest(
                request.request_id,
                request.task_id,
                _json_sha256(asdict(request)),
                body,
                hashlib.sha256(raw).hexdigest(),
            )
        )
    campaign = NotebookCampaign(
        NOTEBOOK_CAMPAIGN_VERSION,
        contract.content_sha256,
        contract.review.baseline_artifact_sha256,
        inputs.binding.content_sha256,
        controls.content_sha256,
        _json_sha256(asdict(contract.baseline.run.configuration)),
        contract.review.expectations_sha256,
        NODE_BODY_PROMPT_VERSION,
        NODE_BODY_SCHEMA_VERSION,
        NODE_BODY_ASSEMBLY_VERSION,
        NODE_CODE_PARAMETER_EVIDENCE_VERSION,
        NODE_CODE_VALIDATOR_VERSION,
        controls.base_url,
        timeout,
        max_response_bytes,
        max_request_bytes,
        max_capture_file_bytes,
        1,
        tuple(requests),
        "",
    )
    payload = _payload(campaign)
    payload.pop("content_sha256")
    return replace(campaign, content_sha256=_json_sha256(payload))


def create_notebook_campaign(  # noqa: PLR0913
    directory: str | Path,
    inputs: NotebookCampaignInputs,
    controls: NotebookOllamaControls,
    *,
    provider_timeout_seconds: float = 120.0,
    max_response_bytes: int = DEFAULT_NOTEBOOK_BODY_RESPONSE_BYTES,
    max_request_bytes: int = 16_777_216,
    max_capture_file_bytes: int = DEFAULT_NOTEBOOK_CAPTURE_FILE_BYTES,
    max_file_bytes: int = DEFAULT_NOTEBOOK_CAMPAIGN_BYTES,
) -> Path:
    """Publish a new single-attempt envelope and empty capture, never dispatch model requests."""
    _limit(max_file_bytes)
    campaign = prepare_notebook_campaign(
        inputs,
        controls,
        provider_timeout_seconds=provider_timeout_seconds,
        max_response_bytes=max_response_bytes,
        max_request_bytes=max_request_bytes,
        max_capture_file_bytes=max_capture_file_bytes,
    )
    payload = _payload(campaign)
    if len(_to_json(payload).encode("utf-8")) > max_file_bytes:
        raise ValueError("campaign manifest exceeds max_file_bytes")
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    create_notebook_body_capture(
        root / "capture",
        inputs.binding,
        project_root=inputs.project_root,
        provider_name="ollama",
        model_name=controls.model_name,
        prompt_version=campaign.prompt_version,
        max_response_bytes=campaign.max_response_bytes,
        max_file_bytes=campaign.max_capture_file_bytes,
    )
    _write(root / "manifest.json", payload, max_file_bytes)
    return root


def load_notebook_campaign(
    directory: str | Path,
    inputs: NotebookCampaignInputs,
    controls: NotebookOllamaControls,
    *,
    max_file_bytes: int = DEFAULT_NOTEBOOK_CAMPAIGN_BYTES,
) -> NotebookCampaignCapture:
    """Recheck reference evidence and inventory without parsing new outcomes, HTTP or workers."""
    _limit(max_file_bytes)
    root = Path(directory).resolve()
    if {path.name for path in root.iterdir()} != {"manifest.json", "capture"}:
        raise ValueError("unexpected campaign directory layout")
    if (root / "capture").is_symlink() or not (root / "capture").resolve().is_relative_to(root):
        raise ValueError("campaign capture must be contained in its directory")
    data = _read(root, root / "manifest.json", max_file_bytes)
    campaign = prepare_notebook_campaign(
        inputs,
        controls,
        provider_timeout_seconds=_number(data.get("provider_timeout_seconds"), "timeout"),
        **{
            name: _integer(data.get(name), name)
            for name in ("max_response_bytes", "max_request_bytes", "max_capture_file_bytes")
        },
    )
    if _json_sha256(data) != _json_sha256(_payload(campaign)):
        raise ValueError("campaign version, integrity or reconstructed evidence mismatch")
    capture = load_notebook_body_capture(
        root / "capture",
        inputs.binding,
        project_root=inputs.project_root,
        max_file_bytes=campaign.max_capture_file_bytes,
    )
    if (
        capture.provider_name,
        capture.model_name,
        capture.prompt_version,
        capture.max_response_bytes,
    ) != (
        "ollama",
        controls.model_name,
        campaign.prompt_version,
        campaign.max_response_bytes,
    ):
        raise ValueError("campaign capture controls mismatch")
    return NotebookCampaignCapture(campaign, capture)


def reserve_notebook_campaign_request(
    directory: str | Path,
    inputs: NotebookCampaignInputs,
    controls: NotebookOllamaControls,
    request_id: str,
) -> None:
    """Reserve a frozen slot exclusively; a future dispatcher must do this before provider I/O."""
    evidence = load_notebook_campaign(directory, inputs, controls)
    reserve_notebook_body_request(
        Path(directory) / "capture",
        inputs.binding,
        request_id,
        project_root=inputs.project_root,
        max_file_bytes=evidence.campaign.max_capture_file_bytes,
    )


def record_notebook_campaign_response(
    directory: str | Path,
    inputs: NotebookCampaignInputs,
    controls: NotebookOllamaControls,
    record: NotebookBodyRecord,
) -> None:
    """Publish a reserved raw outcome, never parse/approve it or silently replace a failure."""
    evidence = load_notebook_campaign(directory, inputs, controls)
    record_notebook_body_response(
        Path(directory) / "capture",
        inputs.binding,
        record,
        project_root=inputs.project_root,
        max_file_bytes=evidence.campaign.max_capture_file_bytes,
    )


def notebook_campaign_summary(evidence: NotebookCampaignCapture) -> dict[str, object]:
    """Describe an inspected inventory, not static acceptance, model accuracy or dispatch proof."""
    capture = evidence.capture
    records = {record.request_id: record for record in capture.records}
    attempted = set(capture.attempted_request_ids)
    slots = []
    for request in evidence.campaign.requests:
        record = records.get(request.request_id)
        if record is None:
            status = "unfinished" if request.request_id in attempted else "not_requested"
        else:
            status = "provider_error" if record.provider_error is not None else "raw_response"
        slots.append(
            {"request_id": request.request_id, "task_id": request.task_id, "status": status}
        )
    return {
        "campaign_sha256": evidence.campaign.content_sha256,
        "pipeline_attempt_budget": evidence.campaign.pipeline_attempt_budget,
        "planned_requests": len(evidence.campaign.requests),
        "reserved_requests": len(capture.attempted_request_ids),
        "published_outcomes": len(capture.records),
        "missing_request_ids": list(capture.missing_request_ids),
        "unfinished_request_ids": list(capture.unfinished_request_ids),
        "complete_inventory": capture.complete,
        "slots": slots,
    }
