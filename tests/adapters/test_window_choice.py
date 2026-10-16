import pytest

from sazed.adapters.windows.windows import RawWindow, choose_windows

CONSOLE_PID, CHROME_PID, FRAME_PID, CALC_PID = 10, 20, 30, 40


def w(hwnd: int, pid: int, **kw: object) -> RawWindow:
    base: dict[str, object] = {
        "child_pids": frozenset(),
        "class_name": "Chrome_WidgetWin_1",
        "title": "t",
        "visible": True,
        "cloaked": False,
        "tool_window": False,
        "owned": False,
    }
    return RawWindow(hwnd, pid, **{**base, **kw})  # type: ignore[arg-type]


def test_without_an_app_the_frontmost_window_that_is_not_sazeds_console() -> None:
    raw = [w(1, CONSOLE_PID, class_name="CASCADIA_HOSTING_WINDOW_CLASS"), w(2, CHROME_PID)]
    assert choose_windows(raw, own_pids={CONSOLE_PID}, app_pids=None) == [2]


@pytest.mark.parametrize(
    "bad",
    [
        {"visible": False},
        {"cloaked": True},
        {"tool_window": True},
        {"owned": True},
        {"title": ""},
        {"class_name": "Progman"},
        {"class_name": "Shell_TrayWnd"},
        {"class_name": "Windows.UI.Core.CoreWindow"},
    ],
)
def test_hidden_tool_owned_shell_and_core_windows_are_skipped(bad: dict[str, object]) -> None:
    assert choose_windows([w(1, CHROME_PID, **bad), w(2, CHROME_PID)], set(), None) == [2]


def test_an_apps_windows_include_store_frames_hosting_it_in_z_order() -> None:
    raw = [
        w(1, CHROME_PID),
        w(2, FRAME_PID, child_pids=frozenset({FRAME_PID, CALC_PID})),
        w(3, CALC_PID),
    ]
    assert choose_windows(raw, set(), app_pids={CALC_PID}) == [2, 3]


def test_sazeds_console_is_excluded_even_when_it_matches_the_app() -> None:
    raw = [w(1, CONSOLE_PID), w(2, CONSOLE_PID)]
    assert choose_windows(raw, own_pids={CONSOLE_PID}, app_pids={CONSOLE_PID}) == []


def test_a_frame_hosting_sazeds_console_is_excluded() -> None:
    # Windows Terminal draws the console inside its own window: child pid is the console host.
    raw = [w(1, 99, child_pids=frozenset({CONSOLE_PID})), w(2, CHROME_PID)]
    assert choose_windows(raw, own_pids={CONSOLE_PID}, app_pids=None) == [2]
