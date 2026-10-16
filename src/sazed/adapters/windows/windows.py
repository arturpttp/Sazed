"""Window control through Win32. The choice of windows is pure (`choose_windows`)."""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass

import psutil

from sazed.adapters.windows.launcher import CORE_WINDOW_CLASS, _snapshot, entry_matcher
from sazed.skills.pc.apps import AppEntry
from sazed.skills.pc.windows import Monitor, Rect, WindowRef, WindowState

log = logging.getLogger(__name__)

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3

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


def number_monitors(items: Sequence[tuple[Rect, bool]]) -> list[Monitor]:
    """Monitors numbered 1.. left-to-right, then top-to-bottom (a stable order to name them)."""
    ordered = sorted(items, key=lambda item: (item[0].left, item[0].top))
    return [Monitor(i, work, primary) for i, (work, primary) in enumerate(ordered, start=1)]


def outer_rect(target: Rect, window: Rect, frame: Rect) -> Rect:
    """The rectangle to give SetWindowPos so the *visible* part lands on `target`.

    Windows 10/11 windows carry invisible resize borders: GetWindowRect (`window`) is larger
    than what is drawn (`frame`, DWMWA_EXTENDED_FRAME_BOUNDS).
    """
    return Rect(
        target.left - (frame.left - window.left),
        target.top - (frame.top - window.top),
        target.right + (window.right - frame.right),
        target.bottom + (window.bottom - frame.bottom),
    )


# Invisible resize borders of a normal window at 100% scale (left, top, right, bottom). Used only
# where DWM cannot report them: a minimised window has no frame to measure.
FRAME_INSET = (7, 0, 7, 7)


def normal_to_screen(normal: Rect, workspace_offset: tuple[int, int]) -> Rect:
    """`rcNormalPosition` (outer rect, workspace coordinates) → visible rect on the screen.

    Workspace coordinates start at the primary monitor's work area, so a taskbar on the left or
    at the top shifts them by `workspace_offset`.
    """
    dx, dy = workspace_offset
    left, top, right, bottom = FRAME_INSET
    return Rect(
        normal.left + dx + left,
        normal.top + dy + top,
        normal.right + dx - right,
        normal.bottom + dy - bottom,
    )


def _rect(value: tuple[int, int, int, int]) -> Rect:
    return Rect(*value)


def _dwm_rect(hwnd: int) -> Rect | None:
    import ctypes
    from ctypes import wintypes

    box = wintypes.RECT()
    dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    result = dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(box),
        ctypes.sizeof(box),
    )
    if result != 0:
        return None
    return Rect(box.left, box.top, box.right, box.bottom)


def _cloaked(hwnd: int) -> bool:
    import ctypes
    from ctypes import wintypes

    value = ctypes.c_int(0)
    dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    result = dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value)
    )
    return result == 0 and value.value != 0


# The shell and session processes that start terminals. The ancestor walk stops at the first of
# them: explorer.exe owns every File Explorer window, which must stay a target.
SHELL_PROCESSES = frozenset(
    {"explorer.exe", "sihost.exe", "svchost.exe", "services.exe", "winlogon.exe", "wininit.exe"}
)


def own_chain(chain: Sequence[tuple[int, str]]) -> set[int]:
    """Pids of Sazed and its ancestors (self first), up to but excluding the Windows shell."""
    pids: set[int] = set()
    for pid, name in chain:
        if name.lower() in SHELL_PROCESSES:
            break
        pids.add(pid)
    return pids


def _own_pids() -> set[int]:
    """Sazed's process and its ancestors: the console, the terminal, the shell, uv."""
    me = psutil.Process()
    chain = [(me.pid, me.name())]
    with contextlib.suppress(psutil.Error):
        chain += [(p.pid, p.name()) for p in me.parents()]
    return own_chain(chain)


class WindowsWindowControl:
    def __init__(self) -> None:
        self.own_pids = _own_pids()

    def _raw(self) -> list[RawWindow]:
        import win32con
        import win32gui
        import win32process

        def pid_of(hwnd: int) -> int:
            return int(win32process.GetWindowThreadProcessId(hwnd)[1])

        found: list[RawWindow] = []

        def on_window(hwnd: int, _: object) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            children: set[int] = set()

            def on_child(child: int, __: object) -> bool:
                children.add(pid_of(child))
                return True

            with contextlib.suppress(win32gui.error):
                win32gui.EnumChildWindows(hwnd, on_child, None)
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            found.append(
                RawWindow(
                    hwnd=hwnd,
                    pid=pid_of(hwnd),
                    child_pids=frozenset(children),
                    class_name=win32gui.GetClassName(hwnd),
                    title=win32gui.GetWindowText(hwnd),
                    visible=True,
                    cloaked=_cloaked(hwnd),
                    tool_window=bool(style & win32con.WS_EX_TOOLWINDOW),
                    owned=bool(win32gui.GetWindow(hwnd, win32con.GW_OWNER)),
                )
            )
            return True

        win32gui.EnumWindows(on_window, None)  # z-order: frontmost first
        return found

    def windows(self, entry: AppEntry | None) -> list[WindowRef]:
        import win32api
        import win32con
        import win32gui

        app_pids = None
        if entry is not None:
            matches = entry_matcher(entry)
            app_pids = {pid for pid, _, exe in _snapshot() if matches(exe)}
            if not app_pids:
                return []
        monitors = self.monitors()
        refs: list[WindowRef] = []
        for hwnd in choose_windows(self._raw(), self.own_pids, app_pids):
            placement = win32gui.GetWindowPlacement(hwnd)
            state: WindowState = "normal"
            if win32gui.IsIconic(hwnd) or placement[1] == SW_SHOWMINIMIZED:
                state = "minimized"
            elif placement[1] == SW_SHOWMAXIMIZED:
                state = "maximized"
            if state == "normal":
                rect = _dwm_rect(hwnd) or _rect(win32gui.GetWindowRect(hwnd))
            else:
                # Minimised: parked at (-32000, -32000). Maximised: the whole work area. Moves
                # and restores need the size the window returns to.
                rect = normal_to_screen(_rect(placement[4]), self._workspace_offset())
            handle = win32api.MonitorFromRect(
                (rect.left, rect.top, rect.right, rect.bottom), win32con.MONITOR_DEFAULTTONEAREST
            )
            work = _rect(win32api.GetMonitorInfo(handle)["Work"])
            number = next((m.number for m in monitors if m.work == work), 1)
            refs.append(WindowRef(hwnd, win32gui.GetWindowText(hwnd), state, rect, number))
        return refs

    def _workspace_offset(self) -> tuple[int, int]:
        import win32api
        import win32con

        primary = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
        info = win32api.GetMonitorInfo(primary)
        return info["Work"][0] - info["Monitor"][0], info["Work"][1] - info["Monitor"][1]

    def monitors(self) -> list[Monitor]:
        import win32api

        items: list[tuple[Rect, bool]] = []
        for handle, _, _ in win32api.EnumDisplayMonitors():
            info = win32api.GetMonitorInfo(handle)
            items.append((_rect(info["Work"]), bool(info["Flags"] & 1)))
        return number_monitors(items)

    def _show(self, hwnd: int, command: int) -> None:
        import win32gui

        win32gui.ShowWindow(hwnd, command)

    def minimize(self, hwnd: int) -> None:
        import win32con

        self._show(hwnd, win32con.SW_MINIMIZE)

    def maximize(self, hwnd: int) -> None:
        import win32con

        self._show(hwnd, win32con.SW_MAXIMIZE)

    def restore(self, hwnd: int) -> None:
        import win32con

        self._show(hwnd, win32con.SW_RESTORE)

    def focus(self, hwnd: int) -> bool:
        import pywintypes
        import win32api
        import win32con
        import win32gui

        if win32gui.IsIconic(hwnd):
            self.restore(hwnd)
        for attempt in range(2):
            with contextlib.suppress(pywintypes.error):
                win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.05)
            if win32gui.GetForegroundWindow() == hwnd:
                return True
            if attempt == 0:
                # Windows only lets the foreground process change the foreground window; a
                # key event makes this process count as having had the last input.
                win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        flags = win32con.FLASHW_ALL | win32con.FLASHW_TIMERNOFG
        with contextlib.suppress(pywintypes.error):
            win32gui.FlashWindowEx(hwnd, flags, 3, 0)
        log.info("foreground change refused for window %s", hwnd)
        return False

    def place(self, hwnd: int, rect: Rect) -> None:
        import win32con
        import win32gui

        placement = win32gui.GetWindowPlacement(hwnd)
        if win32gui.IsIconic(hwnd) or placement[1] == SW_SHOWMAXIMIZED:
            self.restore(hwnd)
            time.sleep(0.05)
        window = _rect(win32gui.GetWindowRect(hwnd))
        frame = _dwm_rect(hwnd) or window
        outer = outer_rect(rect, window, frame)
        win32gui.SetWindowPos(
            hwnd,
            0,
            outer.left,
            outer.top,
            outer.width,
            outer.height,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )

    def _shell(self, method: str) -> None:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            getattr(win32com.client.Dispatch("Shell.Application"), method)()
        finally:
            pythoncom.CoUninitialize()

    def show_desktop(self) -> None:
        self._shell("MinimizeAll")

    def undo_show_desktop(self) -> None:
        self._shell("UndoMinimizeALL")
