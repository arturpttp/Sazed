"""Minimise, maximise, restore, focus, snap and move windows; show the desktop.

The geometry here is pure. Choosing which window a phrase means is the adapter's job
(`adapters/windows/windows.py`), because it needs the running processes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from sazed.core.outcomes import NoSuchMonitor, SingleMonitor
from sazed.skills.pc.apps import AppEntry

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
