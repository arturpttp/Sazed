from datetime import datetime, timedelta

from sazed.core.context import (
    AwaitConfirm,
    AwaitLearn,
    DialogueContext,
    LastKind,
    LastTurn,
)

T0 = datetime(2026, 10, 14, 12, 0, 0)
TTL = 60.0
PENDING = AwaitConfirm("abrir_app", {}, "abre o crome", learn_example=True)
LAST = LastTurn(LastKind.EXECUTED, "aumenta o volume", "volume_aumentar", {}, None)


def test_pending_survives_before_ttl() -> None:
    ctx = DialogueContext().with_pending(PENDING, T0)
    assert ctx.expire(T0 + timedelta(seconds=59), TTL).pending == PENDING


def test_pending_survives_exactly_at_ttl() -> None:
    ctx = DialogueContext().with_pending(PENDING, T0)
    assert ctx.expire(T0 + timedelta(seconds=60), TTL).pending == PENDING


def test_pending_expires_after_ttl() -> None:
    ctx = DialogueContext().with_pending(PENDING, T0)
    assert ctx.expire(T0 + timedelta(seconds=61), TTL).pending is None


def test_last_turn_expires_independently_of_pending() -> None:
    ctx = DialogueContext().with_last(LAST, T0).with_pending(PENDING, T0 + timedelta(seconds=30))
    later = ctx.expire(T0 + timedelta(seconds=75), TTL)
    assert later.last is None
    assert later.pending == PENDING


def test_new_pending_replaces_the_old_one() -> None:
    other = AwaitLearn("abre o zap", "abrir_app")
    ctx = DialogueContext().with_pending(PENDING, T0).with_pending(other, T0)
    assert ctx.pending == other


def test_without_pending_keeps_last() -> None:
    ctx = DialogueContext().with_last(LAST, T0).with_pending(PENDING, T0).without_pending()
    assert ctx.pending is None
    assert ctx.last == LAST


def test_context_is_immutable() -> None:
    ctx = DialogueContext()
    ctx.with_pending(PENDING, T0)
    assert ctx.pending is None
