"""An internal domain value, not a persistent dataset serializer."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Intermediate:
    """Carry one synthetic value between original package functions."""

    value: float
