from datetime import datetime

from fakes.ports import FakeAudio
from sazed.core.outcomes import Muted, Unmuted, VolumeChanged, VolumeSet
from sazed.core.skill import SkillContext
from sazed.core.types import SlotValue
from sazed.skills.pc.volume import VolumeSkill

CTX = SkillContext(now=datetime(2026, 10, 14, 12, 0))


def pct(n: int) -> dict[str, SlotValue]:
    return {"percent": SlotValue("percent", n, str(n), 1.0)}


def test_set_volume() -> None:
    audio = FakeAudio(volume=50)
    assert VolumeSkill(audio).execute("volume_definir", pct(30), CTX) == VolumeSet(30)
    assert audio.volume == 30


def test_increase_uses_default_step() -> None:
    audio = FakeAudio(volume=50)
    assert VolumeSkill(audio).execute("volume_aumentar", {}, CTX) == VolumeChanged(60)
    assert audio.volume == 60


def test_increase_uses_given_step() -> None:
    audio = FakeAudio(volume=50)
    VolumeSkill(audio).execute("volume_aumentar", pct(25), CTX)
    assert audio.volume == 75


def test_increase_clamps_at_100() -> None:
    audio = FakeAudio(volume=95)
    assert VolumeSkill(audio).execute("volume_aumentar", {}, CTX) == VolumeChanged(100)
    assert audio.volume == 100


def test_decrease_clamps_at_0() -> None:
    audio = FakeAudio(volume=5)
    VolumeSkill(audio).execute("volume_diminuir", {}, CTX)
    assert audio.volume == 0


def test_mute_and_unmute() -> None:
    audio = FakeAudio()
    skill = VolumeSkill(audio)
    assert (
        skill.execute("volume_mudo", {"mudo": SlotValue("mudo", True, "muta", 1.0)}, CTX) == Muted()
    )
    assert audio.muted is True
    off = {"mudo": SlotValue("mudo", False, "tira do mudo", 1.0)}
    assert skill.execute("volume_mudo", off, CTX) == Unmuted()
    assert audio.muted is False


def test_mute_without_slot_mutes() -> None:
    audio = FakeAudio()
    VolumeSkill(audio).execute("volume_mudo", {}, CTX)
    assert audio.muted is True


def alvo(n: int) -> dict[str, SlotValue]:
    return {"alvo": SlotValue("alvo", n, str(n), 1.0)}


def test_decrease_to_a_level_above_the_current_one_sets_that_level() -> None:
    audio = FakeAudio(volume=50)
    assert VolumeSkill(audio).execute("volume_diminuir", alvo(100), CTX) == VolumeSet(100)
    assert audio.volume == 100


def test_increase_to_a_level_below_the_current_one_sets_that_level() -> None:
    audio = FakeAudio(volume=80)
    assert VolumeSkill(audio).execute("volume_aumentar", alvo(20), CTX) == VolumeSet(20)
    assert audio.volume == 20


def test_a_level_of_zero_is_kept() -> None:
    audio = FakeAudio(volume=50)
    VolumeSkill(audio).execute("volume_diminuir", {**pct(10), **alvo(0)}, CTX)
    assert audio.volume == 0


def test_a_level_wins_over_the_same_number_read_as_a_step() -> None:
    audio = FakeAudio(volume=50)
    VolumeSkill(audio).execute("volume_diminuir", {**pct(100), **alvo(100)}, CTX)
    assert audio.volume == 100


def test_confirmation_names_the_level() -> None:
    spec = next(s for s in VolumeSkill(FakeAudio()).intents if s.id == "volume_diminuir")
    assert spec.describe(alvo(100)) == "deixar o volume em 100%"
    assert spec.describe({}) == "diminuir o volume"
