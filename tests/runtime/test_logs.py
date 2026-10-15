import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from sazed.runtime.logs import setup_logging


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in root.handlers:
        handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


def test_logging_goes_to_the_file(tmp_path: Path) -> None:
    path = setup_logging(tmp_path / "logs", debug=False)
    logging.getLogger("sazed.test").error("algo quebrou: %s", "detalhe interno")
    assert "detalhe interno" in path.read_text(encoding="utf-8")


def test_logging_never_writes_to_the_console(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup_logging(tmp_path, debug=False)
    try:
        raise RuntimeError("stack trace secreto")
    except RuntimeError:
        logging.getLogger("sazed.test").exception("falhou")
    captured = capsys.readouterr()
    assert "secreto" not in captured.out + captured.err


def test_debug_only_when_enabled(tmp_path: Path) -> None:
    quiet = setup_logging(tmp_path / "a", debug=False)
    logging.getLogger("sazed.test").debug("ranking detalhado")
    assert "ranking detalhado" not in quiet.read_text(encoding="utf-8")
    loud = setup_logging(tmp_path / "b", debug=True)
    logging.getLogger("sazed.test").debug("ranking detalhado")
    assert "ranking detalhado" in loud.read_text(encoding="utf-8")


def test_a_second_process_can_log_to_its_own_file(tmp_path: Path) -> None:
    path = setup_logging(tmp_path, debug=False, filename="painel.log")
    logging.getLogger("sazed.test").warning("do painel")
    assert path == tmp_path / "painel.log"
    assert "do painel" in path.read_text(encoding="utf-8")
    assert not (tmp_path / "sazed.log").exists()
