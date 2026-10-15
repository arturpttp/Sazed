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
