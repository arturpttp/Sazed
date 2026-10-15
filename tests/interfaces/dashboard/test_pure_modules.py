"""The dashboard's pure modules: stdlib only, no I/O, no clock; and rules that are
restated from elsewhere agree with their source."""

import ast
import itertools
import sys
from datetime import datetime
from pathlib import Path

import pytest

from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.coppermind import Episode, Reaction
from sazed.core.outcomes import FAILURE_NAMES
from sazed.interfaces.dashboard.stats import Turn, is_failure

PACKAGE = Path(__file__).resolve().parents[3] / "src" / "sazed" / "interfaces" / "dashboard"
PURE_MODULES = ["ledger", "stats", "redact", "processes"]
IMPURE_ATTRIBUTES = {"now", "today", "utcnow", "getenv", "environ", "read_text", "open"}
IMPURE_NAMES = {"open", "input", "print"}


@pytest.mark.parametrize("module", PURE_MODULES)
def test_pure_module_is_stdlib_only_without_io_or_clock(module: str) -> None:
    tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            problems += [n for n in names if n.split(".")[0] not in sys.stdlib_module_names]
        if isinstance(node, ast.Attribute) and node.attr in IMPURE_ATTRIBUTES:
            problems.append(f".{node.attr}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in IMPURE_NAMES
        ):
            problems.append(f"{node.func.id}()")
    assert problems == []


def test_is_failure_agrees_with_the_store(tmp_path: Path) -> None:
    store = SqliteCoppermind(tmp_path / "c.db")
    decisions = ["Execute", "Confirm", "AskSlot", "NotUnderstood", "control", "error"]
    outcomes = ["", "AppOpened", *sorted(FAILURE_NAMES)]
    turns: dict[int, Turn] = {}
    for decision, outcome, reaction in itertools.product(decisions, outcomes, list(Reaction)):
        episode_id = store.record_episode(
            Episode("x", datetime(2026, 10, 15), (), {}, decision, None, outcome, reaction)
        )
        turns[episode_id] = Turn("", decision, outcome, reaction.value)
    from_store = {s.id for s in store.recent_failures(limit=len(turns))}
    from_dashboard = {i for i, t in turns.items() if is_failure(t, FAILURE_NAMES)}
    store.close()
    assert from_dashboard == from_store
    assert 0 < len(from_store) < len(turns)


def test_only_the_cli_imports_the_dashboard() -> None:
    src = PACKAGE.parents[1]
    importers = []
    for file in sorted(src.rglob("*.py")):
        if PACKAGE in file.parents:
            continue
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "sazed.interfaces.dashboard"
            ):
                importers.append(file.relative_to(src).as_posix())
    assert importers == ["interfaces/cli/main.py"]
