"""Short-term dialogue memory. Pure: `now` is always passed in."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

from sazed.core.types import Slots


@dataclass(frozen=True)
class AliasCandidate:
    slot: str
    alias: str
    value: str


@dataclass(frozen=True)
class AwaitConfirm:
    intent_id: str
    slots: Slots
    utterance: str
    learn_example: bool
    alias: AliasCandidate | None = None


@dataclass(frozen=True)
class AwaitSlot:
    intent_id: str
    slots: Slots
    slot: str
    candidates: tuple[str, ...]
    raw: str
    utterance: str


@dataclass(frozen=True)
class AwaitLearn:
    """Sazed asked "may I remember that <text> means this?"."""

    text: str
    intent_id: str


@dataclass(frozen=True)
class AwaitPlan:
    """A skill proposed an exact change (a file change or its undo); "sim" applies it."""

    skill_id: str
    utterance: str


Pending = AwaitConfirm | AwaitSlot | AwaitLearn | AwaitPlan


class LastKind(Enum):
    EXECUTED = "executed"
    NOT_UNDERSTOOD = "not_understood"
    APP_NOT_FOUND = "app_not_found"


@dataclass(frozen=True)
class LastTurn:
    kind: LastKind
    utterance: str
    intent_id: str | None
    slots: Slots
    raw_query: str | None


@dataclass(frozen=True)
class DialogueContext:
    pending: Pending | None = None
    pending_at: datetime | None = None
    last: LastTurn | None = None
    last_at: datetime | None = None

    def expire(self, now: datetime, ttl_seconds: float) -> DialogueContext:
        ttl = timedelta(seconds=ttl_seconds)
        ctx = self
        if ctx.pending_at is not None and now - ctx.pending_at > ttl:
            ctx = ctx.without_pending()
        if ctx.last_at is not None and now - ctx.last_at > ttl:
            ctx = replace(ctx, last=None, last_at=None)
        return ctx

    def with_pending(self, pending: Pending, now: datetime) -> DialogueContext:
        return replace(self, pending=pending, pending_at=now)

    def without_pending(self) -> DialogueContext:
        return replace(self, pending=None, pending_at=None)

    def with_last(self, last: LastTurn, now: datetime) -> DialogueContext:
        return replace(self, last=last, last_at=now)
