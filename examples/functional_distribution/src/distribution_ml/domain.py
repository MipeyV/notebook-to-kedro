"""Read metadata through normal Python distribution and resource APIs."""

import hashlib
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path


def summarize(value: float, factor: float) -> dict:
    """Expose independent metadata, resource and source-relative observations."""
    lock = Path(__file__).parent.parent.parent / "application.lock"
    return {
        "value": value * factor,
        "version": version("synthetic-distribution-example"),
        "resource": files("distribution_ml").joinpath("resource.txt").read_text().strip(),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None,
    }
