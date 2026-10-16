"""Notes, atomic replacement and snapshot/restore in the SQLite coppermind."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from sazed.adapters.sqlite.coppermind import MIGRATIONS, SqliteCoppermind
from sazed.core.coppermind import (
    Episode,
    LearnedKind,
    NewAlias,
    NewExample,
    NoteTarget,
)

T0 = datetime(2026, 10, 15, 12, 0)
T1 = datetime(2026, 10, 15, 13, 0)
VEC = bytes(8)


@pytest.fixture
def store(tmp_path: Path) -> SqliteCoppermind:
    s = SqliteCoppermind(tmp_path / "c.db")
    s.learn([NewExample("abre o zap", "abrir_app", VEC, "confirmed")], [], T0)
    s.learn([], [NewAlias("app", "zap", "WhatsApp")], T0)
    s.record_episode(Episode("abre o zap", T0, (), {}, "Execute", "abrir_app", "AppOpened"))
    return s


def raw_rows(path: Path, sql: str) -> list[tuple[object, ...]]:
    """Re-query through a separate connection: what is really on disk."""
    conn = sqlite3.connect(path)
    try:
        return list(conn.execute(sql).fetchall())
    finally:
        conn.close()


def test_schema_has_a_notes_table(store: SqliteCoppermind, tmp_path: Path) -> None:
    assert store.schema_version == len(MIGRATIONS)
    tables = {r[0] for r in raw_rows(tmp_path / "c.db", "SELECT name FROM sqlite_master")}
    assert "notes" in tables


def test_a_version_1_database_is_migrated_and_keeps_its_rows(tmp_path: Path) -> None:
    from sazed.adapters.sqlite.coppermind import MIGRATIONS

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(f"BEGIN;\n{MIGRATIONS[0]}\nPRAGMA user_version = 1;\nCOMMIT;")
    conn.execute(
        "INSERT INTO slot_aliases (slot, alias, value, batch, created_at)"
        " VALUES ('app', 'zap', 'WhatsApp', 1, '2026-10-15T12:00:00')"
    )
    conn.commit()
    conn.close()
    store = SqliteCoppermind(path)
    assert store.schema_version == len(MIGRATIONS)
    assert [a.alias for a in store.aliases()] == ["zap"]
    store.close()


@pytest.mark.parametrize("target", list(NoteTarget))
def test_notes_on_every_kind_of_target(store: SqliteCoppermind, target: NoteTarget) -> None:
    note = store.add_note(target, 1, "anotação", T0)
    assert note is not None
    assert (note.target, note.target_id, note.text, note.created_at) == (target, 1, "anotação", T0)
    assert store.notes(target, 1) == [note]


def test_a_note_needs_an_existing_target(store: SqliteCoppermind, tmp_path: Path) -> None:
    assert store.add_note(NoteTarget.EXAMPLE, 99, "x", T0) is None
    assert store.add_note(NoteTarget.EPISODE, 99, "x", T0) is None
    assert raw_rows(tmp_path / "c.db", "SELECT COUNT(*) FROM notes") == [(0,)]


def test_edit_and_remove_a_note(store: SqliteCoppermind, tmp_path: Path) -> None:
    note = store.add_note(NoteTarget.ALIAS, 1, "primeira", T0)
    assert note is not None
    edited = store.edit_note(note.id, "segunda", T1)
    assert edited is not None and (edited.text, edited.updated_at) == ("segunda", T1)
    assert raw_rows(tmp_path / "c.db", "SELECT text FROM notes") == [("segunda",)]
    assert store.remove_note(note.id) is not None
    assert store.notes() == []
    assert store.edit_note(note.id, "x", T1) is None
    assert store.remove_note(note.id) is None


def test_forgetting_an_item_deletes_its_notes_only(store: SqliteCoppermind, tmp_path: Path) -> None:
    store.add_note(NoteTarget.EXAMPLE, 1, "do exemplo", T0)
    store.add_note(NoteTarget.ALIAS, 1, "do apelido", T0)
    store.add_note(NoteTarget.EPISODE, 1, "do episódio", T0)
    assert store.forget(LearnedKind.EXAMPLE, 1) is not None
    assert raw_rows(tmp_path / "c.db", "SELECT target_kind, text FROM notes ORDER BY id") == [
        ("alias", "do apelido"),
        ("episode", "do episódio"),
    ]


def test_forget_latest_deletes_the_notes_of_that_batch(
    store: SqliteCoppermind, tmp_path: Path
) -> None:
    store.add_note(NoteTarget.EXAMPLE, 1, "fica", T0)
    store.add_note(NoteTarget.ALIAS, 1, "vai embora", T0)
    assert [i.kind for i in store.forget_latest()] == [LearnedKind.ALIAS]
    assert raw_rows(tmp_path / "c.db", "SELECT text FROM notes") == [("fica",)]


def test_replace_example_keeps_the_id_and_notes(store: SqliteCoppermind, tmp_path: Path) -> None:
    store.add_note(NoteTarget.EXAMPLE, 1, "nota", T0)
    item = store.replace_example(1, NewExample("abre o whatsapp", "abrir_app", VEC, "painel"), T1)
    assert item is not None and (item.id, item.text, item.created_at) == (1, "abre o whatsapp", T1)
    rows = raw_rows(
        tmp_path / "c.db", "SELECT id, text, intent_id, origin, batch FROM learned_examples"
    )
    assert rows == [(1, "abre o whatsapp", "abrir_app", "painel", 3)]  # a new learning batch
    assert [n.text for n in store.notes(NoteTarget.EXAMPLE, 1)] == ["nota"]


def test_replace_of_a_missing_item_changes_nothing(store: SqliteCoppermind) -> None:
    assert store.replace_example(99, NewExample("x", "abrir_app", VEC, "painel"), T1) is None
    assert store.replace_alias(99, "Discord", T1) is None


def test_a_replace_that_fails_midway_leaves_no_trace(
    store: SqliteCoppermind, tmp_path: Path
) -> None:
    broken = NewExample("abre o whatsapp", "abrir_app", None, "painel")  # type: ignore[arg-type]
    with pytest.raises(sqlite3.IntegrityError):
        store.replace_example(1, broken, T1)  # the delete runs, then the insert fails
    assert raw_rows(tmp_path / "c.db", "SELECT id, text FROM learned_examples") == [
        (1, "abre o zap")
    ]
    assert [e.text for e in store.examples()] == ["abre o zap"]


def test_replace_alias_changes_only_the_target(store: SqliteCoppermind, tmp_path: Path) -> None:
    item = store.replace_alias(1, "WhatsApp Beta", T1)
    assert item is not None and (item.text, item.target, item.slot) == (
        "zap",
        "WhatsApp Beta",
        "app",
    )
    assert raw_rows(tmp_path / "c.db", "SELECT id, slot, alias, value FROM slot_aliases") == [
        (1, "app", "zap", "WhatsApp Beta")
    ]


def test_snapshot_then_restore_brings_back_the_row_and_its_notes(
    store: SqliteCoppermind, tmp_path: Path
) -> None:
    store.add_note(NoteTarget.EXAMPLE, 1, "nota", T0)
    snap = store.snapshot(LearnedKind.EXAMPLE, 1)
    assert snap is not None
    store.forget(LearnedKind.EXAMPLE, 1)
    assert store.restore(snap) is True
    assert raw_rows(tmp_path / "c.db", "SELECT id, text, embedding FROM learned_examples") == [
        (1, "abre o zap", VEC)
    ]
    assert [n.text for n in store.notes(NoteTarget.EXAMPLE, 1)] == ["nota"]


def test_restore_refuses_when_the_slot_was_taken(store: SqliteCoppermind) -> None:
    snap = store.snapshot(LearnedKind.ALIAS, 1)
    assert snap is not None
    store.forget(LearnedKind.ALIAS, 1)
    store.learn([], [NewAlias("app", "zap", "Discord")], T1)  # same alias learned again
    assert store.restore(snap) is False
    assert [(a.alias, a.value) for a in store.aliases()] == [("zap", "Discord")]


def test_snapshot_of_a_missing_item(store: SqliteCoppermind) -> None:
    assert store.snapshot(LearnedKind.EXAMPLE, 99) is None
