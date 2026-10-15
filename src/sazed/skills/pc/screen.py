"""Full screenshots (all monitors) and the Windows snip overlay."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sazed.core.outcomes import Outcome, ScreenshotSaved, SnipOpened
from sazed.core.skill import IntentSpec, SkillContext
from sazed.core.types import Slots


class Screen(Protocol):
    def capture(self, file_name: str) -> str:
        """Save all monitors as `file_name` (or a free variant of it); return the name used."""
        ...

    def open_snip(self) -> None: ...


def screenshot_name(now: datetime) -> str:
    return f"Captura {now:%Y-%m-%d %H-%M-%S}.png"


PRINT_EXAMPLES = (
    "tira um print",
    "tira um print da tela",
    "captura a tela",
    "printa a tela",
    "faz uma captura de tela",
    "salva um print",
    "tira uma foto da tela",
    "print da tela",
    "captura de tela",
    "printa tudo",
)
SNIP_EXAMPLES = (
    "recorta a tela",
    "recortar a tela",
    "faz um recorte da tela",
    "seleciona uma parte da tela",
    "print de uma parte da tela",
    "captura um pedaço da tela",
    "recorte de tela",
    "abre o recorte",
    "quero recortar a tela",
    "print de uma área",
)


class ScreenSkill:
    id = "screen"

    def __init__(self, screen: Screen) -> None:
        self._screen = screen
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec("print_tela", PRINT_EXAMPLES, (), lambda s: "capturar a tela"),
            IntentSpec("recortar_tela", SNIP_EXAMPLES, (), lambda s: "abrir o recorte de tela"),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id == "print_tela":
            return ScreenshotSaved(self._screen.capture(screenshot_name(ctx.now)))
        if intent_id == "recortar_tela":
            self._screen.open_snip()
            return SnipOpened()
        raise ValueError(f"unknown intent {intent_id}")
