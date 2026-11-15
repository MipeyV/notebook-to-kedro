"""Opaque support module retained byte for byte, with relative imports."""

from .domain import Intermediate
from .settings import offset


def prepare_value(values: float, scale: float) -> Intermediate:
    """Build an internal object using a package-relative resource."""
    return Intermediate(values * scale + offset())


def finish_value(prepared: Intermediate) -> dict:
    """Return JSON values that expose the preserved module identities."""
    return {
        "value": prepared.value,
        "type_module": type(prepared).__module__,
        "helper_module": prepare_value.__module__,
    }
