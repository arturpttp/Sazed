"""What a skill is. Skills never touch the OS; they call ports."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sazed.core.outcomes import Outcome
from sazed.core.types import Slots


def never(slots: Slots) -> bool:
    return False


def always(slots: Slots) -> bool:
    return True


@dataclass(frozen=True)
class SlotSpec:
    name: str
    required: bool
    question: str
    """pt-BR question asked when the slot is missing, e.g. "Qual programa devo abrir?"."""


@dataclass(frozen=True)
class SkillContext:
    now: datetime


@dataclass(frozen=True)
class IntentSpec:
    id: str
    examples: tuple[str, ...]
    slots: tuple[SlotSpec, ...]
    describe: Callable[[Slots], str]
    """pt-BR infinitive phrase for confirmations and errors, e.g. "abrir Google Chrome"."""
    requires_confirmation: Callable[[Slots], bool] = never
    learnable: bool = True
    """False: no phrase is ever learned for this intent (power actions)."""
    repeatable: bool = False
    """True: "de novo"/"mais" may rerun it (level steps, next track). Opt-in on purpose."""

    @property
    def required(self) -> frozenset[str]:
        return frozenset(s.name for s in self.slots if s.required)

    @property
    def slot_names(self) -> frozenset[str]:
        return frozenset(s.name for s in self.slots)

    def question(self, slot: str) -> str:
        return next(s.question for s in self.slots if s.name == slot)


class Skill(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def intents(self) -> Sequence[IntentSpec]: ...

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome: ...
