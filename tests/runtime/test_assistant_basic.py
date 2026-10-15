import logging

import pytest

from sazed.core.decisions import AskSlot, Confirm, Execute, NotUnderstood
from sazed.core.outcomes import ActionFailed, AppNotFound, AppOpened, VolumeSet
from sazed.core.persona.definition import TEMPLATES
from support.harness import Make

OPEN_CHROME = {"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60}}
VOLUME_30 = {"volume em 30": {"volume_definir": 0.97, "volume_aumentar": 0.70}}


def test_clear_command_executes_and_opens_the_app(make: Make) -> None:
    h = make(OPEN_CHROME)
    r = h.say("Abre o Chrome!")
    assert h.launcher.launched == ["Google Chrome"]
    assert r.outcome == AppOpened("Google Chrome")
    assert isinstance(r.decision, Execute)
    assert "Google Chrome" in r.text


def test_unknown_text_is_not_understood_and_does_nothing(make: Make) -> None:
    h = make(OPEN_CHROME)
    r = h.say("qual o sentido da vida")
    assert r.decision == NotUnderstood()
    assert h.launcher.launched == []
    assert r.text in {t.format(mestre="Mestre Artur") for t in TEMPLATES["NotUnderstood"]}


def test_low_score_asks_for_confirmation_without_executing(make: Make) -> None:
    h = make({"abre aí o chrome": {"abrir_app": 0.80, "fechar_app": 0.30}})
    r = h.say("abre aí o chrome")
    assert isinstance(r.decision, Confirm)
    assert h.launcher.launched == []
    assert "abrir Google Chrome" in r.text
    assert "abrir_app" not in r.text


def test_missing_slot_asks_the_slot_question(make: Make) -> None:
    h = make({"abre o programa": {"abrir_app": 0.95, "fechar_app": 0.40}})
    r = h.say("abre o programa")
    assert isinstance(r.decision, AskSlot)
    assert "Qual programa devo abrir?" in r.text


def test_unknown_app_reports_not_found(make: Make) -> None:
    h = make({"abre o photoshop": {"abrir_app": 0.95, "fechar_app": 0.40}})
    r = h.say("abre o photoshop")
    assert r.outcome == AppNotFound("photoshop", None)
    assert "photoshop" in r.text
    assert h.launcher.launched == []


def test_volume_command_changes_the_audio_state(make: Make) -> None:
    h = make(VOLUME_30)
    r = h.say("volume em 30")
    assert h.audio.volume == 30
    assert r.outcome == VolumeSet(30)
    assert "30%" in r.text


def test_skill_exception_is_rendered_politely_and_logged(
    make: Make, caplog: pytest.LogCaptureFixture
) -> None:
    h = make({**OPEN_CHROME, **VOLUME_30}, launcher_error=OSError("WinError 2: secret internals"))
    with caplog.at_level(logging.ERROR):
        r = h.say("abre o chrome")
    assert r.outcome == ActionFailed("abrir Google Chrome")
    assert "secret internals" not in r.text
    assert "WinError" not in r.text
    assert "secret internals" in caplog.text
    assert h.say("volume em 30").outcome == VolumeSet(30)


def test_unexpected_error_outside_skills_is_generic(
    make: Make, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = make(VOLUME_30)

    def explode(text: str) -> object:
        raise RuntimeError("index exploded")

    monkeypatch.setattr(h.index, "rank", explode)
    with caplog.at_level(logging.ERROR):
        r = h.say("volume em 30")
    assert r.outcome == ActionFailed("atender a esse pedido")
    assert "exploded" not in r.text
    assert "index exploded" in caplog.text
    monkeypatch.undo()
    assert h.say("volume em 30").outcome == VolumeSet(30)


def test_every_turn_records_an_episode(make: Make) -> None:
    h = make(OPEN_CHROME)
    h.say("Abre o Chrome!")
    h.say("qual o sentido da vida")
    newest, older = h.store.episodes(10)
    assert older.episode.utterance == "Abre o Chrome!"
    assert older.episode.decision == "Execute"
    assert older.episode.outcome == "AppOpened"
    assert older.episode.intent_id == "abrir_app"
    assert older.episode.ranking[0].intent_id == "abrir_app"
    assert older.episode.slots == {"app": "Google Chrome"}
    assert newest.episode.decision == "NotUnderstood"
