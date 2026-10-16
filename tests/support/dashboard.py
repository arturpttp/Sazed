"""A DashboardApi over a temp data dir and fake machine; ENDPOINTS lists every GET route."""

from datetime import datetime
from pathlib import Path
from typing import Any

from fakes.ports import FakeCatalog
from fakes.system import FakeProbe, broken_git
from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.coppermind import Episode, NewAlias, NewExample, Reaction
from sazed.core.types import IntentScore
from sazed.interfaces.dashboard.api import DashboardApi
from sazed.interfaces.dashboard.sources import DevSources, ResourceSampler
from sazed.runtime.insight import CoppermindReader, config_view

NOW = datetime(2026, 10, 15, 12, 0)

ENDPOINTS = [
    "/api/overview",
    "/api/episodes",
    "/api/learning",
    "/api/dev",
    "/api/resources",
    "/api/examples",
    "/api/aliases",
    "/api/capabilities",
    "/api/catalog",
]


def seed(db: Path) -> None:
    store = SqliteCoppermind(db)
    store.learn([NewExample("abre o zap", "abrir_app", b"\x00", "confirmed")], [], NOW)
    store.learn([], [NewAlias("app", "zap", "WhatsApp")], NOW)
    ranking = (IntentScore("abrir_app", 0.97), IntentScore("fechar_app", 0.90))
    slots = {"app": "WhatsApp"}
    store.record_episode(
        Episode("abre o zap", NOW, ranking, slots, "Execute", "abrir_app", "AppOpened")
    )
    second = store.record_episode(
        Episode("toca algo", NOW, (IntentScore("abrir_app", 0.5),), {}, "NotUnderstood", None, "")
    )
    store.set_reaction(second, Reaction.NONE)
    store.close()


def build_api(tmp_path: Path, *, with_db: bool = True, reader: Any = None) -> DashboardApi:
    data = tmp_path / "data"
    data.mkdir()
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[data]\ndir = "{data.as_posix()}"\n[aliases]\napi_key = "sk-SEGREDO"\n',
        encoding="utf-8",
    )
    if with_db:
        seed(data / "coppermind.db")
    view = config_view(config_path)
    return DashboardApi(
        view=view,
        config_path=config_path,
        reader=reader or CoppermindReader(data / "coppermind.db"),
        dev=DevSources(tmp_path, git=broken_git),
        sampler=ResourceSampler(FakeProbe(), own_pid=999),
        catalog=lambda: FakeCatalog(["WhatsApp", "Google Chrome"]).entries(),
        clock=lambda: NOW,
        wall=lambda: 1000.0,
    )
