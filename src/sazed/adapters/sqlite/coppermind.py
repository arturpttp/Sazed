"""SQLite implementation of the coppermind port.

Schema versions live in PRAGMA user_version; MIGRATIONS[n] upgrades from n to n+1. Never
edit a shipped migration: append a new one.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from sazed.core.coppermind import (
    Episode,
    LearnedItem,
    LearnedKind,
    NewAlias,
    NewExample,
    Note,
    NoteTarget,
    Reaction,
    Snapshot,
    StoredAlias,
    StoredEpisode,
    StoredExample,
)
from sazed.core.outcomes import FAILURE_NAMES
from sazed.core.types import IntentScore
from sazed.skills.pc.fileops import ChangePlan, ItemState, LoggedChange

MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE learned_examples (
        id INTEGER PRIMARY KEY,
        text TEXT NOT NULL,
        intent_id TEXT NOT NULL,
        embedding BLOB NOT NULL,
        origin TEXT NOT NULL,
        batch INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE slot_aliases (
        id INTEGER PRIMARY KEY,
        slot TEXT NOT NULL,
        alias TEXT NOT NULL,
        value TEXT NOT NULL,
        batch INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (slot, alias)
    );
    CREATE TABLE episodes (
        id INTEGER PRIMARY KEY,
        utterance TEXT NOT NULL,
        at TEXT NOT NULL,
        ranking TEXT NOT NULL,
        slots TEXT NOT NULL,
        decision TEXT NOT NULL,
        intent_id TEXT,
        outcome TEXT NOT NULL,
        reaction TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE notes (
        id INTEGER PRIMARY KEY,
        target_kind TEXT NOT NULL CHECK (target_kind IN ('example', 'alias', 'episode')),
        target_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT
    );
    CREATE INDEX notes_target ON notes (target_kind, target_id);
    """,
    """
    CREATE TABLE file_changes (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        source TEXT,
        target TEXT NOT NULL,
        is_dir INTEGER NOT NULL,
        size INTEGER NOT NULL,
        mtime REAL NOT NULL,
        recycle_ref TEXT,
        at TEXT NOT NULL,
        undone_at TEXT
    );
    """,
)

_LEARNED = """
    SELECT 'example' AS kind, id, text, intent_id AS target, NULL AS slot, created_at, batch
      FROM learned_examples
    UNION ALL
    SELECT 'alias', id, alias, value, slot, created_at, batch FROM slot_aliases
"""
_FAILURE_OUTCOMES = sorted(FAILURE_NAMES)
_TABLES = {LearnedKind.EXAMPLE: "learned_examples", LearnedKind.ALIAS: "slot_aliases"}
_TARGET_TABLES = {
    NoteTarget.EXAMPLE: "learned_examples",
    NoteTarget.ALIAS: "slot_aliases",
    NoteTarget.EPISODE: "episodes",
}
_NEXT_BATCH = (
    "SELECT COALESCE(MAX(b), 0) + 1 FROM ("
    " SELECT MAX(batch) AS b FROM learned_examples"
    " UNION ALL SELECT MAX(batch) FROM slot_aliases)"
)
_NOTE_COLUMNS = "id, target_kind, target_id, text, created_at, updated_at"


def _note(row: tuple[object, ...]) -> Note:
    note_id, kind, target_id, text, created, updated = row
    return Note(
        int(str(note_id)),
        NoteTarget(kind),
        int(str(target_id)),
        str(text),
        datetime.fromisoformat(str(created)),
        None if updated is None else datetime.fromisoformat(str(updated)),
    )


class CoppermindVersionError(Exception):
    """The database was written by a newer Sazed than this one."""


def _item(row: sqlite3.Row | tuple[object, ...]) -> LearnedItem:
    kind, item_id, text, target, slot, created_at = row[:6]
    return LearnedItem(
        LearnedKind(kind),
        int(str(item_id)),
        str(text),
        str(target),
        None if slot is None else str(slot),
        datetime.fromisoformat(str(created_at)),
    )


class SqliteCoppermind:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._migrate()

    def _migrate(self) -> None:
        version = self.schema_version
        if version > len(MIGRATIONS):
            raise CoppermindVersionError(
                f"database schema {version} is newer than supported {len(MIGRATIONS)}"
            )
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            self._conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")

    @property
    def schema_version(self) -> int:
        (version,) = self._conn.execute("PRAGMA user_version").fetchone()
        return int(version)

    def close(self) -> None:
        self._conn.close()

    # learning ----------------------------------------------------------------

    def learn(
        self, examples: Sequence[NewExample], aliases: Sequence[NewAlias], now: datetime
    ) -> list[LearnedItem]:
        if not examples and not aliases:
            return []
        stamp = now.isoformat()
        items: list[LearnedItem] = []
        with self._conn:  # one transaction: commits on success, rolls back on any error
            (batch,) = self._conn.execute(_NEXT_BATCH).fetchone()
            for ex in examples:
                cur = self._conn.execute(
                    "INSERT INTO learned_examples"
                    " (text, intent_id, embedding, origin, batch, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (ex.text, ex.intent_id, ex.embedding, ex.origin, batch, stamp),
                )
                assert cur.lastrowid is not None
                items.append(
                    LearnedItem(
                        LearnedKind.EXAMPLE, cur.lastrowid, ex.text, ex.intent_id, None, now
                    )
                )
            for al in aliases:
                self._conn.execute(
                    "INSERT INTO slot_aliases (slot, alias, value, batch, created_at)"
                    " VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT (slot, alias) DO UPDATE SET"
                    " value = excluded.value, batch = excluded.batch,"
                    " created_at = excluded.created_at",
                    (al.slot, al.alias, al.value, batch, stamp),
                )
                (alias_id,) = self._conn.execute(
                    "SELECT id FROM slot_aliases WHERE slot = ? AND alias = ?",
                    (al.slot, al.alias),
                ).fetchone()
                items.append(
                    LearnedItem(LearnedKind.ALIAS, alias_id, al.alias, al.value, al.slot, now)
                )
        return items

    def examples(self) -> list[StoredExample]:
        rows = self._conn.execute(
            "SELECT id, text, intent_id, embedding FROM learned_examples ORDER BY id"
        ).fetchall()
        return [StoredExample(i, t, intent, bytes(e)) for i, t, intent, e in rows]

    def aliases(self) -> list[StoredAlias]:
        rows = self._conn.execute(
            "SELECT id, slot, alias, value FROM slot_aliases ORDER BY id"
        ).fetchall()
        return [StoredAlias(*row) for row in rows]

    def learned(self) -> list[LearnedItem]:
        rows = self._conn.execute(f"{_LEARNED} ORDER BY batch DESC, id DESC").fetchall()
        return [_item(r) for r in rows]

    def forget(self, kind: LearnedKind, item_id: int) -> LearnedItem | None:
        row = self._conn.execute(
            f"SELECT * FROM ({_LEARNED}) WHERE kind = ? AND id = ?", (kind.value, item_id)
        ).fetchone()
        if row is None:
            return None
        with self._conn:  # the item and its notes go together, or neither does
            self._conn.execute(f"DELETE FROM {_TABLES[kind]} WHERE id = ?", (item_id,))
            self._conn.execute(
                "DELETE FROM notes WHERE target_kind = ? AND target_id = ?",
                (kind.value, item_id),
            )
        return _item(row)

    def forget_latest(self) -> list[LearnedItem]:
        rows = self._conn.execute(
            f"SELECT * FROM ({_LEARNED}) WHERE batch = (SELECT MAX(batch) FROM ({_LEARNED}))"
        ).fetchall()
        if not rows:
            return []
        batch = rows[0][6]
        with self._conn:
            for kind, table in _TABLES.items():
                self._conn.execute(
                    "DELETE FROM notes WHERE target_kind = ?"
                    f" AND target_id IN (SELECT id FROM {table} WHERE batch = ?)",
                    (kind.value, batch),
                )
            self._conn.execute("DELETE FROM learned_examples WHERE batch = ?", (batch,))
            self._conn.execute("DELETE FROM slot_aliases WHERE batch = ?", (batch,))
        return [_item(r) for r in rows]

    def replace_example(
        self, item_id: int, example: NewExample, now: datetime
    ) -> LearnedItem | None:
        """Forget and relearn in ONE transaction, keeping the id (so notes and refs stay)."""
        with self._conn:
            if not self._exists("learned_examples", item_id):
                return None
            (batch,) = self._conn.execute(_NEXT_BATCH).fetchone()
            self._conn.execute("DELETE FROM learned_examples WHERE id = ?", (item_id,))
            self._conn.execute(
                "INSERT INTO learned_examples"
                " (id, text, intent_id, embedding, origin, batch, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    item_id,
                    example.text,
                    example.intent_id,
                    example.embedding,
                    example.origin,
                    batch,
                    now.isoformat(),
                ),
            )
        return LearnedItem(LearnedKind.EXAMPLE, item_id, example.text, example.intent_id, None, now)

    def replace_alias(self, item_id: int, value: str, now: datetime) -> LearnedItem | None:
        """Point an alias at another value in ONE transaction, keeping the id."""
        with self._conn:
            row = self._conn.execute(
                "SELECT slot, alias FROM slot_aliases WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                return None
            slot, alias = row
            (batch,) = self._conn.execute(_NEXT_BATCH).fetchone()
            self._conn.execute("DELETE FROM slot_aliases WHERE id = ?", (item_id,))
            self._conn.execute(
                "INSERT INTO slot_aliases (id, slot, alias, value, batch, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (item_id, slot, alias, value, batch, now.isoformat()),
            )
        return LearnedItem(LearnedKind.ALIAS, item_id, alias, value, slot, now)

    def snapshot(self, kind: LearnedKind, item_id: int) -> Snapshot | None:
        row = self._conn.execute(
            f"SELECT * FROM {_TABLES[kind]} WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            return None
        return Snapshot(kind, tuple(row), tuple(self.notes(NoteTarget(kind.value), item_id)))

    def restore(self, snap: Snapshot) -> bool:
        """Put a forgotten item back with its id and notes. False if its place was taken."""
        table = _TABLES[snap.kind]
        with self._conn:
            if self._exists(table, int(str(snap.row[0]))):
                return False
            if snap.kind is LearnedKind.ALIAS:
                taken = self._conn.execute(
                    "SELECT 1 FROM slot_aliases WHERE slot = ? AND alias = ?",
                    (snap.row[1], snap.row[2]),
                ).fetchone()
                if taken:
                    return False
            marks = ", ".join("?" for _ in snap.row)
            self._conn.execute(f"INSERT INTO {table} VALUES ({marks})", snap.row)
            for note in snap.notes:
                self._conn.execute(
                    f"INSERT INTO notes ({_NOTE_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        note.id,
                        note.target.value,
                        note.target_id,
                        note.text,
                        note.created_at.isoformat(),
                        None if note.updated_at is None else note.updated_at.isoformat(),
                    ),
                )
        return True

    def _exists(self, table: str, row_id: int) -> bool:
        found = self._conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return found is not None

    # notes -------------------------------------------------------------------

    def add_note(self, target: NoteTarget, target_id: int, text: str, now: datetime) -> Note | None:
        with self._conn:
            if not self._exists(_TARGET_TABLES[target], target_id):
                return None
            cur = self._conn.execute(
                "INSERT INTO notes (target_kind, target_id, text, created_at) VALUES (?, ?, ?, ?)",
                (target.value, target_id, text, now.isoformat()),
            )
        assert cur.lastrowid is not None
        return Note(cur.lastrowid, target, target_id, text, now)

    def edit_note(self, note_id: int, text: str, now: datetime) -> Note | None:
        with self._conn:
            self._conn.execute(
                "UPDATE notes SET text = ?, updated_at = ? WHERE id = ?",
                (text, now.isoformat(), note_id),
            )
        return self._one_note(note_id)

    def remove_note(self, note_id: int) -> Note | None:
        note = self._one_note(note_id)
        if note is not None:
            with self._conn:
                self._conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        return note

    def notes(self, target: NoteTarget | None = None, target_id: int | None = None) -> list[Note]:
        where: str = "1 = 1"
        params: tuple[object, ...] = ()
        if target is not None:
            where, params = "target_kind = ? AND target_id = ?", (target.value, target_id)
        rows = self._conn.execute(
            f"SELECT {_NOTE_COLUMNS} FROM notes WHERE {where} ORDER BY id", params
        ).fetchall()
        return [_note(r) for r in rows]

    def _one_note(self, note_id: int) -> Note | None:
        row = self._conn.execute(
            f"SELECT {_NOTE_COLUMNS} FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
        return None if row is None else _note(row)

    # episodes ----------------------------------------------------------------

    def record_episode(self, episode: Episode) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO episodes"
                " (utterance, at, ranking, slots, decision, intent_id, outcome, reaction)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    episode.utterance,
                    episode.at.isoformat(),
                    json.dumps([[s.intent_id, s.score] for s in episode.ranking]),
                    json.dumps(dict(episode.slots), ensure_ascii=False),
                    episode.decision,
                    episode.intent_id,
                    episode.outcome,
                    episode.reaction.value,
                ),
            )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def set_reaction(self, episode_id: int, reaction: Reaction) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE episodes SET reaction = ? WHERE id = ?", (reaction.value, episode_id)
            )

    def episodes(self, limit: int) -> list[StoredEpisode]:
        return self._episodes("1 = 1", (), limit)

    def episode(self, episode_id: int) -> StoredEpisode | None:
        found = self._episodes("id = ?", (episode_id,), 1)
        return found[0] if found else None

    def recent_failures(self, limit: int) -> list[StoredEpisode]:
        marks = ", ".join("?" for _ in _FAILURE_OUTCOMES)
        where = (
            "decision IN ('NotUnderstood', 'error')"
            " OR reaction IN ('denied', 'corrected')"
            f" OR outcome IN ({marks})"
        )
        return self._episodes(where, tuple(_FAILURE_OUTCOMES), limit)

    def _episodes(self, where: str, params: tuple[object, ...], limit: int) -> list[StoredEpisode]:
        rows = self._conn.execute(
            "SELECT id, utterance, at, ranking, slots, decision, intent_id, outcome, reaction"
            f" FROM episodes WHERE {where} ORDER BY id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [
            StoredEpisode(
                row_id,
                Episode(
                    utterance=utterance,
                    at=datetime.fromisoformat(at),
                    ranking=tuple(IntentScore(i, float(s)) for i, s in json.loads(ranking)),
                    slots=json.loads(slots),
                    decision=decision,
                    intent_id=intent_id,
                    outcome=outcome,
                    reaction=Reaction(reaction),
                ),
            )
            for (
                row_id,
                utterance,
                at,
                ranking,
                slots,
                decision,
                intent_id,
                outcome,
                reaction,
            ) in rows
        ]

    # file changes (the log behind "desfaz isso") ---------------------------------------

    def record(
        self, plan: ChangePlan, after: ItemState | None, recycle_ref: str | None, at: datetime
    ) -> int:
        """One applied change. A delete keeps no source: the item's old place is its target."""
        source = None if plan.kind == "apagar" else plan.source
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO file_changes"
                " (kind, source, target, is_dir, size, mtime, recycle_ref, at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    plan.kind,
                    source,
                    plan.target,
                    int(plan.is_dir),
                    after.size if after is not None else 0,
                    after.mtime if after is not None else 0.0,
                    recycle_ref,
                    at.isoformat(),
                ),
            )
        return int(cursor.lastrowid or 0)

    def latest_open(self) -> LoggedChange | None:
        row = self._conn.execute(
            "SELECT id, kind, source, target, is_dir, size, mtime, recycle_ref FROM file_changes"
            " WHERE undone_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        change_id, kind, source, target, is_dir, size, mtime, ref = row
        return LoggedChange(
            int(change_id), kind, source, target, bool(is_dir), int(size), float(mtime), ref
        )

    def mark_undone(self, change_id: int, at: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE file_changes SET undone_at = ? WHERE id = ?", (at.isoformat(), change_id)
            )
