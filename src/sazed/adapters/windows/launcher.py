"""Start apps through their shortcut; close them gracefully with WM_CLOSE."""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import psutil

from sazed.skills.pc.apps import AppEntry


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _under(exe: str | None, folder: str) -> bool:
    return exe is not None and bool(folder) and _norm(exe).startswith(_norm(folder) + os.sep)


# Squirrel installers (Discord, Teams classic, …) point the shortcut at a launcher that
# starts the real exe from a versioned subfolder, so the target never runs itself.
_LAUNCHER_NAMES = {"update.exe"}


def _matches(exe: str | None, target: str) -> bool:
    if exe is not None and _norm(exe) == _norm(target):
        return True
    if os.path.basename(target).lower() not in _LAUNCHER_NAMES:
        return False
    return _under(exe, os.path.dirname(target))


def entry_matcher(entry: AppEntry) -> Callable[[str | None], bool]:
    """Which running executables belong to `entry`."""
    if entry.kind == "site":
        return lambda exe: False
    if entry.kind == "store":
        return lambda exe: _under(exe, entry.target)
    return lambda exe: _matches(exe, entry.target)


def root_pids(
    processes: Iterable[tuple[int, int, str | None]], matches: Callable[[str | None], bool]
) -> list[int]:
    """PIDs of matching processes whose parent does not also match (one per app instance)."""
    matching = {pid: ppid for pid, ppid, exe in processes if matches(exe)}
    return sorted(pid for pid, ppid in matching.items() if ppid not in matching)


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    child_pids: frozenset[int]
    class_name: str = ""


# A Store app's own CoreWindow ignores WM_CLOSE; only its ApplicationFrameHost frame closes it.
# Right after launch the CoreWindow is briefly top-level, before the frame adopts it.
CORE_WINDOW_CLASS = "Windows.UI.Core.CoreWindow"
FRAME_WAIT_SECONDS = 2.0


def windows_to_close(windows: Sequence[WindowInfo], pids: set[int]) -> list[int]:
    """Top-level windows owned by the app, or hosting it: Store apps draw inside an
    ApplicationFrameHost.exe frame whose child window belongs to the app's process."""
    return [
        w.hwnd
        for w in windows
        if w.class_name != CORE_WINDOW_CLASS and (w.pid in pids or w.child_pids & pids)
    ]


def _snapshot() -> list[tuple[int, int, str | None]]:
    rows: list[tuple[int, int, str | None]] = []
    for proc in psutil.process_iter(["pid", "ppid", "exe"]):
        info = proc.info
        rows.append((info["pid"], info["ppid"] or 0, info.get("exe")))
    return rows


class WindowsLauncher:
    def launch(self, entry: AppEntry) -> None:
        os.startfile(entry.shortcut)  # type: ignore[attr-defined]  # Windows only

    def instances(self, entry: AppEntry) -> int:
        return len(root_pids(_snapshot(), entry_matcher(entry)))

    def close(self, entry: AppEntry) -> int:
        import win32con
        import win32gui
        import win32process

        matches = entry_matcher(entry)
        pids = {pid for pid, _, exe in _snapshot() if matches(exe)}
        if not pids:
            return 0

        def pid_of(hwnd: int) -> int:
            return int(win32process.GetWindowThreadProcessId(hwnd)[1])

        def visible_windows() -> list[WindowInfo]:
            found: list[WindowInfo] = []

            def on_window(hwnd: int, _: object) -> bool:
                if win32gui.IsWindowVisible(hwnd):
                    children: set[int] = set()

                    def on_child(child: int, __: object) -> bool:
                        children.add(pid_of(child))
                        return True

                    with contextlib.suppress(win32gui.error):  # no child windows
                        win32gui.EnumChildWindows(hwnd, on_child, None)
                    found.append(
                        WindowInfo(
                            hwnd, pid_of(hwnd), frozenset(children), win32gui.GetClassName(hwnd)
                        )
                    )
                return True

            win32gui.EnumWindows(on_window, None)
            return found

        targets = windows_to_close(visible_windows(), pids)
        deadline = time.monotonic() + FRAME_WAIT_SECONDS
        while not targets and entry.kind == "store" and time.monotonic() < deadline:
            time.sleep(0.1)  # a just-launched Store app: wait for its frame to adopt it
            targets = windows_to_close(visible_windows(), pids)
        for hwnd in targets:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return len(targets)
