from fakes.ports import fake_pc_ports
from sazed.core.types import SlotValue
from sazed.runtime.config import Config
from sazed.runtime.extractors import build_extractors
from sazed.runtime.skills import build_skills


def test_every_declared_slot_has_an_extractor() -> None:
    skill_set = build_skills(fake_pc_ports([]), Config())
    declared = {
        slot.name for skill in skill_set.skills for spec in skill.intents for slot in spec.slots
    }
    assert declared <= set(skill_set.extractors())


def test_app_extractor_uses_catalog_names_and_aliases() -> None:
    extract = build_extractors(["WhatsApp"])["app"]
    assert extract("abre o zap", {"zap": "WhatsApp"}) == SlotValue(
        "app", "WhatsApp", "zap", 1.0, exact=True
    )
