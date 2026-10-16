"""Real windows: a throwaway Tk window with a unique title; the user's windows are not touched.

Showing the desktop minimises every window, so that test runs only with
SAZED_TEST_DESKTOP=1 (the by-hand session covers it with the user's knowledge).
"""

import contextlib
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator

import psutil
import pytest

from sazed.adapters.windows.windows import WindowsWindowControl
from sazed.skills.pc.apps import AppEntry
from sazed.skills.pc.windows import Rect, WindowRef, half

pytestmark = pytest.mark.windows

TK = (
    "import sys, tkinter as tk\n"
    "r = tk.Tk(); r.title(sys.argv[1]); r.geometry('600x400+200+200')\n"
    "r.after(60000, r.destroy); r.mainloop()\n"
)


@pytest.fixture
def tk_window() -> Iterator[tuple[WindowsWindowControl, AppEntry, str]]:
    title = f"sazed-2b-{uuid.uuid4().hex[:8]}"
    proc = subprocess.Popen([sys.executable, "-c", TK, title])
    try:
        # A venv's python.exe is a launcher: the window belongs to its child interpreter.
        deadline = time.monotonic() + 10
        time.sleep(0.5)
        children = psutil.Process(proc.pid).children(recursive=True)
        exe = (children[-1] if children else psutil.Process(proc.pid)).exe()
        entry = AppEntry("Tk", exe, exe)
        control = WindowsWindowControl()
        while time.monotonic() < deadline and find(control, entry, title) is None:
            time.sleep(0.2)
        assert find(control, entry, title) is not None, "the Tk window never appeared"
        yield control, entry, title
    finally:
        for child in psutil.Process(proc.pid).children(recursive=True):
            with contextlib.suppress(psutil.Error):
                child.kill()
        proc.kill()


def find(control: WindowsWindowControl, entry: AppEntry, title: str) -> WindowRef | None:
    return next((w for w in control.windows(entry) if w.title == title), None)


def wait_for(control: WindowsWindowControl, entry: AppEntry, title: str, state: str) -> WindowRef:
    deadline = time.monotonic() + 3
    ref = find(control, entry, title)
    while ref is not None and ref.state != state and time.monotonic() < deadline:
        time.sleep(0.1)
        ref = find(control, entry, title)
    assert ref is not None
    return ref


def close_to(a: Rect, b: Rect, tolerance: int = 2) -> bool:
    return all(
        abs(x - y) <= tolerance for x, y in zip(vars(a).values(), vars(b).values(), strict=True)
    )


def test_monitors_include_exactly_one_primary() -> None:
    monitors = WindowsWindowControl().monitors()
    assert monitors and sum(m.primary for m in monitors) == 1
    assert [m.number for m in monitors] == list(range(1, len(monitors) + 1))


def test_sazeds_own_console_is_never_listed() -> None:
    control = WindowsWindowControl()
    assert psutil.Process().pid in control.own_pids
    names = {psutil.Process(pid).name().lower() for pid in control.own_pids}
    assert "explorer.exe" not in names  # File Explorer windows stay targets


def test_minimise_restore_maximise(tk_window: tuple[WindowsWindowControl, AppEntry, str]) -> None:
    control, entry, title = tk_window
    ref = find(control, entry, title)
    assert ref is not None and ref.state == "normal"
    control.minimize(ref.hwnd)
    assert wait_for(control, entry, title, "minimized").state == "minimized"
    control.restore(ref.hwnd)
    assert wait_for(control, entry, title, "normal").state == "normal"
    control.maximize(ref.hwnd)
    assert wait_for(control, entry, title, "maximized").state == "maximized"


def test_snap_left_fills_the_left_half(
    tk_window: tuple[WindowsWindowControl, AppEntry, str],
) -> None:
    control, entry, title = tk_window
    ref = find(control, entry, title)
    assert ref is not None
    monitor = next(m for m in control.monitors() if m.number == ref.monitor)
    target = half(monitor.work, "esquerda")
    control.place(ref.hwnd, target)
    time.sleep(0.3)
    placed = find(control, entry, title)
    assert placed is not None and close_to(placed.rect, target), (placed.rect, target)


def test_snap_restores_a_maximised_window_first(
    tk_window: tuple[WindowsWindowControl, AppEntry, str],
) -> None:
    control, entry, title = tk_window
    ref = find(control, entry, title)
    assert ref is not None
    control.maximize(ref.hwnd)
    wait_for(control, entry, title, "maximized")
    monitor = next(m for m in control.monitors() if m.number == ref.monitor)
    control.place(ref.hwnd, half(monitor.work, "direita"))
    placed = wait_for(control, entry, title, "normal")
    assert close_to(placed.rect, half(monitor.work, "direita")), placed.rect


def test_focus_brings_it_to_the_front(
    tk_window: tuple[WindowsWindowControl, AppEntry, str],
) -> None:
    control, entry, title = tk_window
    ref = find(control, entry, title)
    assert ref is not None
    if not control.focus(ref.hwnd):
        pytest.skip("Windows refused the foreground change in this session")
    import win32gui

    assert win32gui.GetForegroundWindow() == ref.hwnd


@pytest.mark.skipif(os.environ.get("SAZED_TEST_DESKTOP") != "1", reason="minimises everything")
def test_show_desktop_and_back(tk_window: tuple[WindowsWindowControl, AppEntry, str]) -> None:
    control, entry, title = tk_window
    control.show_desktop()
    assert wait_for(control, entry, title, "minimized").state == "minimized"
    control.undo_show_desktop()
    assert wait_for(control, entry, title, "normal").state == "normal"


@pytest.mark.parametrize("state", ["minimized", "maximized"])
def test_a_minimised_or_maximised_window_reports_its_normal_rect(
    tk_window: tuple[WindowsWindowControl, AppEntry, str], state: str
) -> None:
    # Final review: a minimised window reported the parking rectangle (-32000, -32000), so
    # moving it to another monitor left a 160x28 sliver.
    control, entry, title = tk_window
    before = find(control, entry, title)
    assert before is not None
    (control.minimize if state == "minimized" else control.maximize)(before.hwnd)
    after = wait_for(control, entry, title, state)
    assert close_to(after.rect, before.rect, tolerance=3), (after.rect, before.rect)
