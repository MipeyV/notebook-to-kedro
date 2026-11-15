"""Load a resource relative to the copied package file."""

import json
from pathlib import Path


def offset() -> float:
    """Return the explicitly supplied resource value."""
    data = json.loads(
        (Path(__file__).parent / "assets" / "offset.json").read_text(encoding="utf-8")
    )
    return float(data["offset"])
