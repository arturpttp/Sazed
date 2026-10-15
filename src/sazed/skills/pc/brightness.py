"""Screen brightness, where the monitor allows it. Mirrors volume (steps and levels)."""

from __future__ import annotations

from typing import Protocol

from sazed.core.outcomes import BrightnessChanged, BrightnessSet, BrightnessUnsupported, Outcome
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots
from sazed.skills.pc.levels import clamp, int_slot, invalid_level, level_label, stepped


class Brightness(Protocol):
    def get(self) -> int | None: ...
    def set(self, percent: int) -> bool: ...


SET_EXAMPLES = (
    "brilho em 50",
    "coloca o brilho em 70",
    "deixa o brilho em 30",
    "ajusta o brilho pra 40",
    "brilho no máximo",
    "brilho no mínimo",
    "põe o brilho em 60",
    "define o brilho para 80",
    "brilho na metade",
    "muda o brilho para 20",
)
UP_EXAMPLES = (
    "aumenta o brilho",
    "sobe o brilho",
    "mais brilho",
    "aumenta o brilho da tela",
    "clareia a tela",
    "aumenta o brilho em 20",
    "sobe o brilho em 10",
    "tela mais clara",
    "deixa a tela mais clara",
    "aumenta mais o brilho",
)
DOWN_EXAMPLES = (
    "diminui o brilho",
    "abaixa o brilho",
    "menos brilho",
    "diminui o brilho da tela",
    "escurece a tela",
    "diminui o brilho em 20",
    "abaixa o brilho em 10",
    "tela mais escura",
    "deixa a tela mais escura",
    "baixa o brilho",
)
_LEVEL = SlotSpec("alvo", False, "Em quanto devo deixar o brilho?")


def _set_label(slots: Slots) -> str:
    n = int_slot(slots, "percent")
    return f"deixar o brilho em {n}%" if n is not None else "ajustar o brilho"


class BrightnessSkill:
    id = "brightness"

    def __init__(self, brightness: Brightness) -> None:
        self._brightness = brightness
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "brilho_definir",
                SET_EXAMPLES,
                (SlotSpec("percent", True, "Em quanto devo deixar o brilho?"),),
                describe=_set_label,
            ),
            IntentSpec(
                "brilho_aumentar",
                UP_EXAMPLES,
                (SlotSpec("percent", False, "Quanto devo aumentar?"), _LEVEL),
                describe=level_label("aumentar o brilho", "o brilho"),
                repeatable=True,
            ),
            IntentSpec(
                "brilho_diminuir",
                DOWN_EXAMPLES,
                (SlotSpec("percent", False, "Quanto devo diminuir?"), _LEVEL),
                describe=level_label("diminuir o brilho", "o brilho"),
                repeatable=True,
            ),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id not in ("brilho_definir", "brilho_aumentar", "brilho_diminuir"):
            raise ValueError(f"unknown intent {intent_id}")
        invalid = invalid_level(slots)
        if invalid is not None:
            return invalid
        current = self._brightness.get()
        if current is None:
            return BrightnessUnsupported()
        if intent_id == "brilho_definir":
            percent = int_slot(slots, "percent")
            if percent is None:
                raise ValueError("brilho_definir called without its required slot 'percent'")
            level, absolute = clamp(percent), True
        else:
            sign = 1 if intent_id == "brilho_aumentar" else -1
            level, absolute = stepped(current, sign, slots)
        if not self._brightness.set(level):
            return BrightnessUnsupported()
        return BrightnessSet(level) if absolute else BrightnessChanged(level)
