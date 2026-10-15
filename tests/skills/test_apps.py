from datetime import datetime

from fakes.ports import FakeCatalog, FakeLauncher
from sazed.core.outcomes import AppClosed, AppNotFound, AppNotRunning, AppOpened
from sazed.core.skill import SkillContext
from sazed.core.types import SlotValue, Unmatched
from sazed.skills.pc.apps import AppsSkill

CTX = SkillContext(now=datetime(2026, 10, 14, 12, 0))
CHROME = SlotValue("app", "Google Chrome", "chrome", 1.0, exact=True)
CROME = SlotValue("app", "Google Chrome", "crome", 0.91, exact=False)


def make(running: dict[str, int] | None = None) -> tuple[AppsSkill, FakeLauncher]:
    launcher = FakeLauncher(running=running)
    return AppsSkill(FakeCatalog(["Google Chrome", "Spotify"]), launcher), launcher


def spec(skill: AppsSkill, intent_id: str):  # type: ignore[no-untyped-def]
    return next(i for i in skill.intents if i.id == intent_id)


def test_open_launches_the_catalog_entry() -> None:
    skill, launcher = make()
    assert skill.execute("abrir_app", {"app": CHROME}, CTX) == AppOpened("Google Chrome")
    assert launcher.launched == ["Google Chrome"]


def test_open_unmatched_reports_not_found_and_launches_nothing() -> None:
    skill, launcher = make()
    outcome = skill.execute("abrir_app", {"app": Unmatched("app", "disc", "Discord")}, CTX)
    assert outcome == AppNotFound("disc", "Discord")
    assert launcher.launched == []


def test_open_value_missing_from_catalog_reports_not_found() -> None:
    skill, launcher = make()
    gone = SlotValue("app", "Steam", "steam", 1.0)
    assert skill.execute("abrir_app", {"app": gone}, CTX) == AppNotFound("steam", None)
    assert launcher.launched == []


def test_close_running_app_closes_it() -> None:
    skill, launcher = make(running={"Google Chrome": 1})
    assert skill.execute("fechar_app", {"app": CHROME}, CTX) == AppClosed("Google Chrome")
    assert launcher.closed == ["Google Chrome"]
    assert launcher.running == {}


def test_close_app_not_running_reports_it_and_closes_nothing() -> None:
    skill, launcher = make()
    assert skill.execute("fechar_app", {"app": CHROME}, CTX) == AppNotRunning("Google Chrome")
    assert launcher.closed == []


def test_close_exact_single_instance_needs_no_confirmation() -> None:
    skill, _ = make(running={"Google Chrome": 1})
    assert spec(skill, "fechar_app").requires_confirmation({"app": CHROME}) is False


def test_close_inexact_match_needs_confirmation() -> None:
    skill, _ = make(running={"Google Chrome": 1})
    assert spec(skill, "fechar_app").requires_confirmation({"app": CROME}) is True


def test_close_with_several_instances_needs_confirmation() -> None:
    skill, _ = make(running={"Google Chrome": 2})
    assert spec(skill, "fechar_app").requires_confirmation({"app": CHROME}) is True


def test_open_never_needs_confirmation() -> None:
    skill, _ = make(running={"Google Chrome": 2})
    assert spec(skill, "abrir_app").requires_confirmation({"app": CROME}) is False


def test_describe_is_a_pt_br_infinitive() -> None:
    skill, _ = make()
    assert spec(skill, "fechar_app").describe({"app": CHROME}) == "fechar Google Chrome"
    assert spec(skill, "abrir_app").describe({}) == "abrir um programa"
