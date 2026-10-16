from datetime import datetime

import pytest

from fakes.ports import FakeMedia
from sazed.core.outcomes import MediaNext, MediaPrevious, MediaToggled, NoMediaSession, NowPlaying
from sazed.core.skill import SkillContext
from sazed.skills.pc.media import MediaSkill, NowPlayingInfo

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))


@pytest.mark.parametrize(
    ("intent", "call", "outcome"),
    [
        ("midia_tocar_pausar", "toggle", MediaToggled()),
        ("midia_proxima", "next", MediaNext()),
        ("midia_anterior", "previous", MediaPrevious()),
    ],
)
def test_controls_reach_the_session(intent: str, call: str, outcome: object) -> None:
    media = FakeMedia()
    assert MediaSkill(media).execute(intent, {}, CTX) == outcome
    assert media.calls == [call]


@pytest.mark.parametrize(
    "intent", ["midia_tocar_pausar", "midia_proxima", "midia_anterior", "midia_tocando"]
)
def test_without_a_session_sazed_says_so(intent: str) -> None:
    assert MediaSkill(FakeMedia(session=False)).execute(intent, {}, CTX) == NoMediaSession()


def test_now_playing_reports_title_and_artist() -> None:
    media = FakeMedia(info=NowPlayingInfo("Bohemian Rhapsody", "Queen"))
    outcome = MediaSkill(media).execute("midia_tocando", {}, CTX)
    assert outcome == NowPlaying("Bohemian Rhapsody", "Queen")


def test_only_track_skips_are_repeatable() -> None:
    repeatable = {s.id for s in MediaSkill(FakeMedia()).intents if s.repeatable}
    assert repeatable == {"midia_proxima", "midia_anterior"}
