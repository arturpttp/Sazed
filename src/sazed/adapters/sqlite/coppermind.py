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
    Reaction,
    StoredAlias,
    StoredEpisode,
    StoredExample,
)
from sazed.core.outcomes import FAILURE_NAMES
from sazed.core.types import IntentScore

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
)

_LEARNED = """
    SELECT 'example' AS kind, id, text, intent_id AS target, NULL AS slot, created_at, batch
      FROM learned_examples
    UNION ALL
    SELECT 'alias', id, alias, value, slot, created_at, batch FROM slot_aliases
"""
_FAILURE_OUTCOMES = sorted(FAILURE_NAMES)


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
            (batch,) = self._conn.execute(
                "SELECT COALESCE(MAX(b), 0) + 1 FROM ("
                " SELECT MAX(batch) AS b FROM learned_examples"
                " UNION ALL SELECT MAX(batch) FROM slot_aliases)"
            ).fetchone()
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
        table = "learned_examples" if kind is LearnedKind.EXAMPLE else "slot_aliases"
        row = self._conn.execute(
            f"SELECT * FROM ({_LEARNED}) WHERE kind = ? AND id = ?", (kind.value, item_id)
        ).fetchone()
        if row is None:
            return None
        with self._conn:
            self._conn.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
        return _item(row)

    def forget_latest(self) -> list[LearnedItem]:
        rows = self._conn.execute(
            f"SELECT * FROM ({_LEARNED}) WHERE batch = (SELECT MAX(batch) FROM ({_LEARNED}))"
        ).fetchall()
        if not rows:
            return []
        batch = rows[0][6]
        with self._conn:
            self._conn.execute("DELETE FROM learned_examples WHERE batch = ?", (batch,))
            self._conn.execute("DELETE FROM slot_aliases WHERE batch = ?", (batch,))
        return [_item(r) for r in rows]

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
