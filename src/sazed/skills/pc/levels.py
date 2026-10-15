"""Level arithmetic shared by volume and brightness: steps, absolute levels, range checks."""

from __future__ import annotations

from collections.abc import Callable

from sazed.core.outcomes import InvalidPercent
from sazed.core.types import Slots, SlotValue, Unmatched

DEFAULT_STEP = 10


def int_slot(slots: Slots, name: str) -> int | None:
    value = slots.get(name)
    return int(value.value) if isinstance(value, SlotValue) else None


def invalid_level(slots: Slots) -> InvalidPercent | None:
    for name in ("percent", "alvo"):
        value = slots.get(name)
        if isinstance(value, Unmatched):
            return InvalidPercent(value.raw)
    return None


def clamp(n: int) -> int:
    return max(0, min(100, n))


def stepped(current: int, sign: int, slots: Slots) -> tuple[int, bool]:
    """The level after an up/down command, and whether it was named as an absolute level."""
    level = int_slot(slots, "alvo")
    if level is not None:
        return clamp(level), True
    step = int_slot(slots, "percent")
    # `is None`, not a truthy check: a step of 0 is a real (if odd) request.
    return clamp(current + sign * (DEFAULT_STEP if step is None else step)), False


def level_label(default: str, noun: str) -> Callable[[Slots], str]:
    def describe(slots: Slots) -> str:
        level = int_slot(slots, "alvo")
        return f"deixar {noun} em {level}%" if level is not None else default

    return describe
