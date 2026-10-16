from datetime import datetime

import pytest

from fakes.ports import FakeCatalog, FakeWindows
from sazed.core.outcomes import (
    AppNotFound,
    DesktopRestored,
    DesktopShown,
    FocusRefused,
    NoSuchMonitor,
    NoWindow,
    SingleMonitor,
    WindowFocused,
    WindowMaximized,
    WindowMinimized,
    WindowMoved,
    WindowNotFound,
    WindowRestored,
    WindowSnapped,
)
from sazed.core.skill import SkillContext
from sazed.core.types import Slots, SlotValue, Unmatched
from sazed.skills.pc.windows import Monitor, Rect, WindowRef, WindowsSkill

CTX = SkillContext(now=datetime(2026, 10, 16, 12, 0))
MAIN = Rect(0, 0, 1920, 1040)
LEFT = Rect(-1280, 0, 0, 984)
MONS = [Monitor(1, LEFT, False), Monitor(2, MAIN, True)]


def ref(hwnd: int, title: str = "x", **kw: object) -> WindowRef:
    base: dict[str, object] = {"state": "normal", "rect": Rect(480, 260, 1440, 780), "monitor": 2}
    return WindowRef(hwnd, title, **{**base, **kw})  # type: ignore[arg-type]


def app(name: str) -> dict[str, SlotValue | Unmatched]:
    return {"app": SlotValue("app", name, name.lower(), 1.0)}


def skill(
    windows: dict[str | None, list[WindowRef]], **kw: object
) -> tuple[WindowsSkill, FakeWindows]:
    fake = FakeWindows(windows, kw.pop("monitors", MONS), **kw)  # type: ignore[arg-type]
    return WindowsSkill(FakeCatalog(["Spotify", "Google Chrome"]), fake), fake


def test_minimise_without_app_acts_on_the_frontmost_window() -> None:
    s, fake = skill({None: [ref(5, "Documento - Word"), ref(6)]})
    assert s.execute("janela_minimizar", {}, CTX) == WindowMinimized("Documento - Word")
    assert fake.calls == [("minimize", 5)]


def test_a_long_title_is_cut() -> None:
    s, _ = skill({None: [ref(5, "a" * 100)]})
    assert s.execute("janela_minimizar", {}, CTX) == WindowMinimized("a" * 60)


def test_a_named_app_uses_its_frontmost_window_and_its_name() -> None:
    s, fake = skill({None: [ref(1)], "Spotify": [ref(7, "Spotify Premium"), ref(8)]})
    assert s.execute("janela_maximizar", app("Spotify"), CTX) == WindowMaximized("Spotify")
    assert fake.calls == [("maximize", 7)]


def test_restore() -> None:
    s, fake = skill({"Spotify": [ref(7, state="minimized")]})
    assert s.execute("janela_restaurar", app("Spotify"), CTX) == WindowRestored("Spotify")
    assert fake.calls == [("restore", 7)]


def test_focus_and_a_refusal() -> None:
    s, _ = skill({"Spotify": [ref(7)]})
    assert s.execute("janela_focar", app("Spotify"), CTX) == WindowFocused("Spotify")
    s, _ = skill({"Spotify": [ref(7)]}, focus_ok=False)
    assert s.execute("janela_focar", app("Spotify"), CTX) == FocusRefused("Spotify")


def test_focus_on_a_closed_app_offers_to_open_it_and_others_do_not() -> None:
    s, _ = skill({})
    assert s.execute("janela_focar", app("Spotify"), CTX) == WindowNotFound("Spotify", True)
    assert s.execute("janela_minimizar", app("Spotify"), CTX) == WindowNotFound("Spotify")


def test_no_window_at_all() -> None:
    s, _ = skill({})
    assert s.execute("janela_maximizar", {}, CTX) == NoWindow()


def test_unknown_app_is_reported_like_opening_it() -> None:
    s, _ = skill({})
    slots: Slots = {"app": Unmatched("app", "spotfy", "Spotify")}
    assert s.execute("janela_minimizar", slots, CTX) == AppNotFound("spotfy", "Spotify")


def test_snap_uses_the_windows_own_monitor() -> None:
    s, fake = skill({"Spotify": [ref(7, monitor=1)]})
    slots = {**app("Spotify"), "lado": SlotValue("lado", "direita", "direita", 1.0)}
    assert s.execute("janela_encaixar", slots, CTX) == WindowSnapped("Spotify", "direita")
    assert fake.windows(FakeCatalog(["Spotify"]).entries()[0])[0].rect == Rect(-640, 0, 0, 984)


def test_move_goes_to_the_other_monitor_keeping_proportions() -> None:
    s, fake = skill({"Spotify": [ref(7)]})
    assert s.execute("janela_mover_monitor", app("Spotify"), CTX) == WindowMoved("Spotify", 1)
    moved = fake.windows(FakeCatalog(["Spotify"]).entries()[0])[0]
    assert moved.rect == Rect(-960, 246, -320, 738)


def test_moving_a_maximised_window_keeps_it_maximised() -> None:
    s, fake = skill({"Spotify": [ref(7, state="maximized")]})
    s.execute("janela_mover_monitor", app("Spotify"), CTX)
    assert fake.calls == [("restore", 7), ("place", 7), ("maximize", 7)]


@pytest.mark.parametrize(
    ("monitors", "wanted", "expected"),
    [
        ([Monitor(1, MAIN, True)], "outro", SingleMonitor()),
        (MONS, 3, NoSuchMonitor(3, 2)),
    ],
)
def test_move_failures(monitors: list[Monitor], wanted: object, expected: object) -> None:
    s, fake = skill({"Spotify": [ref(7, monitor=1)]}, monitors=monitors)
    slots = {**app("Spotify"), "monitor": SlotValue("monitor", wanted, str(wanted), 1.0)}  # type: ignore[arg-type]
    assert s.execute("janela_mover_monitor", slots, CTX) == expected
    assert fake.calls == []


def test_desktop_show_and_back() -> None:
    s, fake = skill({})
    assert s.execute("area_trabalho_mostrar", {}, CTX) == DesktopShown()
    assert fake.desktop_shown
    assert s.execute("area_trabalho_voltar", {}, CTX) == DesktopRestored()
    assert not fake.desktop_shown


def test_minimise_snap_and_move_are_repeatable_and_the_rest_are_not() -> None:
    s, _ = skill({})
    reps = {spec.id for spec in s.intents if spec.repeatable}
    assert reps == {"janela_minimizar", "janela_encaixar", "janela_mover_monitor"}


def test_focus_needs_an_app_and_snap_needs_a_side() -> None:
    s, _ = skill({})
    required = {spec.id: spec.required for spec in s.intents}
    assert required["janela_focar"] == {"app"}
    assert required["janela_encaixar"] == {"lado"}
    assert required["janela_minimizar"] == frozenset()


def test_restore_without_an_app_picks_the_minimised_window_not_the_front_one() -> None:
    # Word was minimised behind a maximised Chrome: "desminimiza essa janela" means Word.
    s, fake = skill(
        {None: [ref(1, "Chrome", state="maximized"), ref(2, "Word", state="minimized")]}
    )
    assert s.execute("janela_restaurar", {}, CTX) == WindowRestored("Word")
    assert fake.calls == [("restore", 2)]


def test_restoring_an_app_prefers_its_window_that_needs_it() -> None:
    s, fake = skill({"Spotify": [ref(7), ref(8, state="minimized")]})
    s.execute("janela_restaurar", app("Spotify"), CTX)
    assert fake.calls == [("restore", 8)]


def test_restore_falls_back_to_a_maximised_window() -> None:
    s, fake = skill({None: [ref(1), ref(2, state="maximized")]})
    s.execute("janela_restaurar", {}, CTX)
    assert fake.calls == [("restore", 2)]
