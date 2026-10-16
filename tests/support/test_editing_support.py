from pathlib import Path

import pytest

from sazed.runtime.config import Config, DataConfig
from support.editing import NAMES, AppFactory


def test_factory_counts_and_builds_an_app_over_the_data_dir(tmp_path: Path) -> None:
    factory = AppFactory()
    app = factory(Config(data=DataConfig(dir=tmp_path)))
    assert factory.calls == 1 and factory.app is app
    assert (tmp_path / "coppermind.db").exists()
    apps = next(s for s in app.skills if s.id == "apps")
    assert apps.intents[0].id == "abrir_app"
    assert NAMES == ["WhatsApp", "Discord"]
    app.close()


def test_factory_raises_the_configured_error(tmp_path: Path) -> None:
    factory = AppFactory(RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        factory(Config(data=DataConfig(dir=tmp_path)))
    assert factory.calls == 1
