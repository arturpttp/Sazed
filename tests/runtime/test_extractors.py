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


def test_window_and_file_slots_have_extractors() -> None:
    found = build_extractors(
        [], folder_names=["Downloads"], folder_synonyms={"baixados": "Downloads"}
    )
    assert found["lado"]("joga pra esquerda", {}) == SlotValue("lado", "esquerda", "esquerda", 1.0)
    assert found["monitor"]("pro monitor 2", {}) == SlotValue("monitor", 2, "monitor 2", 1.0)
    assert found["pasta"]("abre os baixados", {}) == SlotValue(
        "pasta", "Downloads", "baixados", 1.0
    )
    assert found["tipo"]("acha a planilha x", {}) == SlotValue("tipo", "planilha", "planilha", 1.0)
    assert found["arquivo"]("acha a planilha x", {}) == SlotValue("arquivo", "x", "x", 1.0)


def test_file_change_slots_have_extractors() -> None:
    found = build_extractors([], folder_names=["Documentos"], folder_synonyms={})
    assert found["item"]("apaga o rascunho", {}) == SlotValue(
        "item", "arquivo:rascunho", "rascunho", 1.0
    )
    assert found["destino"]("move x pra documentos", {}) == SlotValue(
        "destino", "Documentos", "documentos", 1.0
    )
    assert found["novo_nome"]("renomeia x pra Nome Novo", {}) == SlotValue(
        "novo_nome", "Nome Novo", "Nome Novo", 1.0
    )
