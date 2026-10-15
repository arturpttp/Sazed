import json
import logging
import socket
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from sazed.interfaces.dashboard.launch import run


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


def write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(f'[data]\ndir = "{(tmp_path / "data").as_posix()}"\n', encoding="utf-8")
    return path


def test_invalid_config_stops_with_the_pt_br_message(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[nlu]\nt_exec = 'alto'\n", encoding="utf-8")
    said: list[str] = []
    assert run(path, port=0, root=tmp_path, out=said.append) == 2
    assert said[0].startswith("Configuração inválida")


def test_serves_until_stopped_and_creates_no_database(tmp_path: Path) -> None:
    said: list[str] = []
    answers: list[dict[str, object]] = []

    def serve(server: ThreadingHTTPServer) -> None:
        import threading

        thread = threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}/api/episodes"
        with urllib.request.urlopen(url, timeout=5) as response:
            answers.append(json.loads(response.read()))
        server.shutdown()
        raise KeyboardInterrupt

    assert run(write_config(tmp_path), port=0, root=tmp_path, out=said.append, serve=serve) == 0
    assert said[0].startswith("Painel de Sazed em http://127.0.0.1:")
    assert said[-1] == "Painel encerrado."
    assert answers[0]["available"] is False
    assert not (tmp_path / "data" / "coppermind.db").exists()
    assert (tmp_path / "data" / "logs" / "painel.log").exists()


def test_a_busy_port_is_a_pt_br_message(tmp_path: Path) -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        said: list[str] = []
        assert run(write_config(tmp_path), port=port, root=tmp_path, out=said.append) == 2
    assert said == [
        f"Não consegui abrir a porta {port}; talvez já esteja em uso. Escolha outra com --porta."
    ]
