"""The four ways a command can end."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sazed.core.types import Slots


class ConfirmReason(Enum):
    LOW_SCORE = "low_score"
    SMALL_GAP = "small_gap"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class Execute:
    intent_id: str
    slots: Slots


@dataclass(frozen=True)
class Confirm:
    intent_id: str
    slots: Slots
    reason: ConfirmReason


@dataclass(frozen=True)
class AskSlot:
    intent_id: str
    slots: Slots
    slot: str
    candidates: tuple[str, ...]
    raw: str


@dataclass(frozen=True)
class NotUnderstood:
    pass


Decision = Execute | Confirm | AskSlot | NotUnderstood
