"""Writes to the coppermind for the dashboard: forget/undo, examples, aliases, notes.

The model is loaded only for what needs embeddings (adding, fixing or labelling examples).
Not thread-safe: the dashboard calls every method from one worker thread, because a SQLite
connection belongs to the thread that opened it.

A running Sazed keeps its own in-memory index; what is written here takes effect on its next start.
"""

from __future__ import annotations

import logging
import secrets
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.coppermind import LearnedKind, NoteTarget, Snapshot
from sazed.runtime import admin
from sazed.runtime.config import Config
from sazed.runtime.skills import PcPorts, build_skills
from sazed.runtime.wiring import SazedApp, build_app
from sazed.skills.pc.apps import AppCatalog, CombinedCatalog

log = logging.getLogger(__name__)


class EditorUnavailable(Exception):
    """The model cannot be loaded. `str(error)` is a pt-BR message meant for the user."""


@dataclass(frozen=True)
class WriteOutcome:
    ok: bool
    code: str
    ref: str | None = None
    undo: str | None = None


class _Inert:
    """Stands in for every port. Unlike evaluation's DryRunPorts it raises: the dashboard
    never executes a skill, so reaching a port is a bug, not something to absorb."""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"the dashboard never calls ports (tried {name})")


def real_catalog() -> AppCatalog:
    from sazed.adapters.windows.catalog import StartMenuCatalog
    from sazed.adapters.windows.store import StoreCatalog

    return CombinedCatalog([StartMenuCatalog(), StoreCatalog()])


def inert_ports(catalog: AppCatalog) -> PcPorts:
    inert: Any = _Inert()
    return PcPorts(
        catalog=catalog,
        launcher=inert,
        audio=inert,
        media=inert,
        power=inert,
        screen=inert,
        brightness=inert,
        opener=inert,
        status=inert,
    )


def catalog_names(config: Config) -> list[str]:
    """Every app name Sazed would know: Start menu, Store and the configured sites."""
    return build_skills(inert_ports(real_catalog()), config).app_names


def build_editing_app(config: Config) -> SazedApp:
    """The full app (model, seeds, learned items) with ports that can never act."""
    if not (config.model.embedder_path / "model.onnx").exists():
        raise EditorUnavailable(
            f"Não encontrei o modelo em {config.model.embedder_path}. "
            "Rode uma vez: uv run python scripts/fetch_model.py"
        )
    from sazed.adapters.onnx.embedder import OnnxEmbedder

    try:
        embedder = OnnxEmbedder(config.model.embedder_path)
        return build_app(config, embedder=embedder, ports=inert_ports(real_catalog()))
    except Exception:
        log.exception("could not build the editing app")
        raise EditorUnavailable(
            "Não consegui carregar o modelo para aprender. Os detalhes estão no log."
        ) from None


class Editor:
    def __init__(
        self,
        config: Config,
        *,
        make_app: Callable[[Config], SazedApp] = build_editing_app,
        app_names: Callable[[], Sequence[str]] | None = None,
        clock: Callable[[], datetime],
        undo_limit: int = 50,
    ) -> None:
        self._config = config
        self._make_app = make_app
        self._app_names = app_names or (lambda: catalog_names(config))
        self._names: list[str] | None = None
        self._clock = clock
        self._app: SazedApp | None = None
        self._light: SqliteCoppermind | None = None
        self._undo: OrderedDict[str, Snapshot] = OrderedDict()
        self._undo_limit = undo_limit
        self.state = "idle"
        """idle | loading | ready | failed — read by other threads, written only here."""
        self.message: str | None = None

    # plumbing ------------------------------------------------------------------

    def _store(self) -> SqliteCoppermind:
        if self._app is not None:
            return self._app.store
        if self._light is None:
            self._light = SqliteCoppermind(self._config.data.dir / "coppermind.db")
        return self._light

    def _full(self) -> SazedApp:
        if self._app is None:
            self.state, self.message = "loading", None
            try:
                app = self._make_app(self._config)
            except EditorUnavailable as err:
                self.state, self.message = "failed", str(err)
                raise
            if self._light is not None:
                self._light.close()
                self._light = None
            self._app = app
            self.state = "ready"
        return self._app

    def _names_list(self) -> list[str]:
        if self._names is None:
            self._names = list(self._app_names())
        return self._names

    def close(self) -> None:
        if self._app is not None:
            self._app.close()
        if self._light is not None:
            self._light.close()

    # learned items ---------------------------------------------------------------

    def forget(self, ref: str) -> WriteOutcome:
        kind = next((k for k, p in admin.KIND_PREFIX.items() if ref[:1] == p), None)
        if kind is None or not ref[1:].isdigit():
            return WriteOutcome(False, "not_found")
        store = self._store()
        snap = store.snapshot(kind, int(ref[1:]))
        item = store.forget(kind, int(ref[1:])) if snap is not None else None
        if snap is None or item is None:
            return WriteOutcome(False, "not_found")
        if kind is LearnedKind.EXAMPLE and self._app is not None:
            self._app.index.remove(item.target, item.text)
        token = secrets.token_urlsafe(12)
        self._undo[token] = snap
        while len(self._undo) > self._undo_limit:
            self._undo.popitem(last=False)
        return WriteOutcome(True, "forgotten", ref=ref, undo=token)

    def undo(self, token: str) -> WriteOutcome:
        snap = self._undo.pop(token, None)
        if snap is None:
            return WriteOutcome(False, "undo_expired")
        if not self._store().restore(snap):
            return WriteOutcome(False, "undo_taken")
        if snap.kind is LearnedKind.EXAMPLE and self._app is not None:
            _, text, intent_id, embedding, *_ = snap.row
            assert isinstance(embedding, bytes)
            self._app.index.add(str(intent_id), str(text), embedding)
        return WriteOutcome(True, "restored", ref=f"{admin.KIND_PREFIX[snap.kind]}{snap.row[0]}")

    def learn(self, text: str, intent_id: str, *, force: bool = False) -> WriteOutcome:
        result = admin.learn_example(self._full(), text, intent_id, force=force)
        return WriteOutcome(result is admin.LabelResult.LEARNED, result.value)

    def label(self, episode_id: int, intent_id: str, *, force: bool = False) -> WriteOutcome:
        result = admin.label_episode(self._full(), episode_id, intent_id, force=force)
        return WriteOutcome(result is admin.LabelResult.LEARNED, result.value)

    def edit_example(
        self, item_id: int, text: str, intent_id: str, *, force: bool = False
    ) -> WriteOutcome:
        result = admin.edit_example(self._full(), item_id, text, intent_id, force=force)
        return WriteOutcome(result is admin.LabelResult.LEARNED, result.value, ref=f"e{item_id}")

    def add_alias(self, alias: str, target: str) -> WriteOutcome:
        result = admin.add_alias(self._store(), self._names_list(), alias, target, self._clock())
        return WriteOutcome(result is admin.AliasResult.SAVED, result.value)

    def edit_alias(self, item_id: int, target: str) -> WriteOutcome:
        names = self._names_list()
        result = admin.edit_alias(self._store(), names, item_id, target, self._clock())
        return WriteOutcome(result is admin.AliasResult.SAVED, result.value, ref=f"a{item_id}")

    def app_names(self) -> list[str]:
        return list(self._names_list())

    # notes ---------------------------------------------------------------------

    def add_note(self, target: NoteTarget, target_id: int, text: str) -> WriteOutcome:
        text = text.strip()
        if not text:
            return WriteOutcome(False, "empty")
        note = self._store().add_note(target, target_id, text, self._clock())
        if note is None:
            return WriteOutcome(False, "not_found")
        return WriteOutcome(True, "note_saved", ref=str(note.id))

    def edit_note(self, note_id: int, text: str) -> WriteOutcome:
        text = text.strip()
        if not text:
            return WriteOutcome(False, "empty")
        note = self._store().edit_note(note_id, text, self._clock())
        if note is None:
            return WriteOutcome(False, "not_found")
        return WriteOutcome(True, "note_saved", ref=str(note.id))

    def remove_note(self, note_id: int) -> WriteOutcome:
        if self._store().remove_note(note_id) is None:
            return WriteOutcome(False, "not_found")
        return WriteOutcome(True, "note_removed", ref=str(note_id))
