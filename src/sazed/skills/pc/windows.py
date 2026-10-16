"""Minimise, maximise, restore, focus, snap and move windows; show the desktop.

The geometry here is pure. Choosing which window a phrase means is the adapter's job
(`adapters/windows/windows.py`), because it needs the running processes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from sazed.core.outcomes import (
    AppNotFound,
    DesktopRestored,
    DesktopShown,
    FocusRefused,
    NoSuchMonitor,
    NoWindow,
    Outcome,
    SingleMonitor,
    WindowFocused,
    WindowMaximized,
    WindowMinimized,
    WindowMoved,
    WindowNotFound,
    WindowRestored,
    WindowSnapped,
)
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue, Unmatched
from sazed.skills.pc.apps import AppCatalog, AppEntry

Side = Literal["esquerda", "direita"]
WindowState = Literal["normal", "minimized", "maximized"]


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True)
class Monitor:
    number: int
    """1-based, numbered left-to-right then top-to-bottom."""
    work: Rect
    """The work area: the screen minus the taskbar."""
    primary: bool


@dataclass(frozen=True)
class WindowRef:
    hwnd: int
    title: str
    state: WindowState
    rect: Rect
    """The visible rectangle (without the invisible resize borders)."""
    monitor: int
    """`Monitor.number` of the screen the window is on."""


class WindowControl(Protocol):
    def windows(self, entry: AppEntry | None) -> list[WindowRef]:
        """The app's windows, or every user window when `entry` is None; frontmost first.

        Never Sazed's own console.
        """
        ...

    def monitors(self) -> list[Monitor]: ...
    def minimize(self, hwnd: int) -> None: ...
    def maximize(self, hwnd: int) -> None: ...
    def restore(self, hwnd: int) -> None: ...
    def focus(self, hwnd: int) -> bool:
        """Bring to the front; False when Windows refused (the window then flashes)."""
        ...

    def place(self, hwnd: int, rect: Rect) -> None:
        """Restore if needed and give the window this visible rectangle."""
        ...

    def show_desktop(self) -> None: ...
    def undo_show_desktop(self) -> None: ...


def half(work: Rect, side: Side) -> Rect:
    middle = work.left + work.width // 2
    if side == "esquerda":
        return Rect(work.left, work.top, middle, work.bottom)
    return Rect(middle, work.top, work.right, work.bottom)


def _fit(start: int, end: int, low: int, high: int) -> tuple[int, int]:
    """Shift [start, end) inside [low, high); cut it to that size when it is bigger."""
    size = min(end - start, high - low)
    start = min(max(start, low), high - size)
    return start, start + size


def move_between(rect: Rect, src: Rect, dst: Rect) -> Rect:
    """Where `rect` lands on `dst` keeping its position and size relative to `src`."""

    def x(v: int) -> int:
        return dst.left + round((v - src.left) * dst.width / src.width)

    def y(v: int) -> int:
        return dst.top + round((v - src.top) * dst.height / src.height)

    left, right = _fit(x(rect.left), x(rect.right), dst.left, dst.right)
    top, bottom = _fit(y(rect.top), y(rect.bottom), dst.top, dst.bottom)
    return Rect(left, top, right, bottom)


def target_monitor(
    monitors: Sequence[Monitor], current: int, wanted: str | int
) -> Monitor | NoSuchMonitor | SingleMonitor:
    """The monitor a window should move to: "outro" cycles to the next one, a number picks it."""
    if len(monitors) <= 1:
        return SingleMonitor()
    ordered = sorted(monitors, key=lambda m: m.number)
    if isinstance(wanted, int):
        found = next((m for m in ordered if m.number == wanted), None)
        return found if found is not None else NoSuchMonitor(wanted, len(ordered))
    index = next((i for i, m in enumerate(ordered) if m.number == current), -1)
    return ordered[(index + 1) % len(ordered)]


MINIMIZE_EXAMPLES = (
    "minimiza o chrome",
    "minimiza o spotify",
    "minimizar o word",
    "minimiza essa janela",
    "minimiza a janela",
    "esconde o chrome",
    "esconde a janela",
    "manda a janela pra barra de tarefas",
    "minimiza o notion",
    "abaixa a janela do discord",
    "minimiza aí o chrome",
)
MAXIMIZE_EXAMPLES = (
    "maximiza o chrome",
    "maximiza o spotify",
    "maximizar o word",
    "maximiza essa janela",
    "maximiza a janela",
    "deixa o chrome em tela cheia",
    "aumenta a janela do excel",
    "maximiza o notion",
    "tela cheia no discord",
    "maximiza aí o chrome",
)
RESTORE_EXAMPLES = (
    "restaura o chrome",
    "restaura o word",
    "restaurar o word",
    "restaura essa janela",
    "desmaximiza a janela",
    "volta o chrome ao tamanho normal",
    "tira o spotify da tela cheia",
    "sai da tela cheia no chrome",
    "volta a janela ao tamanho normal",
    "restaura o notion",
    "desminimiza essa janela",
    "restaura aí o chrome",
)
FOCUS_EXAMPLES = (
    "vai pro chrome",
    "vai pro discord",
    "me leva pro spotify",
    "mostra a janela do spotify",
    "troca pra janela do word",
    "traz o chrome pra frente",
    "muda pra janela do excel",
    "alterna pro excel",
    "foca no chrome",
    "me mostra o notion",
    "vai pra janela do chrome",
    "volta pro word",
)
SNAP_EXAMPLES = (
    "joga o chrome pra esquerda",
    "joga o word pra direita",
    "encaixa o discord na esquerda",
    "encaixa essa janela na direita",
    "coloca a janela na metade esquerda",
    "manda o chrome pro lado direito",
    "divide a tela com o word na esquerda",
    "encaixa o notion na direita",
    "joga a janela pra esquerda",
    "põe o discord na metade direita",
)
MOVE_EXAMPLES = (
    "manda o chrome pro outro monitor",
    "joga o excel pra outra tela",
    "move o discord pro monitor 2",
    "manda essa janela pro outro monitor",
    "move a janela pra outra tela",
    "passa o chrome pro segundo monitor",
    "leva a janela pro primeiro monitor",
    "manda o notion pra outra tela",
    "joga a janela pro monitor 1",
    "move o chrome de monitor",
)
DESKTOP_EXAMPLES = (
    "mostra a área de trabalho",
    "minimiza tudo",
    "minimiza todas as janelas",
    "esconde todas as janelas",
    "vai pra área de trabalho",
    "limpa a tela",
    "quero ver a área de trabalho",
    "abaixa todas as janelas",
    "mostra o desktop",
    "some com as janelas",
)
DESKTOP_BACK_EXAMPLES = (
    "volta as janelas",
    "restaura tudo",
    "restaura todas as janelas",
    "traz as janelas de volta",
    "desfaz o minimizar tudo",
    "volta tudo como estava",
    "devolve as janelas",
    "reabre as janelas minimizadas",
    "traz tudo de volta",
    "volta as janelas pra tela",
)

TITLE_LIMIT = 60
_WINDOW = SlotSpec("app", False, "De qual programa é a janela?")


def _side(slots: Slots) -> Side:
    side = slots.get("lado")
    return "direita" if isinstance(side, SlotValue) and side.value == "direita" else "esquerda"


def _label(slots: Slots, verb: str) -> str:
    app = slots.get("app")
    if isinstance(app, SlotValue):
        return f"{verb} {app.value}"
    return f"{verb} a janela"


class WindowsSkill:
    id = "windows"

    def __init__(self, catalog: AppCatalog, control: WindowControl) -> None:
        self._catalog = catalog
        self._control = control
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "janela_minimizar",
                MINIMIZE_EXAMPLES,
                (_WINDOW,),
                lambda s: _label(s, "minimizar"),
                repeatable=True,
            ),
            IntentSpec(
                "janela_maximizar", MAXIMIZE_EXAMPLES, (_WINDOW,), lambda s: _label(s, "maximizar")
            ),
            IntentSpec(
                "janela_restaurar", RESTORE_EXAMPLES, (_WINDOW,), lambda s: _label(s, "restaurar")
            ),
            IntentSpec(
                "janela_focar",
                FOCUS_EXAMPLES,
                (SlotSpec("app", True, "Para qual programa devo ir?"),),
                lambda s: _label(s, "mostrar"),
            ),
            IntentSpec(
                "janela_encaixar",
                SNAP_EXAMPLES,
                (_WINDOW, SlotSpec("lado", True, "Para qual lado?")),
                lambda s: f"{_label(s, 'encaixar')} na {_side(s)}",
                repeatable=True,
            ),
            IntentSpec(
                "janela_mover_monitor",
                MOVE_EXAMPLES,
                (_WINDOW, SlotSpec("monitor", False, "Para qual monitor?")),
                lambda s: f"{_label(s, 'mover')} de monitor",
                repeatable=True,
            ),
            IntentSpec(
                "area_trabalho_mostrar",
                DESKTOP_EXAMPLES,
                (),
                lambda s: "mostrar a área de trabalho",
            ),
            IntentSpec(
                "area_trabalho_voltar",
                DESKTOP_BACK_EXAMPLES,
                (),
                lambda s: "trazer as janelas de volta",
            ),
        )

    def _target(self, intent_id: str, slots: Slots) -> tuple[WindowRef, str] | Outcome:
        """The window a command means and the name to answer with, or why there is none."""
        app = slots.get("app")
        if isinstance(app, Unmatched):
            return AppNotFound(app.raw, app.suggestion)
        entry = None
        if isinstance(app, SlotValue):
            entry = next((e for e in self._catalog.entries() if e.name == app.value), None)
            if entry is None:
                return AppNotFound(app.raw, None)
        windows = self._control.windows(entry)
        if not windows:
            if entry is None:
                return NoWindow()
            return WindowNotFound(entry.name, offer_open=intent_id == "janela_focar")
        window = windows[0]
        if intent_id == "janela_restaurar":
            # A minimised window sits at the bottom of the z-order: restoring means it, then a
            # maximised one, and only then the window in front.
            for state in ("minimized", "maximized"):
                found = next((w for w in windows if w.state == state), None)
                if found is not None:
                    window = found
                    break
        return window, entry.name if entry is not None else window.title[:TITLE_LIMIT]

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id == "area_trabalho_mostrar":
            self._control.show_desktop()
            return DesktopShown()
        if intent_id == "area_trabalho_voltar":
            self._control.undo_show_desktop()
            return DesktopRestored()
        found = self._target(intent_id, slots)
        if not isinstance(found, tuple):
            return found
        window, label = found
        hwnd = window.hwnd
        if intent_id == "janela_minimizar":
            self._control.minimize(hwnd)
            return WindowMinimized(label)
        if intent_id == "janela_maximizar":
            self._control.maximize(hwnd)
            return WindowMaximized(label)
        if intent_id == "janela_restaurar":
            self._control.restore(hwnd)
            return WindowRestored(label)
        if intent_id == "janela_focar":
            return WindowFocused(label) if self._control.focus(hwnd) else FocusRefused(label)
        monitors = self._control.monitors()
        current = next((m for m in monitors if m.number == window.monitor), None)
        if current is None:
            return NoWindow()
        if intent_id == "janela_encaixar":
            side = _side(slots)
            self._control.place(hwnd, half(current.work, side))
            return WindowSnapped(label, side)
        if intent_id == "janela_mover_monitor":
            wanted = slots.get("monitor")
            choice = wanted.value if isinstance(wanted, SlotValue) else "outro"
            if isinstance(choice, bool):
                choice = "outro"
            dst = target_monitor(monitors, current.number, choice)
            if not isinstance(dst, Monitor):
                return dst
            maximized = window.state == "maximized"
            if maximized:
                self._control.restore(hwnd)
            self._control.place(hwnd, move_between(window.rect, current.work, dst.work))
            if maximized:
                self._control.maximize(hwnd)
            return WindowMoved(label, dst.number)
        raise ValueError(f"unknown intent {intent_id}")
