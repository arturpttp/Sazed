"""Every skill, built from one bundle of ports. Used by wiring, evaluation and tests alike."""

from __future__ import annotations

from dataclasses import dataclass

from sazed.core.skill import Skill
from sazed.runtime.config import Config
from sazed.runtime.extractors import SlotExtractor, build_extractors
from sazed.skills.pc.apps import (
    DEFAULT_APP_ALIASES,
    AppCatalog,
    AppLauncher,
    AppsSkill,
    CombinedCatalog,
    StaticCatalog,
    site_entries,
)
from sazed.skills.pc.brightness import Brightness, BrightnessSkill
from sazed.skills.pc.media import MediaControl, MediaSkill
from sazed.skills.pc.power import Power, PowerSkill
from sazed.skills.pc.screen import Screen, ScreenSkill
from sazed.skills.pc.settings import PAGE_NAMES, SettingsSkill
from sazed.skills.pc.status import StatusSkill, SystemStatus
from sazed.skills.pc.volume import AudioControl, VolumeSkill
from sazed.skills.pc.web import UriOpener, WebSkill


@dataclass(frozen=True)
class PcPorts:
    catalog: AppCatalog
    launcher: AppLauncher
    audio: AudioControl
    media: MediaControl
    power: Power
    screen: Screen
    brightness: Brightness
    opener: UriOpener
    status: SystemStatus


@dataclass(frozen=True)
class SkillSet:
    skills: list[Skill]
    app_names: list[str]
    engine_names: list[str]
    page_names: tuple[str, ...]
    app_aliases: dict[str, str]

    def extractors(self) -> dict[str, SlotExtractor]:
        return build_extractors(self.app_names, self.engine_names, self.page_names)


def build_skills(ports: PcPorts, config: Config) -> SkillSet:
    catalog = CombinedCatalog(
        [ports.catalog, StaticCatalog(site_entries(config.effective_sites()))]
    )
    engines = config.search.effective_engines()
    skills: list[Skill] = [
        AppsSkill(catalog, ports.launcher),
        VolumeSkill(ports.audio),
        MediaSkill(ports.media),
        PowerSkill(ports.power),
        ScreenSkill(ports.screen),
        SettingsSkill(ports.opener),
        BrightnessSkill(ports.brightness),
        WebSkill(ports.opener, engines, config.search.default),
        StatusSkill(ports.status),
    ]
    names = [entry.name for entry in catalog.entries()]
    known = set(names)
    defaults = {alias: name for alias, name in DEFAULT_APP_ALIASES.items() if name in known}
    return SkillSet(skills, names, list(engines), PAGE_NAMES, {**defaults, **config.aliases})
