"""Application-owned readers and validation retained as opaque source."""

import json
from dataclasses import dataclass
from pathlib import Path

TRACE = []


@dataclass(frozen=True)
class Measurements:
    """Application dataset with explicit unit metadata."""

    values: tuple[float, ...]
    unit: str


@dataclass(frozen=True)
class Protocol:
    """Frozen unit and scaling rule for this synthetic example."""

    factor: float
    unit: str


def read_snapshot(path: str) -> Measurements:
    """Read values and their declared sibling metadata using application code."""
    TRACE.append("snapshot")
    source = Path(path)
    metadata = json.loads(source.with_suffix(".metadata.json").read_text())
    return Measurements(
        tuple(float(value) for value in source.read_text().split()), metadata["unit"]
    )


def read_protocol(path: str) -> Protocol:
    """Construct an application protocol rather than returning generic JSON."""
    TRACE.append("protocol")
    data = json.loads(Path(path).read_text())
    return Protocol(data["factor"], data["unit"])


def evaluate(dataset: Measurements, protocol: Protocol, candidate: dict[str, float]) -> dict:
    """Enforce unit compatibility and return an explicitly JSON-compatible summary."""
    TRACE.append("evaluate")
    if dataset.unit != protocol.unit:
        raise ValueError("Snapshot sidecar does not match the protocol unit")
    return {
        "total": sum(dataset.values) * protocol.factor + candidate["bias"],
        "unit": dataset.unit,
    }
