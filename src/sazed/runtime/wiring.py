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
from sazed.runtime.logs import setup_logging
from sazed.runtime.skills import PcPorts, build_skills, file_area
from sazed.skills.pc.files import KNOWN_FOLDERS


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
    ports: PcPorts,
    clock: Callable[[], datetime] | None = None,
    rng: Random | None = None,
) -> SazedApp:
    clock = clock or datetime.now
    rng = rng or Random()
    store = SqliteCoppermind(config.data.dir / "coppermind.db")
    skill_set = build_skills(ports, config, change_log=store)
    index = IntentMatcher(embedder)
    for skill in skill_set.skills:
        for spec in skill.intents:
            index.add_examples(spec.id, spec.examples)
    assistant = Assistant(
        skills=skill_set.skills,
        index=index,
        extractors=skill_set.extractors(),
        store=store,
        aliases={"app": skill_set.app_aliases},
        settings=settings_from(config),
        clock=clock,
        rng=rng,
    )
    return SazedApp(assistant, store, index, skill_set.skills, config, rng, clock)


log = logging.getLogger(__name__)


class StartupError(Exception):
    """Sazed cannot start. `str(error)` is a pt-BR message meant for the user."""


def build_default_app(config: Config) -> SazedApp:
    from sazed.adapters.onnx.embedder import OnnxEmbedder
    from sazed.adapters.windows.audio import PycawAudio
    from sazed.adapters.windows.brightness import WmiBrightness
    from sazed.adapters.windows.catalog import StartMenuCatalog
    from sazed.adapters.windows.fileops import WindowsFileChanger
    from sazed.adapters.windows.files import (
        WindowsFileOpener,
        WindowsFileSearch,
        WindowsKnownFolders,
    )
    from sazed.adapters.windows.launcher import WindowsLauncher
    from sazed.adapters.windows.media import WinRtMedia
    from sazed.adapters.windows.opener import ShellOpener
    from sazed.adapters.windows.power import WindowsPower
    from sazed.adapters.windows.screen import WindowsScreen
    from sazed.adapters.windows.status import PsutilStatus
    from sazed.adapters.windows.store import StoreCatalog
    from sazed.adapters.windows.windows import WindowsWindowControl
    from sazed.skills.pc.apps import CombinedCatalog

    known = WindowsKnownFolders(config.folders)
    ports = PcPorts(
        catalog=CombinedCatalog([StartMenuCatalog(), StoreCatalog()]),
        launcher=WindowsLauncher(),
        audio=PycawAudio(),
        media=WinRtMedia(),
        power=WindowsPower(),
        screen=WindowsScreen(),
        brightness=WmiBrightness(),
        opener=ShellOpener(),
        status=PsutilStatus(),
        windows=WindowsWindowControl(),
        folders=known,
        files=WindowsFileSearch([str(Path.home()), *(str(p) for p in config.folders.values())]),
        file_opener=WindowsFileOpener(),
        changer=WindowsFileChanger(),
        file_area=file_area(
            profile=str(Path.home()),
            configured=[str(p) for p in config.folders.values()],
            known=[p for p in map(known.resolve, KNOWN_FOLDERS) if p is not None],
            data_dir=str(config.data.dir),
            project=str(Path(__file__).resolve().parents[3]),  # the repository
        ),
    )
    return build_app(config, embedder=OnnxEmbedder(config.model.embedder_path), ports=ports)


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
