"""Declared source ordering around an independent application writer."""

from artifact_ml.domain import Receipt, RunResult, finish, measure, write_report


def load_values(raw: list[float]) -> tuple[float, ...]:
    """Delegate to application loading."""
    return measure(raw)


def write_run(candidate: dict) -> Receipt:
    """Delegate owned effects to the original application function."""
    return write_report(candidate)


def combine(values: tuple[float, ...], receipt: Receipt) -> RunResult:
    """Return the original application result."""
    return finish(values, receipt)


def workflow(values: list[float], candidate: dict) -> RunResult:
    """Keep loader, independent writer and join in explicit source order."""
    prepared = load_values(values)
    receipt = write_run(candidate)
    result = combine(prepared, receipt)
    return result
