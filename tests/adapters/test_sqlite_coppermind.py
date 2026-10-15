import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from sazed.adapters.sqlite.coppermind import (
    MIGRATIONS,
    CoppermindVersionError,
    SqliteCoppermind,
)
from sazed.core.coppermind import (
    Episode,
    LearnedKind,
    NewAlias,
    NewExample,
    Reaction,
    StoredAlias,
)
from sazed.core.types import IntentScore

T0 = datetime(2026, 10, 14, 12, 0, 0)
EX = NewExample("abre aí o chrome", "abrir_app", b"\x01\x02\x03\x04", "confirmed")
AL = NewAlias("app", "zap", "WhatsApp")


def open_store(tmp_path: Path) -> SqliteCoppermind:
    return SqliteCoppermind(tmp_path / "sub" / "coppermind.db")


def test_learned_example_and_alias_survive_reopening(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    store.learn([EX], [AL], T0)
    store.close()
    reopened = open_store(tmp_path)
    (example,) = reopened.examples()
    assert (example.text, example.intent_id, example.embedding) == (
        "abre aí o chrome",
        "abrir_app",
        b"\x01\x02\x03\x04",
    )
    assert [(a.slot, a.alias, a.value) for a in reopened.aliases()] == [("app", "zap", "WhatsApp")]


def test_a_learning_step_that_fails_midway_leaves_no_rows(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    broken = NewAlias("app", "zap", None)  # type: ignore[arg-type]
    with pytest.raises(sqlite3.IntegrityError):
        store.learn([EX], [broken], T0)
    store.close()
    reopened = open_store(tmp_path)
    assert reopened.examples() == []
    assert reopened.learned() == []


def test_learned_lists_newest_first(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    store.learn([EX], [], T0)
    store.learn([], [AL], T0 + timedelta(seconds=5))
    assert [i.kind for i in store.learned()] == [LearnedKind.ALIAS, LearnedKind.EXAMPLE]


def test_forget_latest_removes_the_whole_latest_batch_and_nothing_else(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    store.learn([EX], [], T0)
    other = NewExample("liga o navegador", "abrir_app", b"\x00" * 4, "offered")
    store.learn([other], [AL], T0 + timedelta(seconds=5))
    forgotten = store.forget_latest()
    assert sorted(i.text for i in forgotten) == ["liga o navegador", "zap"]
    assert [e.text for e in store.examples()] == ["abre aí o chrome"]
    assert store.aliases() == []


def test_forget_latest_with_nothing_learned(tmp_path: Path) -> None:
    assert open_store(tmp_path).forget_latest() == []


def test_forget_by_id(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    (item,) = store.learn([EX], [], T0)
    assert store.forget(LearnedKind.EXAMPLE, item.id) == item
    assert store.examples() == []
    assert store.forget(LearnedKind.EXAMPLE, item.id) is None


def test_relearning_an_alias_replaces_its_value(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    store.learn([], [NewAlias("app", "code", "Claude Code")], T0)
    store.learn([], [NewAlias("app", "code", "Visual Studio Code")], T0)
    assert [(a.alias, a.value) for a in store.aliases()] == [("code", "Visual Studio Code")]


def test_fresh_database_is_at_the_latest_schema(tmp_path: Path) -> None:
    assert open_store(tmp_path).schema_version == len(MIGRATIONS)


def test_database_from_a_newer_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "coppermind.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    with pytest.raises(CoppermindVersionError):
        SqliteCoppermind(path)


def test_episode_round_trip_and_reaction_update(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    episode = Episode(
        utterance="Abre o Chrome!",
        at=T0,
        ranking=(IntentScore("abrir_app", 0.95), IntentScore("fechar_app", 0.6)),
        slots={"app": "Google Chrome"},
        decision="Execute",
        intent_id="abrir_app",
        outcome="AppOpened",
    )
    episode_id = store.record_episode(episode)
    store.set_reaction(episode_id, Reaction.CORRECTED)
    stored = store.episode(episode_id)
    assert stored is not None
    assert stored.episode.ranking == episode.ranking
    assert stored.episode.slots == {"app": "Google Chrome"}
    assert stored.episode.reaction is Reaction.CORRECTED
    assert stored.episode.at == T0


def test_recent_failures_selects_only_failures_newest_first(tmp_path: Path) -> None:
    store = open_store(tmp_path)

    def ep(decision: str, outcome: str, reaction: Reaction = Reaction.NONE) -> int:
        return store.record_episode(Episode("x", T0, (), {}, decision, None, outcome, reaction))

    ok = ep("Execute", "AppOpened")
    not_understood = ep("NotUnderstood", "")
    denied = ep("Confirm", "", Reaction.DENIED)
    missing = ep("Execute", "AppNotFound")
    crashed = ep("error", "ActionFailed")
    ids = [s.id for s in store.recent_failures(10)]
    assert ids == [crashed, missing, denied, not_understood]
    assert ok not in ids


def test_aliases_are_returned_as_stored_values(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    (item,) = store.learn([], [AL], T0)
    assert store.aliases() == [StoredAlias(item.id, "app", "zap", "WhatsApp")]
