"""Open and close installed applications through ports."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sazed.core.outcomes import (
    ActionFailed,
    AppClosed,
    AppNotFound,
    AppNotRunning,
    AppOpened,
    Outcome,
)
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue, Unmatched


@dataclass(frozen=True)
class AppEntry:
    name: str
    target: str
    shortcut: str


class AppCatalog(Protocol):
    def entries(self) -> Sequence[AppEntry]: ...


class AppLauncher(Protocol):
    def launch(self, entry: AppEntry) -> None: ...
    def instances(self, entry: AppEntry) -> int: ...
    def close(self, entry: AppEntry) -> int: ...


OPEN_EXAMPLES = (
    "abre o chrome",
    "abra o spotify",
    "abrir o discord",
    "inicia o steam",
    "inicie o word",
    "iniciar o excel",
    "executa o obs",
    "execute o teams",
    "roda o firefox",
    "liga o spotify",
    "pode abrir o chrome",
    "abre a calculadora",
    "me abre o discord",
    "quero abrir o steam",
    "abre aí o word",
    "carrega o excel",
    "inicializa o obs",
    "coloca o teams pra rodar",
    "abre o programa",
    "abrir aplicativo",
)
CLOSE_EXAMPLES = (
    "fecha o chrome",
    "feche o spotify",
    "fechar o discord",
    "encerra o steam",
    "encerre o word",
    "encerrar o excel",
    "mata o obs",
    "termina o teams",
    "sai do firefox",
    "desliga o spotify",
    "pode fechar o chrome",
    "fecha a calculadora",
    "me fecha o discord",
    "quero fechar o steam",
    "fecha aí o word",
    "finaliza o excel",
    "sai do obs",
    "para o teams",
    "fecha o programa",
    "fechar aplicativo",
)


def _label(slots: Slots) -> str:
    app = slots.get("app")
    if isinstance(app, SlotValue):
        return str(app.value)
    if isinstance(app, Unmatched):
        return app.raw
    return "um programa"


class AppsSkill:
    id = "apps"

    def __init__(self, catalog: AppCatalog, launcher: AppLauncher) -> None:
        self._catalog = catalog
        self._launcher = launcher
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "abrir_app",
                OPEN_EXAMPLES,
                (SlotSpec("app", True, "Qual programa devo abrir?"),),
                describe=lambda s: f"abrir {_label(s)}",
            ),
            IntentSpec(
                "fechar_app",
                CLOSE_EXAMPLES,
                (SlotSpec("app", True, "Qual programa devo fechar?"),),
                describe=lambda s: f"fechar {_label(s)}",
                requires_confirmation=self._close_needs_confirmation,
            ),
        )

    def _find(self, name: str) -> AppEntry | None:
        return next((e for e in self._catalog.entries() if e.name == name), None)

    def _close_needs_confirmation(self, slots: Slots) -> bool:
        app = slots.get("app")
        if not isinstance(app, SlotValue):
            return False
        entry = self._find(str(app.value))
        if entry is None:
            return False
        return not app.exact or self._launcher.instances(entry) > 1

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        app = slots.get("app")
        if isinstance(app, Unmatched):
            return AppNotFound(app.raw, app.suggestion)
        if app is None:
            raise ValueError(f"{intent_id} called without its required slot 'app'")
        entry = self._find(str(app.value))
        if entry is None:
            return AppNotFound(app.raw, None)
        if intent_id == "abrir_app":
            self._launcher.launch(entry)
            return AppOpened(entry.name)
        if intent_id == "fechar_app":
            if self._launcher.instances(entry) == 0:
                return AppNotRunning(entry.name)
            if self._launcher.close(entry) == 0:
                # Nothing accepted the close request (e.g. a tray app with no window).
                return ActionFailed(f"fechar {entry.name}")
            return AppClosed(entry.name)
        raise ValueError(f"unknown intent {intent_id}")
