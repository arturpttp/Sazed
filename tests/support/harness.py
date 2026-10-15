"""Assistant wired to fakes, for runtime tests."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from random import Random

from fakes.clock import ManualClock
from fakes.index import ScriptedIndex
from fakes.ports import (
    FakeAudio,
    FakeBrightness,
    FakeCatalog,
    FakeLauncher,
    FakeMedia,
    FakeOpener,
    FakePower,
    FakeScreen,
    FakeStatus,
)
from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.learning import LearningThresholds
from sazed.core.policy import Thresholds
from sazed.core.response import Response
from sazed.core.skill import Skill
from sazed.runtime.assistant import Assistant, Settings
from sazed.runtime.config import Config
from sazed.runtime.skills import PcPorts, build_skills

APPS = ["Google Chrome", "Spotify", "Discord", "Visual Studio Code", "Claude Code"]
SETTINGS = Settings(
    user_name="Artur",
    thresholds=Thresholds(t_exec=0.90, t_confirm=0.70, g_min=0.05),
    learning=LearningThresholds(t_conflict=0.85, t_dup=0.97),
    context_ttl_seconds=60,
)


@dataclass
class Harness:
    assistant: Assistant
    index: ScriptedIndex
    store: SqliteCoppermind
    launcher: FakeLauncher
    audio: FakeAudio
    clock: ManualClock
    opener: FakeOpener
    power: FakePower
    screen: FakeScreen
    brightness: FakeBrightness
    status: FakeStatus

    def say(self, text: str) -> Response:
        return self.assistant.handle(text)


Make = Callable[..., Harness]


def build_harness(
    script: Mapping[str, Mapping[str, float]] | None = None,
    *,
    running: dict[str, int] | None = None,
    volume: int = 50,
    aliases: Mapping[str, str] | None = None,
    launcher_error: Exception | None = None,
    store: SqliteCoppermind | None = None,
    extra_skills: Sequence[Skill] = (),
) -> Harness:
    index = ScriptedIndex(script)
    store = store or SqliteCoppermind(":memory:")
    launcher = FakeLauncher(running=running, fail_with=launcher_error)
    audio = FakeAudio(volume=volume)
    clock = ManualClock()
    opener, power, screen = FakeOpener(), FakePower(), FakeScreen()
    brightness, status = FakeBrightness(), FakeStatus()
    ports = PcPorts(
        catalog=FakeCatalog(APPS),
        launcher=launcher,
        audio=audio,
        media=FakeMedia(),
        power=power,
        screen=screen,
        brightness=brightness,
        opener=opener,
        status=status,
    )
    skill_set = build_skills(ports, Config())
    assistant = Assistant(
        skills=[*skill_set.skills, *extra_skills],
        index=index,
        extractors=skill_set.extractors(),
        store=store,
        aliases={"app": {**skill_set.app_aliases, **dict(aliases or {})}},
        settings=SETTINGS,
        clock=clock,
        rng=Random(0),
    )
    return Harness(
        assistant, index, store, launcher, audio, clock, opener, power, screen, brightness, status
    )
