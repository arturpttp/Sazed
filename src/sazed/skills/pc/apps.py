"""Open and close installed applications through ports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from sazed.core.outcomes import (
    ActionFailed,
    AppClosed,
    AppNotFound,
    AppNotRunning,
    AppOpened,
    CannotCloseSite,
    Outcome,
)
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue, Unmatched

AppKind = Literal["lnk", "store", "site"]
_KIND_RANK: dict[str, int] = {"lnk": 0, "store": 1, "site": 2}


@dataclass(frozen=True)
class AppEntry:
    name: str
    target: str
    """lnk: the executable; store: the package install folder ("" if unknown); site: the URL."""
    shortcut: str
    """What is opened to launch it: a .lnk path, `shell:AppsFolder\\<AUMID>`, or the URL."""
    kind: AppKind = "lnk"


class AppCatalog(Protocol):
    def entries(self) -> Sequence[AppEntry]: ...


def merge_entries(*groups: Sequence[AppEntry]) -> list[AppEntry]:
    """One entry per name (case-insensitive): an installed app beats a Store app beats a site."""
    best: dict[str, AppEntry] = {}
    for entry in (e for group in groups for e in group):
        key = entry.name.strip().casefold()
        current = best.get(key)
        if current is None or _KIND_RANK[entry.kind] < _KIND_RANK[current.kind]:
            best[key] = entry
    return sorted(best.values(), key=lambda e: e.name.casefold())


class StaticCatalog:
    def __init__(self, entries: Sequence[AppEntry]) -> None:
        self._entries = list(entries)

    def entries(self) -> Sequence[AppEntry]:
        return list(self._entries)


class CombinedCatalog:
    def __init__(self, parts: Sequence[AppCatalog]) -> None:
        self._parts = list(parts)

    def entries(self) -> Sequence[AppEntry]:
        return merge_entries(*(part.entries() for part in self._parts))


def site_entries(sites: Mapping[str, str]) -> list[AppEntry]:
    return [AppEntry(name, url, url, "site") for name, url in sites.items()]


# Store apps can show English names ("Calculator") on a pt-BR desktop. Wiring adds each alias
# only when its target exists in the catalog; config aliases still override them.
DEFAULT_APP_ALIASES: dict[str, str] = {
    "calculadora": "Calculator",
    "bloco de notas": "Notepad",
    "fotos": "Photos",
    "camera": "Camera",
    "relogio": "Clock",
    "loja": "Microsoft Store",
    "ferramenta de captura": "Snipping Tool",
}


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
    "abre o youtube",
    "abre o gmail",
    "abre o site do github",
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
    "fecha o youtube",
    "fecha o gmail",
    "fecha o site do github",
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
        if entry is None or entry.kind == "site":
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
            if entry.kind == "site":
                return CannotCloseSite(entry.name)
            if self._launcher.instances(entry) == 0:
                return AppNotRunning(entry.name)
            if self._launcher.close(entry) == 0:
                # Nothing accepted the close request (e.g. a tray app with no window).
                return ActionFailed(f"fechar {entry.name}")
            return AppClosed(entry.name)
        raise ValueError(f"unknown intent {intent_id}")
