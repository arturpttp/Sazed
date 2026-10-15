"""Build the application from a Config. The only place adapters are chosen."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from random import Random

from sazed.adapters.sqlite.coppermind import CoppermindVersionError, SqliteCoppermind
from sazed.core.learning import LearningThresholds
from sazed.core.persona import Prompt, render
from sazed.core.policy import Thresholds
from sazed.core.skill import Skill
from sazed.nlu.embedder import Embedder
from sazed.nlu.matcher import IntentMatcher
from sazed.runtime.assistant import Assistant, Settings
from sazed.runtime.config import DEFAULT_CONFIG_PATH, Config, ConfigError, load_config
from sazed.runtime.extractors import build_extractors
from sazed.runtime.logs import setup_logging
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


log = logging.getLogger(__name__)


class StartupError(Exception):
    """Sazed cannot start. `str(error)` is a pt-BR message meant for the user."""


def build_default_app(config: Config) -> SazedApp:
    from sazed.adapters.onnx.embedder import OnnxEmbedder
    from sazed.adapters.windows.audio import PycawAudio
    from sazed.adapters.windows.catalog import StartMenuCatalog
    from sazed.adapters.windows.launcher import WindowsLauncher

    return build_app(
        config,
        embedder=OnnxEmbedder(config.model.embedder_path),
        catalog=StartMenuCatalog(),
        launcher=WindowsLauncher(),
        audio=PycawAudio(),
    )


def start(config_path: Path | None) -> SazedApp:
    path = config_path or DEFAULT_CONFIG_PATH
    try:
        config = load_config(path)
    except ConfigError as err:
        raise StartupError(str(err)) from None
    setup_logging(config.data.dir / "logs", debug=config.logging.debug)
    if not (config.model.embedder_path / "model.onnx").exists():
        raise StartupError(
            f"Não encontrei o modelo em {config.model.embedder_path}. "
            "Rode uma vez: uv run python scripts/fetch_model.py"
        )
    try:
        return build_default_app(config)
    except CoppermindVersionError:
        log.exception("coppermind schema is newer than this version")
        raise StartupError(
            "Minha mente de cobre foi gravada por uma versão mais nova de Sazed. "
            "Atualize o programa antes de continuar."
        ) from None
    except Exception:
        log.exception("startup failed")
        raise StartupError(
            "Peço desculpas, não consegui iniciar. Os detalhes estão no arquivo de log."
        ) from None
