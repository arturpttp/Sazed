"""The assistant: one utterance in, one Response out. The only place the clock is read."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from random import Random

from sazed.core.context import (
    AliasCandidate,
    AwaitConfirm,
    AwaitSlot,
    DialogueContext,
    LastKind,
    LastTurn,
)
from sazed.core.coppermind import Coppermind, Episode
from sazed.core.decisions import (
    AskSlot,
    Confirm,
    ConfirmReason,
    Decision,
    Execute,
    NotUnderstood,
)
from sazed.core.learning import LearningThresholds
from sazed.core.outcomes import ActionFailed, AppNotFound, Outcome, is_failure
from sazed.core.persona import Prompt, render
from sazed.core.policy import IntentRequirements, Thresholds, decide
from sazed.core.response import Response
from sazed.core.skill import IntentSpec, Skill, SkillContext
from sazed.core.types import (
    Ambiguous,
    Extraction,
    ParseResult,
    Ranking,
    Slots,
    SlotValue,
    Unmatched,
    Utterance,
)
from sazed.nlu.matcher import IntentIndex
from sazed.nlu.normalize import normalize, strip_accents
from sazed.runtime.extractors import SlotExtractor

log = logging.getLogger(__name__)

GENERIC_ACTION = "atender a esse pedido"


@dataclass(frozen=True)
class Settings:
    user_name: str
    thresholds: Thresholds
    learning: LearningThresholds
    context_ttl_seconds: float


@dataclass
class _Turn:
    texts: list[str]
    outcome: Outcome | None = None
    decision: Decision | None = None
    intent_id: str | None = None
    ranking: Ranking = ()
    slots: Mapping[str, Extraction] = field(default_factory=dict)


def _given(slots: Mapping[str, Extraction]) -> dict[str, SlotValue | Unmatched]:
    return {n: v for n, v in slots.items() if not isinstance(v, Ambiguous)}


def _alias_key(alias: str) -> str:
    return strip_accents(normalize(alias))


def _slot_summary(slots: Mapping[str, Extraction]) -> dict[str, str]:
    summary: dict[str, str] = {}
    for name, value in slots.items():
        if isinstance(value, SlotValue):
            summary[name] = str(value.value)
        elif isinstance(value, Unmatched):
            summary[name] = f"?{value.raw}"
        else:
            summary[name] = "|".join(value.candidates)
    return summary


class Assistant:
    def __init__(
        self,
        *,
        skills: Sequence[Skill],
        index: IntentIndex,
        extractors: Mapping[str, SlotExtractor],
        store: Coppermind,
        aliases: Mapping[str, Mapping[str, str]],
        settings: Settings,
        clock: Callable[[], datetime],
        rng: Random,
    ) -> None:
        self._specs: dict[str, tuple[Skill, IntentSpec]] = {
            spec.id: (skill, spec) for skill in skills for spec in skill.intents
        }
        self._index = index
        self._extractors = extractors
        self._store = store
        self._base_aliases = {
            slot: {_alias_key(k): v for k, v in m.items()} for slot, m in aliases.items()
        }
        self._aliases = {slot: dict(m) for slot, m in self._base_aliases.items()}
        self._settings = settings
        self._clock = clock
        self._rng = rng
        self._ctx = DialogueContext()
        self._now = datetime.min
        self._last_episode: int | None = None

    # entry point ---------------------------------------------------------------

    def handle(self, text: str) -> Response:
        self._now = self._clock()
        self._ctx = self._ctx.expire(self._now, self._settings.context_ttl_seconds)
        utterance = Utterance(text=text, normalized=normalize(text), received_at=self._now)
        try:
            turn = self._dispatch(utterance)
        except Exception:
            self._ctx = DialogueContext()
            failure = ActionFailed(action=GENERIC_ACTION)
            episode_id = self._record(utterance, _Turn([], outcome=failure), decision="error")
            log.exception("turn failed (episode %s)", episode_id)
            return Response(self._say(failure), failure, None)
        log.debug("ranking for %r: %s", utterance.normalized, turn.ranking)
        self._last_episode = self._record(utterance, turn)
        return Response(" ".join(turn.texts), turn.outcome, turn.decision)

    def _dispatch(self, u: Utterance) -> _Turn:
        return self._understand(u)

    # understanding ---------------------------------------------------------------

    def _understand(self, u: Utterance) -> _Turn:
        ranking = self._index.rank(u.normalized)
        if not ranking or ranking[0].intent_id not in self._specs:
            return self._not_understood(u, ranking)
        _, spec = self._specs[ranking[0].intent_id]
        slots = self._extract(spec, u.normalized)
        parse = ParseResult(u, ranking, slots, frozenset(spec.required - set(slots)))
        requirements = IntentRequirements(spec.required, spec.requires_confirmation(_given(slots)))
        decision = decide(parse, requirements, self._settings.thresholds)
        turn = self._enact(decision, spec, u)
        turn.ranking, turn.slots = ranking, slots
        return turn

    def _enact(self, decision: Decision, spec: IntentSpec, u: Utterance) -> _Turn:
        if isinstance(decision, Execute):
            turn = self._execute(spec, decision.slots, u)
            if turn.decision is None:
                turn.decision = decision
            return turn
        if isinstance(decision, Confirm):
            return self._confirm(spec, decision, u)
        if isinstance(decision, AskSlot):
            return self._ask(spec, decision, u)
        return self._not_understood(u)

    def _extract(self, spec: IntentSpec, text: str) -> dict[str, Extraction]:
        found: dict[str, Extraction] = {}
        for slot in spec.slots:
            value = self._extractors[slot.name](text, self._aliases.get(slot.name, {}))
            if value is not None:
                found[slot.name] = value
        return found

    # acting --------------------------------------------------------------------

    def _execute(self, spec: IntentSpec, slots: Slots, u: Utterance) -> _Turn:
        skill, _ = self._specs[spec.id]
        try:
            outcome = skill.execute(spec.id, slots, SkillContext(now=self._now))
        except Exception:
            log.exception("skill %s failed executing %s", skill.id, spec.id)
            outcome = ActionFailed(action=spec.describe(slots))
        if isinstance(outcome, AppNotFound):
            last = LastTurn(LastKind.APP_NOT_FOUND, u.normalized, spec.id, slots, outcome.query)
            self._ctx = self._ctx.with_last(last, self._now)
        elif not is_failure(outcome):
            last = LastTurn(LastKind.EXECUTED, u.normalized, spec.id, slots, None)
            self._ctx = self._ctx.with_last(last, self._now)
        return _Turn([self._say(outcome)], outcome=outcome, intent_id=spec.id)

    def _confirm(
        self, spec: IntentSpec, decision: Confirm, u: Utterance, alias: AliasCandidate | None = None
    ) -> _Turn:
        pending = AwaitConfirm(
            spec.id,
            decision.slots,
            u.normalized,
            learn_example=decision.reason is not ConfirmReason.DESTRUCTIVE,
            alias=alias,
        )
        self._ctx = self._ctx.with_pending(pending, self._now)
        text = self._say(decision, acao=spec.describe(decision.slots))
        return _Turn([text], decision=decision, intent_id=spec.id)

    def _ask(self, spec: IntentSpec, decision: AskSlot, u: Utterance) -> _Turn:
        pending = AwaitSlot(
            spec.id, decision.slots, decision.slot, decision.candidates, decision.raw, u.normalized
        )
        self._ctx = self._ctx.with_pending(pending, self._now)
        text = self._say(decision, pergunta=spec.question(decision.slot))
        return _Turn([text], decision=decision, intent_id=spec.id)

    def _not_understood(self, u: Utterance, ranking: Ranking = ()) -> _Turn:
        last = LastTurn(LastKind.NOT_UNDERSTOOD, u.normalized, None, {}, None)
        self._ctx = self._ctx.with_last(last, self._now)
        decision = NotUnderstood()
        return _Turn([self._say(decision)], decision=decision, ranking=ranking)

    # plumbing ------------------------------------------------------------------

    def _say(self, item: Outcome | Decision | Prompt, **extra: str) -> str:
        return render(item, nome=self._settings.user_name, rng=self._rng, extra=extra)

    def _record(self, u: Utterance, turn: _Turn, decision: str | None = None) -> int | None:
        episode = Episode(
            utterance=u.text,
            at=u.received_at,
            ranking=turn.ranking[:5],
            slots=_slot_summary(turn.slots),
            decision=decision or (type(turn.decision).__name__ if turn.decision else "control"),
            intent_id=turn.intent_id,
            outcome=type(turn.outcome).__name__ if turn.outcome is not None else "",
        )
        try:
            return self._store.record_episode(episode)
        except Exception:
            log.exception("could not record the episode")
            return None
