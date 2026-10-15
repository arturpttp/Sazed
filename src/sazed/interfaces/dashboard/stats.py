"""Aggregations over episodes and learned items, for the charts. Pure: `today` is a parameter."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

DECISION_GROUPS: dict[str, str] = {
    "Execute": "executed",
    "Confirm": "asked",
    "AskSlot": "asked",
    "NotUnderstood": "not_understood",
    "control": "control",
    "error": "error",
}
GROUPS: tuple[str, ...] = (*dict.fromkeys(DECISION_GROUPS.values()), "other")
FAILED_REACTIONS = frozenset({"denied", "corrected"})
FAILED_DECISIONS = frozenset({"NotUnderstood", "error"})


@dataclass(frozen=True)
class Turn:
    at: str
    decision: str
    outcome: str
    reaction: str


@dataclass(frozen=True)
class DayActivity:
    day: str
    executed: int
    asked: int
    not_understood: int
    control: int
    error: int
    other: int
    commands: int
    """Every turn except dialogue control ("sim", "esquece isso")."""
    failures: int
    failure_rate: float | None
    """None when there were no commands that day: unknown, not 0%."""


@dataclass(frozen=True)
class DayLearned:
    day: str
    examples: int
    aliases: int
    total_examples: int
    total_aliases: int


@dataclass(frozen=True)
class Totals:
    turns: int
    commands: int
    today: int
    failures: int
    groups: dict[str, int]


def decision_group(decision: str) -> str:
    return DECISION_GROUPS.get(decision, "other")


def is_failure(turn: Turn, failure_outcomes: frozenset[str]) -> bool:
    """Same rule as `SqliteCoppermind.recent_failures` (a test asserts they agree)."""
    return (
        turn.decision in FAILED_DECISIONS
        or turn.reaction in FAILED_REACTIONS
        or turn.outcome in failure_outcomes
    )


def _day(stamp: str) -> date | None:
    try:
        return datetime.fromisoformat(stamp).date()
    except ValueError:
        return None


def _window(today: date, days: int) -> list[date]:
    if days < 1:
        raise ValueError("days must be at least 1")
    return [today - timedelta(days=n) for n in range(days - 1, -1, -1)]


def daily_activity(
    turns: Iterable[Turn], failure_outcomes: frozenset[str], *, today: date, days: int
) -> list[DayActivity]:
    window = _window(today, days)
    groups: dict[date, Counter[str]] = {d: Counter() for d in window}
    failures: Counter[date] = Counter()
    for turn in turns:
        day = _day(turn.at)
        if day not in groups:
            continue
        group = decision_group(turn.decision)
        groups[day][group] += 1
        if group != "control" and is_failure(turn, failure_outcomes):
            failures[day] += 1
    result = []
    for day in window:
        counts = groups[day]
        commands = sum(counts.values()) - counts["control"]
        result.append(
            DayActivity(
                day.isoformat(),
                executed=counts["executed"],
                asked=counts["asked"],
                not_understood=counts["not_understood"],
                control=counts["control"],
                error=counts["error"],
                other=counts["other"],
                commands=commands,
                failures=failures[day],
                failure_rate=failures[day] / commands if commands else None,
            )
        )
    return result


def daily_learned(dates: Iterable[tuple[str, str]], *, today: date, days: int) -> list[DayLearned]:
    window = _window(today, days)
    per_day: dict[date, Counter[str]] = {d: Counter() for d in window}
    before: Counter[str] = Counter()
    for kind, stamp in dates:
        day = _day(stamp)
        if day is None:
            continue
        if day in per_day:
            per_day[day][kind] += 1
        elif day < window[0]:
            before[kind] += 1
    running = Counter(before)
    result = []
    for day in window:
        running.update(per_day[day])
        result.append(
            DayLearned(
                day.isoformat(),
                per_day[day]["example"],
                per_day[day]["alias"],
                running["example"],
                running["alias"],
            )
        )
    return result


def totals(turns: Iterable[Turn], failure_outcomes: frozenset[str], *, today: date) -> Totals:
    groups = dict.fromkeys(GROUPS, 0)
    count = failures = on_day = 0
    for turn in turns:
        count += 1
        group = decision_group(turn.decision)
        groups[group] += 1
        if group == "control":
            continue
        on_day += _day(turn.at) == today
        failures += is_failure(turn, failure_outcomes)
    return Totals(count, count - groups["control"], on_day, failures, groups)
