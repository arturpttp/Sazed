"""Read-only view of the coppermind, for the dashboard.

Every connection is opened with the SQLite URI `mode=ro`: SQLite itself refuses writes and
never creates a missing file. The writer (`SqliteCoppermind`) stays the only code that
changes the database. Rows come back as plain records; nothing here interprets them.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class CoppermindUnavailable(Exception):
    """The database cannot be read. `str(error)` is a pt-BR message meant for the user."""


@dataclass(frozen=True)
class EpisodeRecord:
    id: int
    utterance: str
    at: str
    ranking: list[tuple[str, float]]
    slots: dict[str, str]
    decision: str
    intent_id: str | None
    outcome: str
    reaction: str


@dataclass(frozen=True)
class EpisodeSummary:
    at: str
    decision: str
    outcome: str
    reaction: str


@dataclass(frozen=True)
class ExampleRecord:
    id: int
    text: str
    intent_id: str
    origin: str
    batch: int
    created_at: str


@dataclass(frozen=True)
class AliasRecord:
    id: int
    slot: str
    alias: str
    value: str
    batch: int
    created_at: str


@dataclass(frozen=True)
class NoteRecord:
    id: int
    target: str
    target_id: int
    text: str
    created_at: str
    updated_at: str | None


def _ranking(raw: str) -> list[tuple[str, float]]:
    try:
        return [(str(intent), float(score)) for intent, score in json.loads(raw)]
    except (ValueError, TypeError):
        return []


def _slots(raw: str) -> dict[str, str]:
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class CoppermindReader:
    def __init__(self, path: Path, *, timeout: float = 1.0) -> None:
        self._path = path
        self._timeout = timeout

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        # Not load-bearing: `mode=ro` already refuses to create a missing file (proven in the
        # dashboard proofs). This check only gives the "nothing recorded yet" message.
        if not self._path.is_file():
            raise CoppermindUnavailable("A mente de cobre ainda não existe: nada foi gravado.")
        uri = f"{self._path.resolve().as_uri()}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=self._timeout)
        except sqlite3.Error as err:
            raise CoppermindUnavailable("Não consegui abrir a mente de cobre.") from err
        try:
            yield conn
        finally:
            conn.close()

    def _rows(self, sql: str, params: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
        with self.connect() as conn:
            try:
                return list(conn.execute(sql, params).fetchall())
            except sqlite3.Error as err:
                raise CoppermindUnavailable(
                    "Não consegui ler a mente de cobre agora (pode estar ocupada)."
                ) from err

    def schema_version(self) -> int:
        ((version,),) = self._rows("PRAGMA user_version")
        return int(str(version))

    # episodes ------------------------------------------------------------------

    @staticmethod
    def _where(
        search: str | None, decision: str | None, intent: str | None
    ) -> tuple[str, tuple[object, ...]]:
        clauses: list[str] = []
        params: list[object] = []
        if search:
            clauses.append("utterance LIKE ? ESCAPE '\\'")
            params.append(_like(search))
        if decision:
            clauses.append("decision = ?")
            params.append(decision)
        if intent:
            clauses.append("intent_id = ?")
            params.append(intent)
        return (" AND ".join(clauses) or "1 = 1"), tuple(params)

    def episodes(
        self,
        limit: int,
        offset: int = 0,
        *,
        search: str | None = None,
        decision: str | None = None,
        intent: str | None = None,
    ) -> list[EpisodeRecord]:
        where, params = self._where(search, decision, intent)
        rows = self._rows(
            "SELECT id, utterance, at, ranking, slots, decision, intent_id, outcome, reaction"
            f" FROM episodes WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [
            EpisodeRecord(
                id=int(str(r[0])),
                utterance=str(r[1]),
                at=str(r[2]),
                ranking=_ranking(str(r[3])),
                slots=_slots(str(r[4])),
                decision=str(r[5]),
                intent_id=None if r[6] is None else str(r[6]),
                outcome=str(r[7]),
                reaction=str(r[8]),
            )
            for r in rows
        ]

    def count_episodes(
        self,
        *,
        search: str | None = None,
        decision: str | None = None,
        intent: str | None = None,
    ) -> int:
        where, params = self._where(search, decision, intent)
        ((count,),) = self._rows(f"SELECT COUNT(*) FROM episodes WHERE {where}", params)
        return int(str(count))

    def episode_summaries(self, since: str | None = None) -> list[EpisodeSummary]:
        rows = self._rows(
            "SELECT at, decision, outcome, reaction FROM episodes WHERE at >= ? ORDER BY id",
            (since or "",),
        )
        return [EpisodeSummary(str(a), str(d), str(o), str(r)) for a, d, o, r in rows]

    # learned -------------------------------------------------------------------

    def examples(
        self, search: str | None = None, limit: int = 500, offset: int = 0
    ) -> list[ExampleRecord]:
        rows = self._rows(
            "SELECT id, text, intent_id, origin, batch, created_at FROM learned_examples"
            " WHERE text LIKE ? ESCAPE '\\' OR intent_id LIKE ? ESCAPE '\\'"
            " ORDER BY id DESC LIMIT ? OFFSET ?",
            (_like(search or ""), _like(search or ""), limit, offset),
        )
        return [
            ExampleRecord(int(str(i)), str(t), str(n), str(o), int(str(b)), str(c))
            for i, t, n, o, b, c in rows
        ]

    def aliases(self, search: str | None = None) -> list[AliasRecord]:
        rows = self._rows(
            "SELECT id, slot, alias, value, batch, created_at FROM slot_aliases"
            " WHERE alias LIKE ? ESCAPE '\\' OR value LIKE ? ESCAPE '\\' ORDER BY id DESC",
            (_like(search or ""), _like(search or "")),
        )
        return [
            AliasRecord(int(str(i)), str(s), str(a), str(v), int(str(b)), str(c))
            for i, s, a, v, b, c in rows
        ]

    def learned_dates(self) -> list[tuple[str, str]]:
        rows = self._rows(
            "SELECT 'example', created_at FROM learned_examples"
            " UNION ALL SELECT 'alias', created_at FROM slot_aliases"
        )
        return [(str(kind), str(at)) for kind, at in rows]

    def notes(self) -> list[NoteRecord]:
        """Every note. A database Sazed has not migrated yet simply has none."""
        tables = self._rows("SELECT name FROM sqlite_master WHERE type = 'table'")
        if ("notes",) not in tables:
            return []
        rows = self._rows(
            "SELECT id, target_kind, target_id, text, created_at, updated_at FROM notes ORDER BY id"
        )
        return [
            NoteRecord(
                int(str(i)), str(k), int(str(t)), str(x), str(c), None if u is None else str(u)
            )
            for i, k, t, x, c, u in rows
        ]
