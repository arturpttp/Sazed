import pytest

from sazed.interfaces.dashboard.ledger import (
    LedgerEntry,
    PlanTask,
    choose_active_plan,
    current_task,
    parse_git_log,
    parse_ledger,
    parse_plan_tasks,
    proof_summary,
    task_statuses,
)

LEDGER = """# SDD ledger — plan: docs/superpowers/plans/2026-10-15-sazed-pc-skills-2a.md

Task 1: started
Task 1: Ruling: keep the fake clock in tests/fakes
Task 1: complete (commits abc1234..def5678, tests: uv run pytest → 412 passed)
Task 2: started
algo que ninguém previu
Final: Ruling: power intents are never learned
Final: minor (deferred): rename the brightness port
Final: fixed the Desinstalação filter
"""


def test_header_names_the_plan() -> None:
    assert parse_ledger(LEDGER).plan == "docs/superpowers/plans/2026-10-15-sazed-pc-skills-2a.md"


def test_every_non_blank_line_is_kept_in_order() -> None:
    entries = parse_ledger(LEDGER).entries
    expected = [line for line in LEDGER.splitlines()[1:] if line.strip()]
    assert [e.line for e in entries] == expected


@pytest.mark.parametrize(
    ("line", "kind", "task", "text"),
    [
        ("Task 1: started", "started", 1, ""),
        ("- Task 12: started", "started", 12, ""),
        ("Task 3: Ruling: use psutil", "ruling", 3, "use psutil"),
        ("Final: Ruling: never learn power", "ruling", None, "never learn power"),
        ("Ruling: bare ruling", "ruling", None, "bare ruling"),
        ("Final: minor (deferred): rename X", "deferred", None, "rename X"),
        ("Final: fixed the filter", "fixed", None, "the filter"),
        ("algo que ninguém previu", "raw", None, "algo que ninguém previu"),
        ("Task x: started", "raw", None, "Task x: started"),
        ("## Notes", "raw", None, "## Notes"),
    ],
)
def test_line_kinds(line: str, kind: str, task: int | None, text: str) -> None:
    (entry,) = parse_ledger(line).entries
    assert (entry.kind, entry.task, entry.text, entry.line) == (kind, task, text, line)


def test_ruling_scope() -> None:
    task_ruling, final_ruling = (e for e in parse_ledger(LEDGER).entries if e.kind == "ruling")
    assert (task_ruling.scope, final_ruling.scope) == ("Task 1", "Final")


def test_complete_line_carries_commits_and_tests() -> None:
    (entry,) = parse_ledger(
        "Task 4: complete (commits 1a2b3c4..5d6e7f8,"
        " tests: uv run pytest -q → 400 passed, 2 skipped)"
    ).entries
    assert entry.kind == "complete"
    assert entry.task == 4
    assert entry.commits == "1a2b3c4..5d6e7f8"
    assert entry.tests_command == "uv run pytest -q"
    assert entry.tests_result == "400 passed, 2 skipped"


@pytest.mark.parametrize(
    "line",
    ["Task 4: complete", "Task 4: complete (sem detalhes)", "Task 4: complete (tests: x -> ok)"],
)
def test_complete_line_tolerates_missing_details(line: str) -> None:
    (entry,) = parse_ledger(line).entries
    assert (entry.kind, entry.task) == ("complete", 4)


def test_ascii_arrow_is_accepted() -> None:
    (entry,) = parse_ledger("Task 2: complete (commits a1..b2, tests: pytest -> 3 passed)").entries
    assert (entry.tests_command, entry.tests_result) == ("pytest", "3 passed")


def test_missing_header_means_unknown_plan() -> None:
    ledger = parse_ledger("Task 1: started\n")
    assert ledger.plan is None
    assert [e.kind for e in ledger.entries] == ["started"]


def test_empty_ledger() -> None:
    ledger = parse_ledger("")
    assert (ledger.plan, ledger.entries) == (None, ())


PLAN = """# Plan

### Task 1: Fix the deferred minors
text
### Task 2: Media skill
## Not a task
### Task 10: Docs
### Taskless heading
"""


def test_plan_tasks_are_the_task_headings() -> None:
    assert parse_plan_tasks(PLAN) == [
        PlanTask(1, "Fix the deferred minors"),
        PlanTask(2, "Media skill"),
        PlanTask(10, "Docs"),
    ]


def test_task_statuses_merge_plan_and_ledger() -> None:
    statuses = task_statuses(parse_plan_tasks(PLAN), parse_ledger(LEDGER))
    assert [(s.number, s.status) for s in statuses] == [(1, "done"), (2, "active"), (10, "pending")]
    done = statuses[0]
    assert done.commits == "abc1234..def5678"
    assert (done.tests_command, done.tests_result) == ("uv run pytest", "412 passed")
    assert done.rulings == ("keep the fake clock in tests/fakes",)


def test_a_task_only_in_the_ledger_is_still_shown() -> None:
    statuses = task_statuses([PlanTask(1, "A")], parse_ledger("Task 7: started"))
    assert [(s.number, s.title, s.status) for s in statuses] == [
        (1, "A", "pending"),
        (7, "(fora do plano)", "active"),
    ]


def test_current_task_is_the_latest_started_not_completed() -> None:
    statuses = task_statuses(parse_plan_tasks(PLAN), parse_ledger(LEDGER))
    current = current_task(statuses)
    assert current is not None and current.number == 2


def test_no_current_task_when_nothing_is_active() -> None:
    assert current_task(task_statuses([PlanTask(1, "A")], parse_ledger(""))) is None


def test_active_plan_is_the_newest_with_a_ledger() -> None:
    plans = ["2026-10-14-sazed-core", "2026-10-15-pc-2a", "2026-10-16-voice"]
    assert choose_active_plan(plans, {"2026-10-14-sazed-core", "2026-10-15-pc-2a"}) == (
        "2026-10-15-pc-2a"
    )
    assert choose_active_plan(plans, set()) is None


def test_git_log_parsing() -> None:
    text = (
        "abc123\x1f2026-10-15T10:00:00-03:00\x1fArtur\x1ffeat(x): one\x1e\n"
        "def456\x1f2026-10-14T09:00:00-03:00\x1fArtur\x1ffix(y): two | pipes\x1e\n"
    )
    commits = parse_git_log(text)
    assert [(c.sha, c.subject) for c in commits] == [
        ("abc123", "feat(x): one"),
        ("def456", "fix(y): two | pipes"),
    ]
    assert commits[0].date == "2026-10-15T10:00:00-03:00"
    assert commits[0].author == "Artur"


def test_git_log_skips_malformed_records() -> None:
    assert parse_git_log("lixo\x1e\n\x1e") == []


def test_proof_summary() -> None:
    title, sections = proof_summary("# Proofs — x\n\n## 1. Thing\nbody\n## 2. Other\n")
    assert title == "Proofs — x"
    assert sections == ["1. Thing", "2. Other"]
    assert proof_summary("sem título") == ("", [])


def test_entry_is_a_value() -> None:
    entry = parse_ledger("Task 1: started").entries[0]
    assert isinstance(entry, LedgerEntry)
