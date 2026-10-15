from datetime import date

import pytest

from sazed.interfaces.dashboard.stats import (
    DECISION_GROUPS,
    Turn,
    daily_activity,
    daily_learned,
    decision_group,
    is_failure,
    totals,
)

FAILURES = frozenset({"AppNotFound", "ActionFailed"})
TODAY = date(2026, 10, 15)


def turn(at: str, decision: str, outcome: str = "", reaction: str = "none") -> Turn:
    return Turn(at, decision, outcome, reaction)


@pytest.mark.parametrize(
    ("decision", "group"),
    [
        ("Execute", "executed"),
        ("Confirm", "asked"),
        ("AskSlot", "asked"),
        ("NotUnderstood", "not_understood"),
        ("control", "control"),
        ("error", "error"),
        ("SomethingNew", "other"),
    ],
)
def test_decision_groups(decision: str, group: str) -> None:
    assert decision_group(decision) == group


@pytest.mark.parametrize(
    ("t", "failed"),
    [
        (turn("x", "Execute", "AppOpened"), False),
        (turn("x", "Execute", "AppNotFound"), True),
        (turn("x", "NotUnderstood"), True),
        (turn("x", "error", "ActionFailed"), True),
        (turn("x", "Execute", "AppOpened", "denied"), True),
        (turn("x", "Execute", "AppOpened", "corrected"), True),
        (turn("x", "Confirm", "", "confirmed"), False),
        (turn("x", "control"), False),
    ],
)
def test_is_failure(t: Turn, failed: bool) -> None:
    assert is_failure(t, FAILURES) is failed


def test_daily_activity_fills_every_day_of_the_window() -> None:
    turns = [
        turn("2026-10-15T10:00:00", "Execute", "AppOpened"),
        turn("2026-10-15T10:01:00", "Confirm"),
        turn("2026-10-15T10:02:00", "NotUnderstood"),
        turn("2026-10-15T10:03:00", "control"),
        turn("2026-10-13T08:00:00", "AskSlot"),
        turn("2026-09-01T08:00:00", "Execute"),  # outside the window
        turn("lixo", "Execute"),  # malformed date: skipped
    ]
    days = daily_activity(turns, FAILURES, today=TODAY, days=3)
    assert [d.day for d in days] == ["2026-10-13", "2026-10-14", "2026-10-15"]
    last = days[-1]
    assert (last.executed, last.asked, last.not_understood, last.control) == (1, 1, 1, 1)
    assert last.commands == 3  # control turns are not commands
    assert last.failures == 1
    assert last.failure_rate == pytest.approx(1 / 3)
    assert days[1].failure_rate is None  # nothing that day: unknown, not 0%
    assert days[0].asked == 1


def test_daily_learned_counts_per_day_and_cumulative() -> None:
    dates = [
        ("example", "2026-10-01T09:00:00"),  # before the window: only in the cumulative
        ("example", "2026-10-14T09:00:00"),
        ("alias", "2026-10-14T10:00:00"),
        ("example", "2026-10-15T09:00:00"),
        ("example", "quebrado"),
    ]
    days = daily_learned(dates, today=TODAY, days=2)
    assert [(d.day, d.examples, d.aliases) for d in days] == [
        ("2026-10-14", 1, 1),
        ("2026-10-15", 1, 0),
    ]
    assert [(d.total_examples, d.total_aliases) for d in days] == [(2, 1), (3, 1)]


def test_totals() -> None:
    turns = [
        turn("2026-10-15T10:00:00", "Execute", "AppOpened"),
        turn("2026-10-14T10:00:00", "Execute", "AppNotFound"),
        turn("2026-10-15T11:00:00", "Confirm", "", "confirmed"),
        turn("2026-10-15T12:00:00", "control"),
    ]
    summary = totals(turns, FAILURES, today=TODAY)
    assert summary.turns == 4
    assert summary.commands == 3
    assert summary.today == 2  # commands today; the "control" turn is not one
    assert summary.failures == 1
    assert summary.groups["executed"] == 2
    assert summary.groups["asked"] == 1
    assert set(summary.groups) == set(DECISION_GROUPS.values()) | {"other"}


def test_window_must_be_positive() -> None:
    with pytest.raises(ValueError):
        daily_activity([], FAILURES, today=TODAY, days=0)
