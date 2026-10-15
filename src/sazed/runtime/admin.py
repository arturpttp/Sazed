"""Read and edit what Sazed learned, for the `aprendizado` and `revisar` commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sazed.core.coppermind import LearnedItem, LearnedKind, NewExample, Reaction
from sazed.core.outcomes import FAILURE_NAMES
from sazed.nlu.normalize import normalize
from sazed.runtime.wiring import SazedApp

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
    return None if item is None else _row(app, item)


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


def label_episode(app: SazedApp, episode_id: int, intent_id: str) -> bool:
    known = {spec.id for skill in app.skills for spec in skill.intents}
    stored = app.store.episode(episode_id)
    if stored is None or intent_id not in known:
        return False
    text = normalize(stored.episode.utterance)
    app.store.learn(
        [NewExample(text, intent_id, app.index.vectorize(text), "review")], [], app.clock()
    )
    return True
