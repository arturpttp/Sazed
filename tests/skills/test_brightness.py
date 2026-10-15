from datetime import datetime

import pytest

from fakes.ports import FakeBrightness
from sazed.core.outcomes import (
    BrightnessChanged,
    BrightnessSet,
    BrightnessUnsupported,
    InvalidPercent,
)
from sazed.core.skill import SkillContext
from sazed.core.types import SlotValue, Unmatched
from sazed.skills.pc.brightness import BrightnessSkill

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))


def pct(n: int) -> dict[str, SlotValue]:
    return {"percent": SlotValue("percent", n, str(n), 1.0)}


def alvo(n: int) -> dict[str, SlotValue]:
    return {"alvo": SlotValue("alvo", n, str(n), 1.0)}


def test_set() -> None:
    b = FakeBrightness(50)
    assert BrightnessSkill(b).execute("brilho_definir", pct(30), CTX) == BrightnessSet(30)
    assert b.level == 30


def test_steps_and_levels_mirror_volume() -> None:
    b = FakeBrightness(50)
    skill = BrightnessSkill(b)
    assert skill.execute("brilho_aumentar", {}, CTX) == BrightnessChanged(60)
    assert skill.execute("brilho_diminuir", pct(0), CTX) == BrightnessChanged(60)
    assert skill.execute("brilho_diminuir", alvo(100), CTX) == BrightnessSet(100)
    assert b.level == 100


def test_out_of_range_is_explained() -> None:
    b = FakeBrightness(50)
    slots = {"percent": Unmatched("percent", "150", None)}
    assert BrightnessSkill(b).execute("brilho_aumentar", slots, CTX) == InvalidPercent("150")
    assert b.level == 50


@pytest.mark.parametrize("intent", ["brilho_definir", "brilho_aumentar", "brilho_diminuir"])
def test_unsupported_monitor_is_reported_honestly(intent: str) -> None:
    slots = pct(30) if intent == "brilho_definir" else {}
    outcome = BrightnessSkill(FakeBrightness(None)).execute(intent, slots, CTX)
    assert outcome == BrightnessUnsupported()


def test_a_refused_set_is_unsupported() -> None:
    b = FakeBrightness(50, accepts=False)
    assert BrightnessSkill(b).execute("brilho_definir", pct(30), CTX) == BrightnessUnsupported()
