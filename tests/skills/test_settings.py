from datetime import datetime

from fakes.ports import FakeOpener
from sazed.core.outcomes import SettingsOpened, UnknownSettingsPage
from sazed.core.skill import SkillContext
from sazed.core.types import SlotValue, Unmatched
from sazed.skills.pc.settings import PAGE_NAMES, SETTINGS_PAGES, SettingsSkill

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))


def test_every_page_is_a_settings_uri_and_names_are_unique() -> None:
    assert all(p.uri.startswith("ms-settings:") for p in SETTINGS_PAGES)
    assert len(PAGE_NAMES) == len(set(PAGE_NAMES))


def test_a_named_page_opens_its_uri() -> None:
    opener = FakeOpener()
    slots = {"pagina": SlotValue("pagina", "dispositivos", "dispositivos", 1.0)}
    outcome = SettingsSkill(opener).execute("abrir_configuracao", slots, CTX)
    assert outcome == SettingsOpened("bluetooth")
    assert opener.opened == ["ms-settings:bluetooth"]


def test_no_page_opens_the_settings_home() -> None:
    opener = FakeOpener()
    outcome = SettingsSkill(opener).execute("abrir_configuracao", {}, CTX)
    assert outcome == SettingsOpened("início")
    assert opener.opened == ["ms-settings:"]


def test_an_unknown_page_is_explained_and_opens_nothing() -> None:
    opener = FakeOpener()
    slots = {"pagina": Unmatched("pagina", "teletransporte", None)}
    outcome = SettingsSkill(opener).execute("abrir_configuracao", slots, CTX)
    assert outcome == UnknownSettingsPage("teletransporte")
    assert opener.opened == []
