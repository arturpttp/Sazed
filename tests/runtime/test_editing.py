"""The dashboard's write service: lazy model, undo, notes, aliases."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from sazed.core.coppermind import NoteTarget
from sazed.runtime.config import Config, DataConfig, ModelConfig
from sazed.runtime.editing import Editor, EditorUnavailable, build_editing_app
from support.editing import NAMES, AppFactory

FRESH = "me mostra o mensageiro verde"
T = datetime(2026, 10, 15, 12, 0)


def make_editor(tmp_path: Path, factory: AppFactory | None = None) -> tuple[Editor, AppFactory]:
    factory = factory or AppFactory()
    config = Config(data=DataConfig(dir=tmp_path))
    return Editor(config, make_app=factory, app_names=lambda: NAMES, clock=lambda: T), factory


def on_disk(tmp_path: Path, sql: str) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(tmp_path / "coppermind.db")
    try:
        return list(conn.execute(sql).fetchall())
    finally:
        conn.close()


def test_aliases_notes_and_forget_never_load_the_model(tmp_path: Path) -> None:
    editor, factory = make_editor(tmp_path)
    assert editor.add_alias("zap", "WhatsApp").code == "saved"
    assert editor.add_note(NoteTarget.ALIAS, 1, "meu apelido").code == "note_saved"
    assert editor.edit_alias(1, "Discord").code == "saved"
    forgotten = editor.forget("a1")
    assert (forgotten.ok, forgotten.code) == (True, "forgotten")
    assert factory.calls == 0
    assert editor.state == "idle"
    editor.close()


def test_the_model_is_loaded_once_on_the_first_example(tmp_path: Path) -> None:
    editor, factory = make_editor(tmp_path)
    assert editor.learn(FRESH, "abrir_app").code == "learned"
    assert editor.learn("abre aquele editor de fotos", "abrir_app").code == "learned"
    assert factory.calls == 1
    assert editor.state == "ready"
    assert on_disk(tmp_path, "SELECT COUNT(*) FROM learned_examples") == [(2,)]
    editor.close()


def test_a_missing_model_is_a_pt_br_failure_and_is_retried(tmp_path: Path) -> None:
    factory = AppFactory(EditorUnavailable("Não encontrei o modelo."))
    editor, _ = make_editor(tmp_path, factory)
    with pytest.raises(EditorUnavailable, match="Não encontrei o modelo"):
        editor.learn(FRESH, "abrir_app")
    assert (editor.state, editor.message) == ("failed", "Não encontrei o modelo.")
    factory.error = None
    assert editor.learn(FRESH, "abrir_app").code == "learned"
    assert factory.calls == 2
    editor.close()


def test_forget_then_undo_restores_row_and_notes(tmp_path: Path) -> None:
    editor, factory = make_editor(tmp_path)
    editor.learn(FRESH, "abrir_app")
    editor.add_note(NoteTarget.EXAMPLE, 1, "nota")
    gone = editor.forget("e1")
    assert gone.undo is not None
    assert on_disk(tmp_path, "SELECT COUNT(*) FROM notes") == [(0,)]
    assert factory.app is not None
    assert factory.app.index.scores(FRESH)["abrir_app"] < 0.99
    back = editor.undo(gone.undo)
    assert (back.ok, back.code, back.ref) == (True, "restored", "e1")
    assert on_disk(tmp_path, "SELECT id, text FROM learned_examples") == [(1, FRESH)]
    assert on_disk(tmp_path, "SELECT text FROM notes") == [("nota",)]
    assert factory.app.index.scores(FRESH)["abrir_app"] == pytest.approx(1.0)
    assert editor.undo(gone.undo).code == "undo_expired"
    editor.close()


def test_undo_is_refused_when_the_place_was_taken(tmp_path: Path) -> None:
    editor, _ = make_editor(tmp_path)
    editor.add_alias("zap", "WhatsApp")
    gone = editor.forget("a1")
    editor.add_alias("zap", "Discord")
    assert gone.undo is not None
    assert editor.undo(gone.undo).code == "undo_taken"
    editor.close()


@pytest.mark.parametrize("ref", ["e9", "x1", "e", "a-1"])
def test_forget_unknown_refs(tmp_path: Path, ref: str) -> None:
    editor, _ = make_editor(tmp_path)
    assert editor.forget(ref).code == "not_found"
    editor.close()


def test_label_and_edit_go_through_the_safeguards(tmp_path: Path) -> None:
    editor, factory = make_editor(tmp_path)
    editor.learn(FRESH, "abrir_app")
    assert factory.app is not None
    from sazed.core.coppermind import Episode

    episode = factory.app.store.record_episode(Episode("desliga tudo", T, (), {}, "x", None, ""))
    assert editor.label(episode, "pc_desligar").code == "not_learnable"
    assert editor.edit_example(1, "fecha o chrome", "abrir_app").code == "conflict"
    assert editor.edit_example(1, "fecha o chrome", "abrir_app", force=True).code == "learned"
    assert on_disk(tmp_path, "SELECT text FROM learned_examples") == [("fecha o chrome",)]
    editor.close()


def test_notes_lifecycle(tmp_path: Path) -> None:
    editor, _ = make_editor(tmp_path)
    assert editor.add_note(NoteTarget.EPISODE, 1, "x").code == "not_found"
    editor.add_alias("zap", "WhatsApp")
    note = editor.add_note(NoteTarget.ALIAS, 1, "  primeira  ")
    assert note.ref is not None
    assert on_disk(tmp_path, "SELECT text FROM notes") == [("primeira",)]
    note_id = int(note.ref)
    assert editor.edit_note(note_id, "segunda").code == "note_saved"
    assert editor.edit_note(note_id, "   ").code == "empty"
    assert editor.remove_note(note_id).code == "note_removed"
    assert editor.remove_note(note_id).code == "not_found"
    editor.close()


def test_build_editing_app_without_a_model_says_how_to_fetch_it(tmp_path: Path) -> None:
    config = Config(data=DataConfig(dir=tmp_path), model=ModelConfig(embedder_path=tmp_path))
    with pytest.raises(EditorUnavailable, match="fetch_model.py"):
        build_editing_app(config)


def test_writes_wait_for_a_busy_database(tmp_path: Path) -> None:
    """The design note promises a 5 s busy timeout while a running Sazed holds a write."""
    editor, _ = make_editor(tmp_path)
    editor.add_alias("zap", "WhatsApp")
    (timeout,) = editor._store()._conn.execute("PRAGMA busy_timeout").fetchone()
    assert timeout >= 5000
    editor.close()
