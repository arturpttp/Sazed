from datetime import datetime

import pytest

from fakes.ports import FakePower
from sazed.core.outcomes import Locked, Restarting, ShuttingDown, SigningOut, Suspending
from sazed.core.skill import SkillContext
from sazed.skills.pc.power import POWER_INTENTS, PowerSkill

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))


@pytest.mark.parametrize(
    ("intent", "call", "outcome"),
    [
        ("pc_bloquear", "lock", Locked()),
        ("pc_desligar", "shutdown", ShuttingDown()),
        ("pc_reiniciar", "restart", Restarting()),
        ("pc_suspender", "sleep", Suspending()),
        ("pc_sair_conta", "sign_out", SigningOut()),
    ],
)
def test_each_action_calls_its_port_method(intent: str, call: str, outcome: object) -> None:
    power = FakePower()
    assert PowerSkill(power).execute(intent, {}, CTX) == outcome
    assert power.calls == [call]


def test_power_intents_always_confirm_and_are_never_learned() -> None:
    specs = {s.id: s for s in PowerSkill(FakePower()).intents}
    assert {"pc_desligar", "pc_reiniciar", "pc_suspender", "pc_sair_conta"} == POWER_INTENTS
    for intent in POWER_INTENTS:
        assert specs[intent].requires_confirmation({}) is True
        assert specs[intent].learnable is False


def test_locking_runs_directly_and_may_be_learned() -> None:
    lock = next(s for s in PowerSkill(FakePower()).intents if s.id == "pc_bloquear")
    assert lock.requires_confirmation({}) is False
    assert lock.learnable is True
