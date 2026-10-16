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
    FakeFileOpener,
    FakeFolders,
    FakeLauncher,
    FakeMedia,
    FakeOpener,
    FakePower,
    FakeScreen,
    FakeSearch,
    FakeStatus,
    FakeWindows,
)
from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.learning import LearningThresholds
from sazed.core.policy import Thresholds
from sazed.core.response import Response
from sazed.core.skill import Skill
from sazed.runtime.assistant import Assistant, Settings
from sazed.runtime.config import Config
from sazed.runtime.skills import PcPorts, build_skills
from sazed.skills.pc.files import FileHit
from sazed.skills.pc.windows import Monitor, Rect, WindowRef

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
    windows: FakeWindows
    search: FakeSearch
    file_opener: FakeFileOpener

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
    windows: dict[str | None, list[WindowRef]] | None = None,
    files: Sequence[FileHit] = (),
) -> Harness:
    index = ScriptedIndex(script)
    store = store or SqliteCoppermind(":memory:")
    launcher = FakeLauncher(running=running, fail_with=launcher_error)
    audio = FakeAudio(volume=volume)
    clock = ManualClock()
    opener, power, screen = FakeOpener(), FakePower(), FakeScreen()
    brightness, status = FakeBrightness(), FakeStatus()
    desk = FakeWindows(windows or {}, [Monitor(1, Rect(0, 0, 1920, 1040), True)])
    search = FakeSearch(files)
    file_opener = FakeFileOpener({hit.path for hit in files})
    folders = FakeFolders({"Downloads": "C:/U/Downloads"})
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
        windows=desk,
        folders=folders,
        files=search,
        file_opener=file_opener,
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
        assistant,
        index,
        store,
        launcher,
        audio,
        clock,
        opener,
        power,
        screen,
        brightness,
        status,
        desk,
        search,
        file_opener,
    )
