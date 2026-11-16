"""Application-owned artifact writes, errors and result types."""

import json
from dataclasses import dataclass
from pathlib import Path

TRACE = []


@dataclass(frozen=True)
class Receipt:
    """Original application receipt, not an engine serializer."""

    path: Path
    bias: float


@dataclass(frozen=True)
class RunResult:
    """Original application result retains its receipt."""

    total: float
    receipt: Receipt


def measure(values: list[float]) -> tuple[float, ...]:
    """Load a trusted synthetic value sequence."""
    TRACE.append("load")
    return tuple(values)


def measure_file(path: str) -> tuple[float, ...]:
    """Keep raw-file interpretation inside the application loader."""
    return measure(json.loads(Path(path).read_text(encoding="utf-8")))


def write_report(candidate: dict) -> Receipt:
    """Create the application directory and retain owned partial writes on failure."""
    TRACE.append("write")
    output = Path(candidate["output"])
    if output.exists():
        raise FileExistsError("Application requires a new output directory")
    output.mkdir(parents=True)
    (output / "receipt.json").write_text(json.dumps({"bias": candidate["bias"]}), encoding="utf-8")
    if candidate.get("fail_after_write", False):
        raise RuntimeError("Application failed after its owned write")
    return Receipt(output, candidate["bias"])


def finish(values: tuple[float, ...], receipt: Receipt) -> RunResult:
    """Keep application references and scientific behavior unchanged."""
    TRACE.append("finish")
    return RunResult(sum(values) + receipt.bias, receipt)
