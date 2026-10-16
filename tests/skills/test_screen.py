from datetime import datetime

from fakes.ports import FakeScreen
from sazed.core.outcomes import ScreenshotSaved, SnipOpened
from sazed.core.skill import SkillContext
from sazed.skills.pc.screen import ScreenSkill, screenshot_name

CTX = SkillContext(now=datetime(2026, 10, 15, 14, 3, 22))


def test_screenshot_name_comes_from_the_turn_time() -> None:
    assert screenshot_name(CTX.now) == "Captura 2026-10-15 14-03-22.png"


def test_screenshot_reports_the_name_actually_saved() -> None:
    screen = FakeScreen(existing={"Captura 2026-10-15 14-03-22.png"})
    outcome = ScreenSkill(screen).execute("print_tela", {}, CTX)
    assert outcome == ScreenshotSaved("Captura 2026-10-15 14-03-22 (2).png")
    assert screen.saved == ["Captura 2026-10-15 14-03-22 (2).png"]


def test_snip_opens_the_overlay() -> None:
    screen = FakeScreen()
    assert ScreenSkill(screen).execute("recortar_tela", {}, CTX) == SnipOpened()
    assert screen.snips == 1
