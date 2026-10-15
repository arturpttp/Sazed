from datetime import datetime
from pathlib import Path
from random import Random

import pytest

from fakes.clock import ManualClock
from fakes.embedder import HashingEmbedder
from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher
from sazed.core.policy import Thresholds
from sazed.core.skill import SkillContext
from sazed.core.types import SlotValue
from sazed.runtime.config import Config, DataConfig, ModelConfig
from sazed.runtime.insight import (
    PORT_DESCRIPTIONS,
    capabilities,
    config_view,
    explain,
    learned_for,
    path_rows,
    ports,
    skills_for_listing,
)
from sazed.runtime.wiring import build_app

TH = Thresholds(t_exec=0.94, t_confirm=0.88, g_min=0.01)


def test_listing_skills_match_the_wired_skills(tmp_path: Path) -> None:
    app = build_app(
        Config(data=DataConfig(dir=tmp_path)),
        embedder=HashingEmbedder(),
        catalog=FakeCatalog([]),
        launcher=FakeLauncher(),
        audio=FakeAudio(),
        clock=ManualClock(),
        rng=Random(0),
    )
    wired = [(s.id, [i.id for i in s.intents]) for s in app.skills]
    listed = [(s.id, [i.id for i in s.intents]) for s in skills_for_listing()]
    app.close()
    assert listed == wired


def test_capabilities_describe_every_intent() -> None:
    infos = capabilities(skills_for_listing())
    by_id = {i.id: i for s in infos for i in s.intents}
    abrir = by_id["abrir_app"]
    assert abrir.examples == len(abrir.example_texts) >= 8
    assert [(s.name, s.required) for s in abrir.slots] == [("app", True)]
    assert abrir.slots[0].question == "Qual programa devo abrir?"
    assert abrir.confirmation == "nunca"
    assert by_id["fechar_app"].confirmation == "conforme o pedido"
    assert abrir.description.startswith("abrir")


def test_listing_skills_never_execute() -> None:
    skill = skills_for_listing()[0]
    slots = {"app": SlotValue("app", "Chrome", "chrome", 1.0)}
    with pytest.raises(RuntimeError, match="never calls ports"):
        skill.execute("abrir_app", slots, SkillContext(datetime(2026, 10, 15)))


def test_every_port_has_a_pt_br_description() -> None:
    found = ports(skills_for_listing())
    assert {p.name for p in found} == {"AppCatalog", "AppLauncher", "AudioControl"}
    assert {p.name for p in found} <= set(PORT_DESCRIPTIONS)
    catalog = next(p for p in found if p.name == "AppCatalog")
    assert catalog.methods == ("entries",)
    assert catalog.skill == "apps"


@pytest.mark.parametrize(
    ("ranking", "decision", "slots", "needle"),
    [
        ([("abrir_app", 0.97), ("fechar_app", 0.90)], "Execute", {}, "limiar de execução"),
        ([("abrir_app", 0.90), ("fechar_app", 0.80)], "Confirm", {}, "entre o limiar"),
        ([("abrir_app", 0.96), ("fechar_app", 0.955)], "Confirm", {}, "próximos"),
        ([("fechar_app", 0.99), ("abrir_app", 0.80)], "Confirm", {}, "exige confirmação"),
        ([("abrir_app", 0.50)], "NotUnderstood", {}, "abaixo do limiar de confirmação"),
        ([], "NotUnderstood", {}, "Nenhum pedido"),
        ([("abrir_app", 0.97)], "AskSlot", {}, "Qual programa devo abrir?"),
        ([("abrir_app", 0.97)], "AskSlot", {"app": "Chrome|Chromium"}, "Chrome, Chromium"),
        ([], "control", {}, "diálogo"),
        ([], "error", {}, "log"),
        ([("abrir_app", 0.97)], "Inventado", {}, "Inventado"),
    ],
)
def test_explain(
    ranking: list[tuple[str, float]], decision: str, slots: dict[str, str], needle: str
) -> None:
    intent = ranking[0][0] if ranking else None
    text = explain(ranking, decision, slots, intent, skills_for_listing(), TH)
    assert needle in text


def test_explain_flags_a_decision_the_current_thresholds_would_not_make() -> None:
    text = explain([("abrir_app", 0.90)], "Execute", {}, "abrir_app", skills_for_listing(), TH)
    assert "limiares atuais" in text


def test_learned_for_links_examples_and_aliases() -> None:
    examples = [("abre o zap", "abrir_app"), ("fecha tudo", "fechar_app")]
    aliases = [("zap", "WhatsApp"), ("disc", "Discord")]
    found = learned_for("Abre o Zap!", examples, aliases)
    assert found == ["exemplo 'abre o zap' → abrir_app", "apelido 'zap' → WhatsApp"]


def test_config_view_reads_file_and_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[nlu]\nt_exec = 0.95\n", encoding="utf-8")
    view = config_view(path)
    assert view.raw == {"nlu": {"t_exec": 0.95}}
    assert view.effective["nlu"]["t_exec"] == 0.95
    assert view.effective["nlu"]["t_confirm"] == 0.88
    assert view.config.nlu.t_exec == 0.95


def test_config_view_without_a_file(tmp_path: Path) -> None:
    view = config_view(tmp_path / "nada.toml")
    assert view.raw == {}
    assert view.effective["user"]["name"] == "Artur"


def test_path_rows_report_presence(tmp_path: Path) -> None:
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.onnx").write_bytes(b"x" * 10)
    config = Config(data=DataConfig(dir=tmp_path / "data"), model=ModelConfig(embedder_path=model))
    rows = {r.label: r for r in path_rows(config, tmp_path / "config.toml")}
    assert rows["Modelo (model.onnx)"].exists and rows["Modelo (model.onnx)"].size == 10
    assert not rows["Mente de cobre"].exists
    assert rows["Mente de cobre"].path.endswith("coppermind.db")
    assert not rows["config.toml"].exists
    assert not (tmp_path / "data").exists()  # listing paths creates nothing
