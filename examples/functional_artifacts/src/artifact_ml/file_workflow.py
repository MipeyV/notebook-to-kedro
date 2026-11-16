"""Combine staged raw paths, owned artifacts and an opaque memory result."""

from artifact_ml.domain import Receipt, RunResult, finish, measure_file, write_report


def load_values(path: str) -> tuple[float, ...]:
    """Interpret the staged path with the original application reader."""
    return measure_file(path)


def write_run(candidate: dict) -> Receipt:
    """Delegate artifact ownership to the original function."""
    return write_report(candidate)


def combine(values: tuple[float, ...], receipt: Receipt) -> RunResult:
    """Return the original typed application result."""
    return finish(values, receipt)


def workflow(values_path: str, candidate: dict) -> RunResult:
    """Preserve loader, independent writer and join ordering."""
    prepared = load_values(values_path)
    receipt = write_run(candidate)
    result = combine(prepared, receipt)
    return result
