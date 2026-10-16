"""Power safety, driven by the skill's own specs: a future power intent is covered automatically."""

import pytest

from fakes.ports import FakePower
from sazed.core.decisions import Confirm, ConfirmReason
from sazed.skills.pc.power import PowerSkill
from support.harness import Make

UNLEARNABLE = sorted(s.id for s in PowerSkill(FakePower()).intents if not s.learnable)


def test_there_are_power_intents_to_check() -> None:
    assert UNLEARNABLE  # an empty parametrisation would pass every test below vacuously


@pytest.mark.parametrize("intent", UNLEARNABLE)
def test_a_certain_power_command_still_confirms(make: Make, intent: str) -> None:
    h = make({"faz isso": {intent: 1.0}})
    r = h.say("faz isso")
    assert r.decision == Confirm(intent, {}, ConfirmReason.DESTRUCTIVE)
    assert h.power.calls == []


@pytest.mark.parametrize("intent", UNLEARNABLE)
def test_confirming_a_low_score_power_command_learns_nothing(make: Make, intent: str) -> None:
    # A LOW_SCORE confirm (unlike DESTRUCTIVE) normally learns the phrase: only the gate stops it.
    h = make({"faz isso aí": {intent: 0.80}})
    assert isinstance(h.say("faz isso aí").decision, Confirm)
    h.say("sim")
    assert len(h.power.calls) == 1
    assert h.store.learned() == []


@pytest.mark.parametrize("intent", UNLEARNABLE)
def test_a_correction_towards_a_power_command_confirms_and_learns_nothing(
    make: Make, intent: str
) -> None:
    h = make({"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.6}, "desligar": {intent: 0.95}})
    h.say("abre o chrome")
    r = h.say("não, era pra desligar")
    assert isinstance(r.decision, Confirm)
    assert h.power.calls == []
    h.say("sim")
    assert h.store.learned() == []
