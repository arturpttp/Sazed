"""Live learning with the real model: what a learned phrase does to the commands around it.

The fixture never learns, so it cannot see this. Found by hand (2026-10-15): after "abre o
whatsapp" was learned from a confirmation, "fecha o whatsapp" ranked opening, because e5
weighs the object over the verb.
"""

from pathlib import Path
from random import Random

import pytest

from fakes.clock import ManualClock
from fakes.ports import fake_pc_ports
from sazed.adapters.onnx.embedder import OnnxEmbedder
from sazed.core.decisions import Confirm
from sazed.nlu.normalize import normalize
from sazed.runtime.config import DEFAULT_MODEL_DIR, Config, DataConfig, NluConfig
from sazed.runtime.wiring import SazedApp, build_app

pytestmark = pytest.mark.model

NAMES = ["WhatsApp", "Spotify", "Discord", "Google Chrome"]


@pytest.fixture(scope="module")
def embedder() -> OnnxEmbedder:
    if not (DEFAULT_MODEL_DIR / "model.onnx").exists():
        pytest.fail("model missing: run `uv run python scripts/fetch_model.py` first")
    return OnnxEmbedder(DEFAULT_MODEL_DIR)


@pytest.fixture
def app(tmp_path: Path, embedder: OnnxEmbedder) -> SazedApp:
    # Every command confirms, so every "sim" below teaches the phrase (as ~half do in use).
    config = Config(
        data=DataConfig(dir=tmp_path), nlu=NluConfig(t_exec=1.0, t_confirm=0.0, g_min=0.0)
    )
    return build_app(
        config,
        embedder=embedder,
        ports=fake_pc_ports(NAMES),
        clock=ManualClock(),
        rng=Random(0),
    )


def teach(app: SazedApp, text: str, intent: str) -> None:
    asked = app.assistant.handle(text)
    assert isinstance(asked.decision, Confirm)
    assert asked.decision.intent_id == intent
    app.assistant.handle("sim")


def top(app: SazedApp, text: str) -> str:
    ranking = app.index.rank(normalize(text))
    return ranking[0].intent_id


def test_confirming_an_open_does_not_turn_closing_that_app_into_opening(app: SazedApp) -> None:
    teach(app, "abre o whatsapp", "abrir_app")
    assert top(app, "fecha o whatsapp") == "fechar_app"


def test_a_learned_wording_does_not_pull_the_opposite_verb_for_that_app(app: SazedApp) -> None:
    teach(app, "bota o spotify pra rodar", "abrir_app")
    assert top(app, "fecha o spotify") == "fechar_app"
    assert top(app, "fecha o spotify pra mim") == "fechar_app"


def test_a_learned_wording_carries_over_to_other_apps(app: SazedApp) -> None:
    # Measured 2026-10-15: "bota o discord pra rodar" 0.915 vs 0.909 before, 0.958 after.
    teach(app, "bota o spotify pra rodar", "abrir_app")
    best = app.index.rank(normalize("bota o discord pra rodar"))[0]
    assert best.intent_id == "abrir_app"
    assert best.score >= Config().nlu.t_exec
