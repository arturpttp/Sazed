"""Window control through Win32. The choice of windows is pure (`choose_windows`)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sazed.adapters.windows.launcher import CORE_WINDOW_CLASS

SHELL_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})


@dataclass(frozen=True)
class RawWindow:
    hwnd: int
    pid: int
    child_pids: frozenset[int]
    class_name: str
    title: str
    visible: bool
    cloaked: bool
    """Hidden by DWM: suspended Store apps and windows on other virtual desktops."""
    tool_window: bool
    owned: bool
    """Has an owner window: dialogs and pop-ups, not a window of its own."""


def _is_user_window(w: RawWindow) -> bool:
    return (
        w.visible
        and not w.cloaked
        and not w.tool_window
        and not w.owned
        and bool(w.title)
        and w.class_name not in SHELL_CLASSES
        and w.class_name != CORE_WINDOW_CLASS
    )


def choose_windows(
    raw: Sequence[RawWindow], own_pids: set[int], app_pids: set[int] | None
) -> list[int]:
    """User windows in z-order (frontmost first): the app's, or all when `app_pids` is None.

    Sazed's console is never one of them: its process, or a terminal frame hosting it.
    """
    chosen: list[int] = []
    for w in raw:
        if not _is_user_window(w) or w.pid in own_pids or w.child_pids & own_pids:
            continue
        if app_pids is None or w.pid in app_pids or w.child_pids & app_pids:
            chosen.append(w.hwnd)
    return chosen
