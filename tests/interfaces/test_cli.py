import io
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from random import Random

import pytest

from fakes.clock import ManualClock
from fakes.embedder import HashingEmbedder
from fakes.ports import FakeAudio, fake_pc_ports
from sazed.core.coppermind import Episode, NewAlias
from sazed.interfaces.cli.main import main
from sazed.runtime.config import Config, DataConfig
from sazed.runtime.wiring import SazedApp, StartupError, build_app

T0 = datetime(2026, 10, 14, 12, 0)


@pytest.fixture
def audio() -> FakeAudio:
    return FakeAudio(volume=50)


Boot = Callable[[], SazedApp]


@pytest.fixture
def boot(tmp_path: Path, audio: FakeAudio) -> Boot:
    """A fresh app over the same data dir: `main` closes the app it was given, as it should."""

    def make() -> SazedApp:
        return build_app(
            Config(data=DataConfig(dir=tmp_path)),
            embedder=HashingEmbedder(),
            ports=fake_pc_ports(["WhatsApp", "Google Chrome"], audio=audio),
            clock=ManualClock(),
            rng=Random(0),
        )

    return make


@pytest.fixture
def app(boot: Boot) -> SazedApp:
    """Used to set up and re-query the store, through its own connection."""
    return boot()


def run(boot: Boot, argv: list[str], stdin: str = "") -> int:
    return main(argv, build=lambda _path: boot(), stdin=io.StringIO(stdin))


def test_repl_greets_executes_and_says_goodbye(
    boot: Boot, app: SazedApp, audio: FakeAudio, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(boot, [], "volume em 30\nsair\n") == 0
    out = capsys.readouterr().out
    assert audio.volume == 30
    assert "30%" in out
    assert "Até logo, Mestre Artur." in out


def test_repl_ends_on_end_of_input(
    boot: Boot, app: SazedApp, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(boot, [], "") == 0
    assert "Até logo" in capsys.readouterr().out


def test_learned_list_and_forget(
    boot: Boot, app: SazedApp, capsys: pytest.CaptureFixture[str]
) -> None:
    app.store.learn([], [NewAlias("app", "zap", "WhatsApp")], T0)
    assert run(boot, ["aprendizado"]) == 0
    out = capsys.readouterr().out
    assert "a1" in out and "apelido" in out and "zap" in out and "WhatsApp" in out
    assert run(boot, ["aprendizado", "--esquecer", "a1"]) == 0
    assert app.store.aliases() == []


def test_forgetting_an_unknown_ref_is_explained(
    boot: Boot, app: SazedApp, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(boot, ["aprendizado", "--esquecer", "a9"]) == 1
    assert "a9" in capsys.readouterr().out


def test_review_lists_and_labels(
    boot: Boot, app: SazedApp, capsys: pytest.CaptureFixture[str]
) -> None:
    episode_id = app.store.record_episode(
        Episode("liga o navegador", T0, (), {}, "NotUnderstood", None, "")
    )
    assert run(boot, ["revisar"]) == 0
    assert "liga o navegador" in capsys.readouterr().out
    assert run(boot, ["revisar", "--rotular", str(episode_id), "abrir_app"]) == 0
    assert [e.intent_id for e in app.store.examples()] == ["abrir_app"]


def test_review_rejects_an_unknown_intent(
    boot: Boot, app: SazedApp, capsys: pytest.CaptureFixture[str]
) -> None:
    episode_id = app.store.record_episode(Episode("x", T0, (), {}, "NotUnderstood", None, ""))
    assert run(boot, ["revisar", "--rotular", str(episode_id), "voar"]) == 1
    assert "abrir_app" in capsys.readouterr().out  # lists the valid intents


def test_startup_error_is_shown_without_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    def broken(_path: Path | None) -> SazedApp:
        raise StartupError(
            "Configuração inválida em config.toml:\n- nlu.t_exec: deve ser no máximo 1"
        )

    assert main([], build=broken, stdin=io.StringIO("")) == 2
    out = capsys.readouterr()
    assert "deve ser no máximo 1" in out.out
    assert "Traceback" not in out.out + out.err


def test_help_is_in_pt_br(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--ajuda"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert "uso:" in out and "aprendizado" in out
    for english in ("usage:", "options:", "show this help", "positional arguments"):
        assert english not in out


def test_bad_arguments_are_explained_in_pt_br(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["voar"])
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert "--ajuda" in captured.out + captured.err
    assert "invalid choice" not in captured.out + captured.err


def test_painel_starts_the_dashboard_without_loading_sazed(tmp_path: Path) -> None:
    calls: list[tuple[object, ...]] = []

    def dashboard(config: Path | None, *, port: int, root: Path | None) -> int:
        calls.append((config, port, root))
        return 0

    def never_build(config: Path | None) -> SazedApp:
        raise AssertionError("the dashboard must not load the model or open the coppermind")

    assert main(["painel"], build=never_build, dashboard=dashboard) == 0
    assert (
        main(
            ["--config", "c.toml", "painel", "--porta", "9000", "--raiz", str(tmp_path)],
            build=never_build,
            dashboard=dashboard,
        )
        == 0
    )
    assert calls == [(None, 8765, None), (Path("c.toml"), 9000, tmp_path)]


@pytest.mark.parametrize("port", ["abc", "70000", "-1"])
def test_painel_rejects_a_bad_port(port: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["painel", "--porta", port], dashboard=lambda *a, **k: 0)
    assert exited.value.code == 2
    assert "Comando não reconhecido" in capsys.readouterr().err


def test_painel_help_is_pt_br(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["painel", "--ajuda"])
    out = capsys.readouterr().out
    assert "porta" in out and "painel" in out.lower()


def test_review_explains_a_conflict_and_accepts_force(
    boot: Boot, app: SazedApp, capsys: pytest.CaptureFixture[str]
) -> None:
    ep = Episode("abre o chrome", T0, (), {}, "Execute", None, "")
    episode_id = app.store.record_episode(ep)
    assert run(boot, ["revisar", "--rotular", str(episode_id), "fechar_app"]) == 1
    assert "--forcar" in capsys.readouterr().out
    assert run(boot, ["revisar", "--rotular", str(episode_id), "fechar_app", "--forcar"]) == 0
    assert [e.intent_id for e in app.store.examples()] == ["fechar_app"]
