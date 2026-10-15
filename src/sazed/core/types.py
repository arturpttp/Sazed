"""Value types shared by every layer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Utterance:
    text: str
    normalized: str
    received_at: datetime


@dataclass(frozen=True)
class IntentScore:
    intent_id: str
    score: float


Ranking = tuple[IntentScore, ...]
"""Intent scores, best first."""


@dataclass(frozen=True)
class SlotValue:
    name: str
    value: str | int | bool
    raw: str
    confidence: float
    exact: bool = True


@dataclass(frozen=True)
class Ambiguous:
    """Several candidates fit equally well; the user must choose."""

    name: str
    raw: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class Unmatched:
    """The user named something, but nothing known matches it."""

    name: str
    raw: str
    suggestion: str | None


Extraction = SlotValue | Ambiguous | Unmatched
Slots = Mapping[str, SlotValue | Unmatched]
"""Slots handed to a skill. Ambiguous values never reach a skill."""


@dataclass(frozen=True)
class ParseResult:
    utterance: Utterance
    ranking: Ranking
    slots: Mapping[str, Extraction]
    missing_slots: frozenset[str]
