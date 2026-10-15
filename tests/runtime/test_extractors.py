from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher
from sazed.core.types import SlotValue
from sazed.runtime.extractors import build_extractors
from sazed.skills.pc.apps import AppsSkill
from sazed.skills.pc.volume import VolumeSkill


def test_every_declared_slot_has_an_extractor() -> None:
    skills = [AppsSkill(FakeCatalog([]), FakeLauncher()), VolumeSkill(FakeAudio())]
    declared = {slot.name for skill in skills for spec in skill.intents for slot in spec.slots}
    assert declared <= set(build_extractors([]))


def test_app_extractor_uses_catalog_names_and_aliases() -> None:
    extract = build_extractors(["WhatsApp"])["app"]
    assert extract("abre o zap", {"zap": "WhatsApp"}) == SlotValue(
        "app", "WhatsApp", "zap", 1.0, exact=True
    )
