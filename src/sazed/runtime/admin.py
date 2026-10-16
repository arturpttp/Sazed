"""Read and edit what Sazed learned: the `aprendizado` and `revisar` commands, and the
dashboard. Every write here validates first, then writes once."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.coppermind import LearnedItem, LearnedKind, NewAlias, NewExample, Reaction
from sazed.core.learning import Verdict, judge_example
from sazed.core.outcomes import FAILURE_NAMES
from sazed.core.skill import IntentSpec
from sazed.nlu.normalize import normalize, strip_accents
from sazed.runtime.assistant import alias_key
from sazed.runtime.wiring import SazedApp, settings_from

KIND_LABELS = {LearnedKind.EXAMPLE: "exemplo", LearnedKind.ALIAS: "apelido"}
KIND_PREFIX = {LearnedKind.EXAMPLE: "e", LearnedKind.ALIAS: "a"}
DECISION_LABELS = {
    "Execute": "executado",
    "Confirm": "pediu confirmação",
    "AskSlot": "pediu um detalhe",
    "NotUnderstood": "não entendido",
    "control": "resposta",
    "error": "erro interno",
}
REACTION_LABELS = {
    Reaction.NONE: "",
    Reaction.CONFIRMED: "confirmado",
    Reaction.DENIED: "negado",
    Reaction.CORRECTED: "corrigido",
}


@dataclass(frozen=True)
class LearnedRow:
    ref: str
    kind: str
    text: str
    meaning: str
    created_at: datetime


@dataclass(frozen=True)
class EpisodeRow:
    id: int
    at: datetime
    utterance: str
    what: str


def _describe_intent(app: SazedApp, intent_id: str) -> str:
    for skill in app.skills:
        for spec in skill.intents:
            if spec.id == intent_id:
                return spec.describe({})
    return "pedido desconhecido"


def _row(app: SazedApp, item: LearnedItem) -> LearnedRow:
    meaning = item.target if item.kind is LearnedKind.ALIAS else _describe_intent(app, item.target)
    return LearnedRow(
        f"{KIND_PREFIX[item.kind]}{item.id}",
        KIND_LABELS[item.kind],
        item.text,
        meaning,
        item.created_at,
    )


def learned_rows(app: SazedApp) -> list[LearnedRow]:
    return [_row(app, item) for item in app.store.learned()]


def forget_learned(app: SazedApp, ref: str) -> LearnedRow | None:
    kind = next((k for k, p in KIND_PREFIX.items() if ref[:1] == p), None)
    if kind is None or not ref[1:].isdigit():
        return None
    item = app.store.forget(kind, int(ref[1:]))
    if item is None:
        return None
    if kind is LearnedKind.EXAMPLE:
        app.index.remove(item.target, item.text)  # keep this session's index in step
    return _row(app, item)


def failure_rows(app: SazedApp, limit: int) -> list[EpisodeRow]:
    rows = []
    for stored in app.store.recent_failures(limit):
        ep = stored.episode
        parts = [DECISION_LABELS.get(ep.decision, ep.decision), REACTION_LABELS[ep.reaction]]
        if ep.outcome in FAILURE_NAMES:
            parts.append("falhou")
        rows.append(EpisodeRow(stored.id, ep.at, ep.utterance, ", ".join(p for p in parts if p)))
    return rows


def intent_rows(app: SazedApp) -> list[tuple[str, str]]:
    return [(spec.id, spec.describe({})) for skill in app.skills for spec in skill.intents]


class LabelResult(Enum):
    LEARNED = "learned"
    UNKNOWN = "unknown"
    ALREADY_KNOWN = "already_known"
    CONFLICT = "conflict"
    NOT_LEARNABLE = "not_learnable"
    EMPTY = "empty"
    """Nothing left after normalisation (only punctuation or spaces)."""


def _specs(app: SazedApp) -> dict[str, IntentSpec]:
    return {spec.id: spec for skill in app.skills for spec in skill.intents}


def _judge(app: SazedApp, text: str, intent_id: str, force: bool) -> LabelResult | None:
    """The live-learning safeguards (spec §5.2). None means: go ahead and save."""
    specs = _specs(app)
    if intent_id not in specs:
        return LabelResult.UNKNOWN
    if not specs[intent_id].learnable:
        return LabelResult.NOT_LEARNABLE
    if not text:
        return LabelResult.EMPTY
    verdict = judge_example(app.index.scores(text), intent_id, settings_from(app.config).learning)
    if verdict is Verdict.DUPLICATE:
        return LabelResult.ALREADY_KNOWN
    if verdict is Verdict.CONFLICT and not force:
        return LabelResult.CONFLICT
    return None


def learn_example(
    app: SazedApp, text: str, intent_id: str, *, force: bool = False, origin: str = "painel"
) -> LabelResult:
    """Teach `text` as an example of `intent_id`, exactly as live learning would."""
    text = app.assistant.learnable_text(normalize(text), intent_id)
    refused = _judge(app, text, intent_id, force)
    if refused is not None:
        return refused
    vector = app.index.vectorize(text)
    app.store.learn([NewExample(text, intent_id, vector, origin)], [], app.clock())
    app.index.add(intent_id, text, vector)
    return LabelResult.LEARNED


def label_episode(
    app: SazedApp, episode_id: int, intent_id: str, *, force: bool = False
) -> LabelResult:
    stored = app.store.episode(episode_id)
    if stored is None:
        return LabelResult.UNKNOWN
    return learn_example(app, stored.episode.utterance, intent_id, force=force, origin="review")


def edit_example(
    app: SazedApp, item_id: int, text: str, intent_id: str, *, force: bool = False
) -> LabelResult:
    """Fix a learned example's text or intent: judged as new, saved in one transaction."""
    old = next((e for e in app.store.examples() if e.id == item_id), None)
    if old is None:
        return LabelResult.UNKNOWN
    text = app.assistant.learnable_text(normalize(text), intent_id)
    # Judge without the old version, or changing only the intent always "conflicts" with itself.
    removed = app.index.remove(old.intent_id, old.text)
    saved = False
    try:
        refused = _judge(app, text, intent_id, force)
        if refused is not None:
            return refused
        vector = app.index.vectorize(text)
        app.store.replace_example(
            item_id, NewExample(text, intent_id, vector, "painel"), app.clock()
        )
        saved = True
    finally:
        if removed and not saved:  # refused or failed: the index goes back as it was
            app.index.add(old.intent_id, old.text, old.embedding)
    app.index.add(intent_id, text, vector)
    return LabelResult.LEARNED


class AliasResult(Enum):
    SAVED = "saved"
    EMPTY = "empty"
    APP_UNKNOWN = "app_unknown"
    EXISTS = "exists"
    UNKNOWN = "unknown"


def _catalog_name(names: Sequence[str], target: str) -> str | None:
    wanted = strip_accents(normalize(target))
    return next((n for n in names if strip_accents(normalize(n)) == wanted), None)


def add_alias(
    store: SqliteCoppermind, names: Sequence[str], alias: str, target: str, now: datetime
) -> AliasResult:
    """A new name for a catalog app (slot `app`). Never overwrites an existing alias."""
    alias = normalize(alias)
    if not alias:
        return AliasResult.EMPTY
    value = _catalog_name(names, target)
    if value is None:
        return AliasResult.APP_UNKNOWN
    key = alias_key(alias)
    if any(a.slot == "app" and alias_key(a.alias) == key for a in store.aliases()):
        return AliasResult.EXISTS
    store.learn([], [NewAlias("app", alias, value)], now)
    return AliasResult.SAVED


def edit_alias(
    store: SqliteCoppermind, names: Sequence[str], item_id: int, target: str, now: datetime
) -> AliasResult:
    if not any(a.id == item_id for a in store.aliases()):
        return AliasResult.UNKNOWN
    value = _catalog_name(names, target)
    if value is None:
        return AliasResult.APP_UNKNOWN
    store.replace_alias(item_id, value, now)
    return AliasResult.SAVED
