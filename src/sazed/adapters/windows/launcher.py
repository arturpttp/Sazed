"""Start apps through their shortcut; close them gracefully with WM_CLOSE."""

from __future__ import annotations

import os
from collections.abc import Iterable

import psutil

from sazed.skills.pc.apps import AppEntry


def _same_path(a: str | None, b: str) -> bool:
    return a is not None and os.path.normcase(os.path.normpath(a)) == os.path.normcase(
        os.path.normpath(b)
    )


def root_pids(processes: Iterable[tuple[int, int, str | None]], target: str) -> list[int]:
    """PIDs running `target` whose parent is not also running it (one per app instance)."""
    matching = {pid: ppid for pid, ppid, exe in processes if _same_path(exe, target)}
    return sorted(pid for pid, ppid in matching.items() if ppid not in matching)


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
        return len(root_pids(_snapshot(), entry.target))

    def close(self, entry: AppEntry) -> int:
        import win32con
        import win32gui
        import win32process

        pids = {pid for pid, _, exe in _snapshot() if _same_path(exe, entry.target)}
        closed: set[int] = set()

        def on_window(hwnd: int, _: object) -> bool:
            if win32gui.IsWindowVisible(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in pids:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    closed.add(pid)
            return True

        win32gui.EnumWindows(on_window, None)
        return len(closed)
