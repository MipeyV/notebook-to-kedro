"""Explicit ordered loaders; original application readers own data interpretation."""

from reference_ml.domain import Measurements, Protocol, evaluate, read_protocol, read_snapshot


def load_snapshot(path: str) -> Measurements:
    """Delegate snapshot interpretation to the original domain reader."""
    return read_snapshot(path)


def load_protocol(path: str) -> Protocol:
    """Delegate scientific settings interpretation to the original reader."""
    return read_protocol(path)


def evaluate_candidate(dataset: Measurements, protocol: Protocol, candidate: dict) -> dict:
    """Keep domain validation inside the original application function."""
    return evaluate(dataset, protocol, candidate)


def workflow(snapshot_path: str, protocol_path: str, candidate: dict) -> dict:
    """Read two independent inputs in order, then evaluate once."""
    dataset = load_snapshot(snapshot_path)
    protocol = load_protocol(protocol_path)
    result = evaluate_candidate(dataset, protocol, candidate)
    return result
