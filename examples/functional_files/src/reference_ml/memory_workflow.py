"""Explicit workflow returning an application result without JSON coercion."""

from reference_ml.domain import (
    EvaluationResult,
    Measurements,
    Protocol,
    evaluate_result,
    read_protocol,
    read_snapshot,
)


def load_snapshot(path: str) -> Measurements:
    """Construct the original domain dataset."""
    return read_snapshot(path)


def load_protocol(path: str) -> Protocol:
    """Construct the original domain protocol."""
    return read_protocol(path)


def evaluate_candidate(
    dataset: Measurements, protocol: Protocol, candidate: dict
) -> EvaluationResult:
    """Return the original application result unchanged."""
    return evaluate_result(dataset, protocol, candidate)


def workflow(snapshot_path: str, protocol_path: str, candidate: dict) -> EvaluationResult:
    """Preserve declared loader order and the final result object."""
    dataset = load_snapshot(snapshot_path)
    protocol = load_protocol(protocol_path)
    result = evaluate_candidate(dataset, protocol, candidate)
    return result
