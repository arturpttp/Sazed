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
    AwaitLearn,
    AwaitSlot,
    DialogueContext,
    LastKind,
    LastTurn,
    Pending,
)
from sazed.core.coppermind import (
    Coppermind,
    Episode,
    LearnedItem,
    LearnedKind,
    NewAlias,
    NewExample,
    Reaction,
)
from sazed.core.decisions import (
    AskSlot,
    Confirm,
    ConfirmReason,
    Decision,
    Execute,
    NotUnderstood,
)
from sazed.core.learning import LearningThresholds, Verdict, judge_example
from sazed.core.outcomes import (
    ActionFailed,
    AliasLearned,
    AlreadyKnown,
    AmbiguousSlot,
    AppNotFound,
    Cancelled,
    ExampleLearned,
    Forgotten,
    NothingToForget,
    NothingToRepeat,
    Outcome,
    WindowNotFound,
    is_failure,
)
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
from sazed.nlu.control import Control, ControlKind, parse_control, pick_candidate
from sazed.nlu.matcher import IntentIndex
from sazed.nlu.normalize import normalize, strip_accents
from sazed.nlu.slots.app import mask_app
from sazed.nlu.slots.change import bare_name
from sazed.nlu.slots.mask import mask_words
from sazed.runtime.extractors import SlotExtractor

log = logging.getLogger(__name__)

GENERIC_ACTION = "atender a esse pedido"
# Slots that name a thing, and the word that stands for any such thing in a learned phrase.
_NAMED_SLOTS = {"pasta": "pasta", "arquivo": "arquivo"}
# Slots read from the original text (case and punctuation kept): a new file name.
RAW_SLOTS = frozenset({"novo_nome"})


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


def alias_key(alias: str) -> str:
    return strip_accents(normalize(alias))


def _describe_learned(items: Sequence[LearnedItem]) -> str:
    parts = [
        f"'{i.text}' como {i.target}" if i.kind is LearnedKind.ALIAS else f"'{i.text}'"
        for i in items
    ]
    return " e ".join(parts)


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
            slot: {alias_key(k): v for k, v in m.items()} for slot, m in aliases.items()
        }
        self._aliases = {slot: dict(m) for slot, m in self._base_aliases.items()}
        self._settings = settings
        self._clock = clock
        self._rng = rng
        self._ctx = DialogueContext()
        self._now = datetime.min
        self._last_episode: int | None = None
        self._command_episode: int | None = None
        for example in store.examples():
            index.add(example.intent_id, example.text, example.embedding)
        for alias in store.aliases():
            self._aliases.setdefault(alias.slot, {})[alias_key(alias.alias)] = alias.value

    # entry point ---------------------------------------------------------------

    def handle(self, text: str) -> Response:
        self._now = self._clock()
        self._ctx = self._ctx.expire(self._now, self._settings.context_ttl_seconds)
        utterance = Utterance(text=text, normalized=normalize(text), received_at=self._now)
        last_before = self._ctx.last
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
        last = self._ctx.last
        # Identity, not time: turns can share a timestamp, but a command creates a new LastTurn.
        if (
            last is not None
            and last is not last_before
            and last.kind is not LastKind.NOT_UNDERSTOOD
        ):
            # This turn ran (or tried to run) a command: a later correction refers to it.
            self._command_episode = self._last_episode
        return Response(" ".join(turn.texts), turn.outcome, turn.decision)

    def _dispatch(self, u: Utterance) -> _Turn:
        control = parse_control(u.normalized)
        pending = self._ctx.pending
        if pending is not None:
            self._ctx = self._ctx.without_pending()
            answered = self._answer(pending, u, control)
            if answered is not None:
                return answered
        if control is not None:
            last = self._ctx.last
            if control.kind is ControlKind.FORGET:
                return self._forget()
            if control.kind is ControlKind.REPEAT:
                # Never falls through to ranking: a bare "mais" is not a command by itself.
                if (
                    last is not None
                    and last.kind is LastKind.EXECUTED
                    and last.intent_id is not None
                    and self._specs[last.intent_id][1].repeatable
                ):
                    return self._proceed(last.intent_id, last.slots, u)
                nothing = NothingToRepeat()
                return _Turn([self._say(nothing)], outcome=nothing)
            if control.kind is ControlKind.CORRECT and last is not None:
                return self._correct(u, last, control.rest)
            if control.kind in (ControlKind.CONFIRM, ControlKind.DENY):
                return self._not_understood(u, remember=False)
        return self._understand(u)

    # understanding ---------------------------------------------------------------

    def _understand(self, u: Utterance) -> _Turn:
        ranking = self._index.rank(u.normalized)
        if not ranking or ranking[0].intent_id not in self._specs:
            return self._not_understood(u, ranking)
        _, spec = self._specs[ranking[0].intent_id]
        slots = self._extract(spec, u.normalized, raw=u.text)
        parse = ParseResult(u, ranking, slots, frozenset(spec.required - set(slots)))
        requirements = IntentRequirements(spec.required, spec.requires_confirmation(_given(slots)))
        decision = decide(parse, requirements, self._settings.thresholds)
        turn = self._enact(decision, spec, u)
        turn.ranking, turn.slots = ranking, slots
        return turn

    def _enact(self, decision: Decision, spec: IntentSpec, u: Utterance) -> _Turn:
        if isinstance(decision, Execute):
            previous = self._ctx.last
            turn = self._execute(spec, decision.slots, u)
            if turn.decision is None:
                turn.decision = decision
            rephrased = previous is not None and previous.kind is LastKind.NOT_UNDERSTOOD
            if (
                rephrased
                and previous is not None
                and isinstance(turn.decision, Execute)
                and not is_failure(turn.outcome)
                and self._ctx.pending is None
            ):
                self._ctx = self._ctx.with_pending(
                    AwaitLearn(previous.utterance, spec.id), self._now
                )
                turn.texts.append(self._say(Prompt.OFFER_LEARN, original=previous.utterance))
            return turn
        if isinstance(decision, Confirm):
            return self._confirm(spec, decision, u)
        if isinstance(decision, AskSlot):
            return self._ask(spec, decision, u)
        return self._not_understood(u)

    # dialogue ------------------------------------------------------------------

    def _answer(self, pending: Pending, u: Utterance, control: Control | None) -> _Turn | None:
        """Try `u` as the answer to `pending`. None means "not an answer": handle it normally."""
        kind = control.kind if control is not None else None
        if isinstance(pending, AwaitSlot):
            if kind is ControlKind.DENY:
                return self._cancelled()
            if kind is not None:
                return None
            value = self._resolve_answer(pending, u)
            if value is None:
                return None
            alias = None
            if pending.candidates and pending.raw and isinstance(value, SlotValue):
                alias = AliasCandidate(pending.slot, pending.raw, str(value.value))
            slots = {**pending.slots, pending.slot: value}
            return self._proceed(pending.intent_id, slots, u, alias=alias)
        if kind is ControlKind.DENY:
            if isinstance(pending, AwaitConfirm):
                self._react(Reaction.DENIED)
            return self._cancelled()
        if kind is not ControlKind.CONFIRM:
            return None
        if isinstance(pending, AwaitConfirm):
            self._react(Reaction.CONFIRMED)
            _, spec = self._specs[pending.intent_id]
            turn = self._execute(spec, pending.slots, u)
            if not is_failure(turn.outcome):
                examples = (
                    [(pending.utterance, spec.id, "confirmed")] if pending.learn_example else []
                )
                aliases = [pending.alias] if pending.alias is not None else []
                texts, _ = self._learn(examples, aliases)
                turn.texts.extend(texts)
            return turn
        texts, outcome = self._learn(
            [(pending.text, pending.intent_id, "offered")], [], announce=True, allow_conflict=True
        )
        return _Turn(texts, outcome=outcome)

    def _resolve_answer(self, pending: AwaitSlot, u: Utterance) -> SlotValue | Unmatched | None:
        ranking = self._index.rank(u.normalized)
        if (
            ranking
            and ranking[0].intent_id != pending.intent_id
            and ranking[0].score >= self._settings.thresholds.t_exec
        ):
            return None  # a different, clearly recognised command: not an answer
        if pending.candidates:
            choice = pick_candidate(u.normalized, pending.candidates)
            if choice is None:
                return None
            return SlotValue(pending.slot, choice, pending.raw or u.normalized, 1.0, exact=True)
        aliases = self._aliases.get(pending.slot, {})
        if pending.slot in RAW_SLOTS:
            extracted = self._extractors[pending.slot](u.text, aliases) or bare_name(u.text)
        else:
            extracted = self._extractors[pending.slot](u.normalized, aliases)
        if isinstance(extracted, SlotValue):
            return extracted
        if isinstance(extracted, Unmatched):
            looks_like_a_command = (
                bool(ranking) and ranking[0].score >= self._settings.thresholds.t_confirm
            )
            return None if looks_like_a_command else extracted
        return None

    def _proceed(
        self, intent_id: str, slots: Slots, u: Utterance, *, alias: AliasCandidate | None = None
    ) -> _Turn:
        """Continue a command whose intent is already settled (answer, repeat, correction)."""
        _, spec = self._specs[intent_id]
        missing = sorted(spec.required - set(slots))
        if missing:
            return self._ask(spec, AskSlot(intent_id, slots, missing[0], (), ""), u)
        if spec.requires_confirmation(slots):
            decision = Confirm(intent_id, slots, ConfirmReason.DESTRUCTIVE)
            return self._confirm(spec, decision, u, alias=alias)
        turn = self._execute(spec, slots, u)
        if turn.decision is None:
            turn.decision = Execute(intent_id, slots)
        if alias is not None and not is_failure(turn.outcome):
            texts, _ = self._learn([], [alias])
            turn.texts.extend(texts)
        return turn

    def _cancelled(self) -> _Turn:
        outcome = Cancelled()
        return _Turn([self._say(outcome)], outcome=outcome)

    def _react(self, reaction: Reaction, episode: int | None = None) -> None:
        target = episode if episode is not None else self._last_episode
        if target is None:
            return
        try:
            self._store.set_reaction(target, reaction)
        except Exception:
            log.exception("could not record the reaction")

    def _extract(
        self, spec: IntentSpec, text: str, raw: str | None = None
    ) -> dict[str, Extraction]:
        found: dict[str, Extraction] = {}
        for slot in spec.slots:
            source = raw if raw is not None and slot.name in RAW_SLOTS else text
            value = self._extractors[slot.name](source, self._aliases.get(slot.name, {}))
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
        if isinstance(outcome, AmbiguousSlot):
            ask = AskSlot(spec.id, slots, outcome.slot, outcome.candidates, "")
            return self._ask(spec, ask, u)
        if isinstance(outcome, WindowNotFound) and outcome.offer_open:
            app = slots.get("app")
            if isinstance(app, SlotValue):
                # "vai pro X" meant focus: opening X is offered, never learned as "open".
                offer = AwaitConfirm("abrir_app", {"app": app}, u.normalized, learn_example=False)
                self._ctx = self._ctx.with_pending(offer, self._now)
        if isinstance(outcome, AppNotFound):
            last = LastTurn(LastKind.APP_NOT_FOUND, u.normalized, spec.id, slots, outcome.query)
            self._ctx = self._ctx.with_last(last, self._now)
            if outcome.suggestion is not None:
                # AppNotFound is specific to the "app" slot, so the slot name is fixed here.
                fixed = {
                    **slots,
                    "app": SlotValue("app", outcome.suggestion, outcome.query, 1.0, exact=True),
                }
                offer = AwaitConfirm(
                    spec.id,
                    fixed,
                    u.normalized,
                    learn_example=False,
                    alias=AliasCandidate("app", outcome.query, outcome.suggestion),
                )
                self._ctx = self._ctx.with_pending(offer, self._now)
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

    def _not_understood(
        self, u: Utterance, ranking: Ranking = (), *, remember: bool = True
    ) -> _Turn:
        # Control phrases ("sim", "não, era …") are never remembered as a failed command,
        # otherwise the next success would offer to learn "sim" as its meaning.
        if remember:
            last = LastTurn(LastKind.NOT_UNDERSTOOD, u.normalized, None, {}, None)
            self._ctx = self._ctx.with_last(last, self._now)
        decision = NotUnderstood()
        return _Turn([self._say(decision)], decision=decision, ranking=ranking)

    # learning ------------------------------------------------------------------

    def _learn(
        self,
        examples: Sequence[tuple[str, str, str]],
        aliases: Sequence[AliasCandidate],
        *,
        ignore: frozenset[str] = frozenset(),
        announce: bool = False,
        allow_conflict: bool = False,
    ) -> tuple[list[str], Outcome | None]:
        """Validate every candidate, then write all of them in one store transaction."""
        # The single gate for examples: confirmations, offers and corrections all pass here.
        examples = [
            (self.learnable_text(text, intent_id), intent_id, origin)
            for text, intent_id, origin in examples
            if self._specs[intent_id][1].learnable
        ]
        texts: list[str] = []
        outcome: Outcome | None = None
        new_examples: list[NewExample] = []
        for text, intent_id, origin in examples:
            scores = self._index.scores(text)
            verdict = judge_example(scores, intent_id, self._settings.learning, ignore)
            if verdict is Verdict.DUPLICATE:
                if announce:
                    outcome = AlreadyKnown()
                    texts.append(self._say(outcome))
                continue
            if verdict is Verdict.CONFLICT and not allow_conflict:
                _, spec = self._specs[intent_id]
                self._ctx = self._ctx.with_pending(AwaitLearn(text, intent_id), self._now)
                texts.append(self._say(Prompt.CONFLICT_ASK, texto=text, acao=spec.describe({})))
                continue
            new_examples.append(NewExample(text, intent_id, self._index.vectorize(text), origin))
        new_aliases = [
            NewAlias(a.slot, a.alias, a.value)
            for a in aliases
            if self._aliases.get(a.slot, {}).get(alias_key(a.alias)) != a.value
        ]
        if new_examples or new_aliases:
            try:
                self._store.learn(new_examples, new_aliases, self._now)
            except Exception:
                # The action (if any) already happened; only remembering it failed.
                log.exception("could not write learned items")
                texts.append(self._say(Prompt.LEARN_FAILED))
                return texts, outcome
            for ex in new_examples:
                self._index.add(ex.intent_id, ex.text, ex.embedding)
            for al in new_aliases:
                self._aliases.setdefault(al.slot, {})[alias_key(al.alias)] = al.value
        if announce and new_examples:
            outcome = ExampleLearned(new_examples[0].text)
            texts.append(self._say(outcome))
        for al in new_aliases:
            outcome = AliasLearned(al.alias, al.value)
            texts.append(self._say(outcome))
        return texts, outcome

    def learnable_text(self, text: str, intent_id: str) -> str:
        """The form of `text` that is learned: the app it names becomes a placeholder."""
        entry = self._specs.get(intent_id)
        if entry is None:
            return text
        names = entry[1].slot_names
        if "app" in names:
            aliases = self._aliases.get("app", {})
            text = mask_app(text, self._extractors["app"](text, aliases), aliases)
        for slot, placeholder in _NAMED_SLOTS.items():
            if slot in names:
                found = self._extractors[slot](text, self._aliases.get(slot, {}))
                if isinstance(found, SlotValue | Unmatched):
                    text = mask_words(text, found.raw.split(), placeholder)
        return text

    def _forget(self) -> _Turn:
        items = self._store.forget_latest()
        if not items:
            nothing = NothingToForget()
            return _Turn([self._say(nothing)], outcome=nothing)
        for item in items:
            if item.kind is LearnedKind.EXAMPLE:
                self._index.remove(item.target, item.text)
            else:
                self._unlearn_alias(item.slot or "", item.text)
        outcome = Forgotten(_describe_learned(items))
        return _Turn([self._say(outcome)], outcome=outcome)

    def _unlearn_alias(self, slot: str, alias: str) -> None:
        key = alias_key(alias)
        configured = self._base_aliases.get(slot, {}).get(key)
        current = self._aliases.setdefault(slot, {})
        if configured is None:
            current.pop(key, None)
        else:
            current[key] = configured

    def _correct(self, u: Utterance, last: LastTurn, rest: str) -> _Turn:
        rest_norm = normalize(rest)
        if last.kind is LastKind.APP_NOT_FOUND and last.intent_id is not None and last.raw_query:
            _, spec = self._specs[last.intent_id]
            found = self._extractors["app"](rest_norm, self._aliases.get("app", {}))
            if found is None:
                return self._not_understood(u, remember=False)
            self._react(Reaction.CORRECTED, self._command_episode)
            if isinstance(found, Ambiguous):
                ask = AskSlot(spec.id, last.slots, "app", found.candidates, last.raw_query)
                return self._ask(spec, ask, u)
            alias = None
            if isinstance(found, SlotValue):
                alias = AliasCandidate("app", last.raw_query, str(found.value))
            return self._proceed(spec.id, {**last.slots, "app": found}, u, alias=alias)

        if last.kind is LastKind.EXECUTED and last.intent_id is not None:
            ranking = self._index.rank(rest_norm)
            top = ranking[0] if ranking else None
            if (
                top is None
                or top.score < self._settings.thresholds.t_confirm
                or top.intent_id == last.intent_id
                or top.intent_id not in self._specs
            ):
                # Same intent: the user is correcting a slot ("não, era o spotify").
                _, spec = self._specs[last.intent_id]
                fixed = {
                    n: v
                    for n, v in self._extract(spec, rest_norm).items()
                    if isinstance(v, SlotValue)
                }
                if not fixed:
                    return self._not_understood(u, remember=False)
                self._react(Reaction.CORRECTED, self._command_episode)
                return self._proceed(spec.id, {**last.slots, **fixed}, u)
            # Another intent: the last command misfired. Learn the original phrase for the
            # right intent; resembling the misfired intent is expected, so it is ignored.
            _, spec = self._specs[top.intent_id]
            carried = {n: v for n, v in last.slots.items() if n in spec.slot_names}
            fresh = _given(self._extract(spec, rest_norm))
            self._react(Reaction.CORRECTED, self._command_episode)
            turn = self._proceed(spec.id, {**carried, **fresh}, u)
            texts, _ = self._learn(
                [(last.utterance, spec.id, "corrected")], [], ignore=frozenset({last.intent_id})
            )
            turn.texts.extend(texts)
            return turn

        return self._understand(Utterance(rest, rest_norm, u.received_at))

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
