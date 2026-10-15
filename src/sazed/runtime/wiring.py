"""Build the application from a Config. The only place adapters are chosen."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from random import Random

from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.learning import LearningThresholds
from sazed.core.persona import Prompt, render
from sazed.core.policy import Thresholds
from sazed.core.skill import Skill
from sazed.nlu.embedder import Embedder
from sazed.nlu.matcher import IntentMatcher
from sazed.runtime.assistant import Assistant, Settings
from sazed.runtime.config import Config
from sazed.runtime.extractors import build_extractors
from sazed.skills.pc.apps import AppCatalog, AppLauncher, AppsSkill
from sazed.skills.pc.volume import AudioControl, VolumeSkill


@dataclass
class SazedApp:
    assistant: Assistant
    store: SqliteCoppermind
    index: IntentMatcher
    skills: Sequence[Skill]
    config: Config
    rng: Random
    clock: Callable[[], datetime]

    def greeting(self) -> str:
        return render(Prompt.GREETING, nome=self.config.user.name, rng=self.rng)

    def farewell(self) -> str:
        return render(Prompt.FAREWELL, nome=self.config.user.name, rng=self.rng)

    def close(self) -> None:
        self.store.close()


def settings_from(config: Config) -> Settings:
    return Settings(
        user_name=config.user.name,
        thresholds=Thresholds(config.nlu.t_exec, config.nlu.t_confirm, config.nlu.g_min),
        learning=LearningThresholds(config.learning.t_conflict, config.learning.t_dup),
        context_ttl_seconds=config.dialogue.context_ttl_seconds,
    )


def build_app(
    config: Config,
    *,
    embedder: Embedder,
    catalog: AppCatalog,
    launcher: AppLauncher,
    audio: AudioControl,
    clock: Callable[[], datetime] | None = None,
    rng: Random | None = None,
) -> SazedApp:
    clock = clock or datetime.now
    rng = rng or Random()
    store = SqliteCoppermind(config.data.dir / "coppermind.db")
    skills: list[Skill] = [AppsSkill(catalog, launcher), VolumeSkill(audio)]
    index = IntentMatcher(embedder)
    for skill in skills:
        for spec in skill.intents:
            index.add_examples(spec.id, spec.examples)
    names = [entry.name for entry in catalog.entries()]
    assistant = Assistant(
        skills=skills,
        index=index,
        extractors=build_extractors(names),
        store=store,
        aliases={"app": config.aliases},
        settings=settings_from(config),
        clock=clock,
        rng=rng,
    )
    return SazedApp(assistant, store, index, skills, config, rng, clock)
