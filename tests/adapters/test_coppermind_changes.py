"""Coppermind migration 3: the file-change log behind "desfaz isso"."""

from datetime import datetime
from pathlib import Path

import pytest

import sazed.adapters.sqlite.coppermind as coppermind
from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.coppermind import NewExample
from sazed.skills.pc.fileops import ChangePlan, ItemState

T0 = datetime(2026, 10, 16, 15, 0)
MOVE = ChangePlan(
    "mover",
    r"C:\U\Downloads\a.txt",
    r"C:\U\Documents\a.txt",
    False,
    ItemState(r"C:\U\Downloads\a.txt", False, 10, 1.0, 0),
)
AFTER = ItemState(r"C:\U\Documents\a.txt", False, 10, 2.5, 0)


def test_a_version_2_database_upgrades_with_its_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "c.db"
    shipped = coppermind.MIGRATIONS
    monkeypatch.setattr(coppermind, "MIGRATIONS", shipped[:2])
    old = SqliteCoppermind(path)
    old.learn([NewExample("abre o programa", "abrir_app", b"\x00", "test")], [], T0)
    assert old.schema_version == 2
    old.close()
    monkeypatch.setattr(coppermind, "MIGRATIONS", shipped)
    new = SqliteCoppermind(path)
    assert new.schema_version == 3
    assert [e.text for e in new.examples()] == ["abre o programa"]
    assert new.latest_open() is None


def test_a_change_round_trips_through_a_fresh_connection(tmp_path: Path) -> None:
    path = tmp_path / "c.db"
    store = SqliteCoppermind(path)
    change_id = store.record(MOVE, AFTER, None, T0)
    store.close()
    again = SqliteCoppermind(path)
    change = again.latest_open()
    assert change is not None
    assert (change.id, change.kind, change.source, change.target) == (
        change_id,
        "mover",
        MOVE.source,
        MOVE.target,
    )
    assert (change.is_dir, change.size, change.mtime, change.recycle_ref) == (False, 10, 2.5, None)


def test_undone_changes_are_skipped_and_a_delete_keeps_its_recycle_ref(tmp_path: Path) -> None:
    store = SqliteCoppermind(tmp_path / "c.db")
    first = store.record(MOVE, AFTER, None, T0)
    delete = ChangePlan("apagar", AFTER.path, AFTER.path, False, AFTER)
    second = store.record(delete, None, '{"path": "x"}', T0)
    latest = store.latest_open()
    assert latest is not None and latest.id == second
    assert (latest.source, latest.recycle_ref) == (None, '{"path": "x"}')
    store.mark_undone(second, T0)
    latest = store.latest_open()
    assert latest is not None and latest.id == first
    rows = store._conn.execute("SELECT undone_at FROM file_changes ORDER BY id").fetchall()
    assert rows == [(None,), (T0.isoformat(),)]


def test_the_dashboard_reader_still_opens_a_version_3_file(tmp_path: Path) -> None:
    from sazed.adapters.sqlite.reader import CoppermindReader

    path = tmp_path / "c.db"
    SqliteCoppermind(path).close()
    reader = CoppermindReader(path)
    assert reader.schema_version() == 3
    assert reader.examples() == []
