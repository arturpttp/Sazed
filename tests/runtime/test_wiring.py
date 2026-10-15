from pathlib import Path
from random import Random

from fakes.clock import ManualClock
from fakes.embedder import HashingEmbedder
from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher
from sazed.core.decisions import Confirm, Execute
from sazed.runtime.config import Config, DataConfig, LearningConfig, NluConfig
from sazed.runtime.wiring import SazedApp, build_app, settings_from


def boot(config: Config) -> SazedApp:
    return build_app(
        config,
        embedder=HashingEmbedder(),
        catalog=FakeCatalog(["Google Chrome"]),
        launcher=FakeLauncher(),
        audio=FakeAudio(),
        clock=ManualClock(),
        rng=Random(0),
    )


def test_settings_follow_the_config() -> None:
    config = Config()
    settings = settings_from(config)
    assert settings.user_name == config.user.name
    assert settings.thresholds.t_exec == config.nlu.t_exec
    assert settings.thresholds.t_confirm == config.nlu.t_confirm
    assert settings.thresholds.g_min == config.nlu.g_min
    assert settings.learning.t_conflict == config.learning.t_conflict
    assert settings.learning.t_dup == config.learning.t_dup
    assert settings.context_ttl_seconds == config.dialogue.context_ttl_seconds


def test_learning_persists_across_restarts_and_changes_the_decision(tmp_path: Path) -> None:
    # Thresholds chosen so only an exact (learned) example executes: everything else confirms.
    config = Config(
        data=DataConfig(dir=tmp_path),
        nlu=NluConfig(t_exec=0.999, t_confirm=0.0, g_min=0.0),
        learning=LearningConfig(t_conflict=1.0, t_dup=0.999),
    )
    app = boot(config)
    first = app.assistant.handle("abre o chrome agora")
    assert isinstance(first.decision, Confirm)
    assert first.decision.intent_id == "abrir_app"
    app.assistant.handle("sim")
    app.close()

    restarted = boot(config)
    again = restarted.assistant.handle("abre o chrome agora")
    assert isinstance(again.decision, Execute)
    assert (tmp_path / "coppermind.db").exists()


def test_greeting_addresses_the_configured_user(tmp_path: Path) -> None:
    app = boot(Config(data=DataConfig(dir=tmp_path)))
    assert app.farewell() == "Até logo, Mestre Artur."
    assert "Mestre Artur" in app.greeting()
