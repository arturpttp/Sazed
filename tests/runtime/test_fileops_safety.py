"""Nothing on disk changes before "sim" — for every file-change intent, at any score.

Derived from the specs: a new intent with `confirms_itself` must get a phrase here, or
`test_every_self_confirming_intent_has_a_phrase` fails.
"""

from datetime import datetime
from pathlib import Path
from random import Random

import pytest

from fakes.clock import ManualClock
from fakes.embedder import HashingEmbedder
from fakes.ports import fake_pc_ports
from sazed.runtime.admin import LabelResult, learn_example
from sazed.runtime.config import Config, DataConfig
from sazed.runtime.skills import build_skills
from sazed.runtime.wiring import build_app
from sazed.skills.pc.files import FileHit
from sazed.skills.pc.fileops import ItemState
from support.harness import Make

SELF_CONFIRMING = sorted(
    spec.id
    for skill in build_skills(fake_pc_ports([]), Config()).skills
    for spec in skill.intents
    if spec.confirms_itself
)
PHRASES = {
    "arquivo_mover": "move o relatório pra pasta documentos",
    "arquivo_copiar": "copia o relatório pra pasta documentos",
    "arquivo_renomear": "renomeia o relatório pra final",
    "arquivo_apagar": "apaga o relatório",
    "pasta_criar": "cria uma pasta chamada nova",
}
REPORT = ItemState(r"C:\U\Downloads\relatório.docx", False, 10, 1.0, 0)
HIT = FileHit(REPORT.path, "relatório.docx", "Downloads", datetime(2026, 10, 14, 9))


def test_every_self_confirming_intent_has_a_phrase() -> None:
    assert sorted(PHRASES) == SELF_CONFIRMING


@pytest.mark.parametrize("intent", SELF_CONFIRMING)
@pytest.mark.parametrize("score", [0.75, 0.89, 0.95, 1.0])
def test_nothing_changes_before_yes(make: Make, intent: str, score: float) -> None:
    h = make({PHRASES[intent]: {intent: score}}, files=[HIT], disk=[REPORT])
    r = h.say(PHRASES[intent])
    assert h.changer.calls == [], r.text
    assert r.text.endswith("Confirma, Mestre Artur?"), r.text
    h.say("sim")
    assert h.changer.calls != []


@pytest.mark.parametrize("intent", SELF_CONFIRMING)
def test_no_file_change_phrase_can_be_taught(tmp_path: Path, intent: str) -> None:
    app = build_app(
        Config(data=DataConfig(dir=tmp_path)),
        embedder=HashingEmbedder(),
        ports=fake_pc_ports([]),
        clock=ManualClock(),
        rng=Random(0),
    )
    found = learn_example(app, f"{PHRASES[intent]} rapidinho", intent, force=True)
    assert found is LabelResult.NOT_LEARNABLE
    assert app.store.examples() == []
