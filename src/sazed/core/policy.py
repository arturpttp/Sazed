"""Turn scores and slots into exactly one decision. Pure."""

from __future__ import annotations

from dataclasses import dataclass

from sazed.core.decisions import AskSlot, Confirm, ConfirmReason, Decision, Execute, NotUnderstood
from sazed.core.types import Ambiguous, ParseResult, Slots


@dataclass(frozen=True)
class Thresholds:
    t_exec: float
    t_confirm: float
    g_min: float


@dataclass(frozen=True)
class IntentRequirements:
    required: frozenset[str]
    requires_confirmation: bool


def decide(parse: ParseResult, req: IntentRequirements, th: Thresholds) -> Decision:
    if not parse.ranking:
        return NotUnderstood()
    top = parse.ranking[0]
    second = parse.ranking[1].score if len(parse.ranking) > 1 else 0.0
    if top.score < th.t_confirm:
        return NotUnderstood()

    given: Slots = {n: v for n, v in parse.slots.items() if not isinstance(v, Ambiguous)}
    for name in sorted(req.required):
        extraction = parse.slots.get(name)
        if extraction is None:
            return AskSlot(top.intent_id, given, name, (), "")
        if isinstance(extraction, Ambiguous):
            return AskSlot(top.intent_id, given, name, extraction.candidates, extraction.raw)

    if top.score < th.t_exec:
        return Confirm(top.intent_id, given, ConfirmReason.LOW_SCORE)
    if top.score - second < th.g_min:
        return Confirm(top.intent_id, given, ConfirmReason.SMALL_GAP)
    if req.requires_confirmation:
        return Confirm(top.intent_id, given, ConfirmReason.DESTRUCTIVE)
    return Execute(top.intent_id, given)
