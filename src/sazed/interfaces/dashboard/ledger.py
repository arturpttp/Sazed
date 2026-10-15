"""Development progress: the SDD ledger, plan task headings, git log and proofs. Pure.

The ledger is written by another agent and its format may drift, so parsing is tolerant:
a line that matches no known pattern is kept as a `raw` entry, never dropped.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

_HEADER = re.compile(r"^#\s*SDD ledger\b.*?\bplan:\s*(?P<plan>.+?)\s*$", re.IGNORECASE)
_RULING = re.compile(r"(?:(?P<scope>Task\s+(?P<task>\d+)|Final)\s*:\s*)?Ruling:\s*(?P<text>.*)$")
_STARTED = re.compile(r"\bTask\s+(?P<task>\d+)\s*:\s*started\b")
_COMPLETE = re.compile(r"\bTask\s+(?P<task>\d+)\s*:\s*complete\b(?P<rest>.*)$")
_COMMITS = re.compile(r"commits\s+(?P<commits>[0-9a-fA-F]+\.\.[0-9a-fA-F]+)")
_TESTS = re.compile(r"tests:\s*(?P<command>.+?)\s*(?:→|->)\s*(?P<result>.+?)\)?\s*$")
_DEFERRED = re.compile(r"\bFinal\s*:\s*minor\s*\(deferred\)\s*:\s*(?P<text>.*)$")
_FIXED = re.compile(r"\bFinal\s*:\s*fixed\s+(?P<text>.*)$")
_PLAN_TASK = re.compile(r"^###\s+Task\s+(?P<number>\d+)\s*:\s*(?P<title>.+?)\s*$")
_HEADING = re.compile(r"^(?P<marks>#{1,6})\s+(?P<text>.+?)\s*$")

OUTSIDE_PLAN = "(fora do plano)"


@dataclass(frozen=True)
class LedgerEntry:
    kind: str
    """started | complete | ruling | deferred | fixed | raw"""
    line: str
    task: int | None = None
    scope: str | None = None
    text: str = ""
    commits: str | None = None
    tests_command: str | None = None
    tests_result: str | None = None


@dataclass(frozen=True)
class Ledger:
    plan: str | None
    entries: tuple[LedgerEntry, ...]


@dataclass(frozen=True)
class PlanTask:
    number: int
    title: str


@dataclass(frozen=True)
class TaskStatus:
    number: int
    title: str
    status: str
    """done | active | pending"""
    commits: str | None = None
    tests_command: str | None = None
    tests_result: str | None = None
    rulings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Commit:
    sha: str
    date: str
    author: str
    subject: str


def _entry(line: str) -> LedgerEntry:
    if ruling := _RULING.search(line):
        task = ruling.group("task")
        scope = ruling.group("scope")
        return LedgerEntry(
            "ruling",
            line,
            task=int(task) if task else None,
            scope=re.sub(r"\s+", " ", scope) if scope else None,
            text=ruling.group("text").strip(),
        )
    if done := _COMPLETE.search(line):
        rest = done.group("rest")
        commits = _COMMITS.search(rest)
        tests = _TESTS.search(rest)
        return LedgerEntry(
            "complete",
            line,
            task=int(done.group("task")),
            commits=commits.group("commits") if commits else None,
            tests_command=tests.group("command") if tests else None,
            tests_result=tests.group("result") if tests else None,
        )
    if started := _STARTED.search(line):
        return LedgerEntry("started", line, task=int(started.group("task")))
    if deferred := _DEFERRED.search(line):
        return LedgerEntry("deferred", line, text=deferred.group("text").strip())
    if fixed := _FIXED.search(line):
        return LedgerEntry("fixed", line, text=fixed.group("text").strip())
    return LedgerEntry("raw", line, text=line)


def parse_ledger(text: str) -> Ledger:
    lines = text.splitlines()
    plan = None
    if lines and (header := _HEADER.match(lines[0].strip())):
        plan = header.group("plan")
        lines = lines[1:]
    return Ledger(plan, tuple(_entry(line) for line in lines if line.strip()))


def parse_plan_tasks(text: str) -> list[PlanTask]:
    tasks = []
    for line in text.splitlines():
        if found := _PLAN_TASK.match(line.strip()):
            tasks.append(PlanTask(int(found.group("number")), found.group("title")))
    return tasks


def task_statuses(tasks: Sequence[PlanTask], ledger: Ledger) -> list[TaskStatus]:
    titles = {t.number: t.title for t in tasks}
    started: set[int] = set()
    completed: dict[int, LedgerEntry] = {}
    rulings: dict[int, list[str]] = {}
    for entry in ledger.entries:
        if entry.task is None:
            continue
        if entry.kind == "started":
            started.add(entry.task)
        elif entry.kind == "complete":
            completed[entry.task] = entry
        elif entry.kind == "ruling":
            rulings.setdefault(entry.task, []).append(entry.text)
    numbers = sorted(set(titles) | started | set(completed) | set(rulings))
    result = []
    for number in numbers:
        done = completed.get(number)
        status = "done" if done else "active" if number in started else "pending"
        result.append(
            TaskStatus(
                number,
                titles.get(number, OUTSIDE_PLAN),
                status,
                commits=done.commits if done else None,
                tests_command=done.tests_command if done else None,
                tests_result=done.tests_result if done else None,
                rulings=tuple(rulings.get(number, ())),
            )
        )
    return result


def current_task(statuses: Sequence[TaskStatus]) -> TaskStatus | None:
    active = [s for s in statuses if s.status == "active"]
    return active[-1] if active else None


def choose_active_plan(plan_stems: Iterable[str], ledger_stems: set[str]) -> str | None:
    """Plan files are named by date, so the newest is the greatest name."""
    with_ledger = [stem for stem in plan_stems if stem in ledger_stems]
    return max(with_ledger) if with_ledger else None


GIT_LOG_FORMAT = "%H%x1f%cI%x1f%an%x1f%s%x1e"


def parse_git_log(text: str) -> list[Commit]:
    commits = []
    for record in text.split("\x1e"):
        fields = record.strip("\r\n").split("\x1f")
        if len(fields) == 4 and fields[0]:
            commits.append(Commit(*fields))
    return commits


def proof_summary(text: str) -> tuple[str, list[str]]:
    title = ""
    sections = []
    for line in text.splitlines():
        if found := _HEADING.match(line):
            if len(found.group("marks")) == 1 and not title:
                title = found.group("text")
            elif len(found.group("marks")) == 2:
                sections.append(found.group("text"))
    return title, sections
