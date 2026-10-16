"""Writes over HTTP: POST only, token, Origin, size. Reads stay read-only, never load the model."""

import http.client
import json
import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from sazed.interfaces.dashboard.server import HOST, MAX_BODY, make_server
from sazed.interfaces.dashboard.writes import WRITE_ROUTES, WriteApi
from sazed.runtime.config import Config, DataConfig
from sazed.runtime.editing import Editor
from support.dashboard import ENDPOINTS, build_api
from support.editing import NAMES, AppFactory

TOKEN = "token-de-teste-0123456789"
T = datetime(2026, 10, 15, 12, 0)


@dataclass
class Served:
    port: int
    factory: AppFactory
    data: Path

    @property
    def origin(self) -> str:
        return f"http://{HOST}:{self.port}"


@pytest.fixture
def served(tmp_path: Path) -> Iterator[Served]:
    api = build_api(tmp_path, with_db=False)
    factory = AppFactory()
    data = tmp_path / "data"
    editor = Editor(
        Config(data=DataConfig(dir=data)),
        make_app=factory,
        app_names=lambda: NAMES,
        clock=lambda: T,
    )
    writes = WriteApi(editor)
    server = make_server(api, port=0, writes=writes, token=TOKEN)
    thread = threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True)
    thread.start()
    yield Served(server.server_address[1], factory, data)
    server.shutdown()
    server.server_close()
    writes.close()


def send(
    s: Served,
    path: str,
    body: Any = None,
    *,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    raw: bytes | None = None,
) -> tuple[int, dict[str, Any]]:
    payload = raw if raw is not None else json.dumps(body or {}).encode()
    base = {
        "Content-Type": "application/json",
        "X-Sazed-Token": TOKEN,
        "Origin": s.origin,
        "Content-Length": str(len(payload)),
    }
    for key, value in (headers or {}).items():
        if value is None:
            base.pop(key, None)
        else:
            base[key] = value
    conn = http.client.HTTPConnection(HOST, s.port, timeout=10)
    conn.putrequest(method, path, skip_accept_encoding=True)
    for key, value in base.items():
        conn.putheader(key, value)
    conn.endheaders(payload if method == "POST" else None)
    response = conn.getresponse()
    text = response.read()
    conn.close()
    return response.status, json.loads(text) if text else {}


def aliases_on_disk(s: Served) -> list[tuple[object, ...]]:
    path = s.data / "coppermind.db"
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    try:
        return list(conn.execute("SELECT alias, value FROM slot_aliases").fetchall())
    finally:
        conn.close()


ADD = {"alias": "zap", "target": "WhatsApp"}


def test_a_valid_write_is_saved(served: Served) -> None:
    status, payload = send(served, "/api/write/alias/add", ADD)
    assert (status, payload["ok"]) == (200, True)
    assert aliases_on_disk(served) == [("zap", "WhatsApp")]


@pytest.mark.parametrize("token", [None, "", "errado", TOKEN + "x"])
def test_the_token_is_required(served: Served, token: str | None) -> None:
    status, payload = send(served, "/api/write/alias/add", ADD, headers={"X-Sazed-Token": token})
    assert status == 403
    assert payload["error"].startswith("Acesso negado")
    assert aliases_on_disk(served) == []


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "http://evil.example"},
        {"Origin": "http://127.0.0.1:1"},
        {"Origin": "null"},
        {"Origin": None, "Referer": None},
        {"Origin": None, "Referer": "http://evil.example/"},
        {"Origin": None, "Referer": "http://127.0.0.1:1/"},
    ],
)
def test_the_origin_must_be_the_dashboard(served: Served, headers: dict[str, str]) -> None:
    status, _ = send(served, "/api/write/alias/add", ADD, headers=headers)
    assert status == 403
    assert aliases_on_disk(served) == []


def test_a_same_origin_referer_is_enough_without_origin(served: Served) -> None:
    headers = {"Origin": None, "Referer": f"{served.origin}/#coppermind"}
    status, _ = send(served, "/api/write/alias/add", ADD, headers=headers)  # type: ignore[arg-type]
    assert status == 200


def test_only_json_bodies(served: Served) -> None:
    status, payload = send(
        served, "/api/write/alias/add", ADD, headers={"Content-Type": "text/plain"}
    )
    assert status == 415 and "JSON" in payload["error"]


def test_body_size_is_limited(served: Served) -> None:
    big = json.dumps({"alias": "z", "target": "x" * MAX_BODY}).encode()
    status, payload = send(served, "/api/write/alias/add", raw=big)
    assert status == 413 and "grande" in payload["error"]
    assert aliases_on_disk(served) == []


def test_missing_length_is_refused(served: Served) -> None:
    status, _ = send(served, "/api/write/alias/add", ADD, headers={"Content-Length": None})
    assert status == 411


@pytest.mark.parametrize("path", sorted(WRITE_ROUTES))
def test_writes_are_post_only(served: Served, path: str) -> None:
    status, _ = send(served, path, method="GET")
    assert status == 405


@pytest.mark.parametrize("path", ENDPOINTS)
def test_reads_refuse_post(served: Served, path: str) -> None:
    status, _ = send(served, path, {})
    assert status == 405


def test_reads_never_load_the_model(served: Served) -> None:
    send(served, "/api/write/alias/add", ADD)  # the database now exists
    for path in [*ENDPOINTS, "/api/editor", "/"]:
        conn = http.client.HTTPConnection(HOST, served.port, timeout=10)
        conn.request("GET", path)
        assert conn.getresponse().status == 200, path
        conn.close()
    assert served.factory.calls == 0


def test_page_carries_the_token(served: Served) -> None:
    conn = http.client.HTTPConnection(HOST, served.port, timeout=10)
    conn.request("GET", "/")
    body = conn.getresponse().read().decode("utf-8")
    conn.close()
    assert f'<meta name="sazed-token" content="{TOKEN}">' in body
    assert "__SAZED_TOKEN__" not in body


def test_editor_status_endpoint(served: Served) -> None:
    conn = http.client.HTTPConnection(HOST, served.port, timeout=10)
    conn.request("GET", "/api/editor")
    payload = json.loads(conn.getresponse().read())
    conn.close()
    assert payload == {"available": True, "writable": True, "state": "idle", "message": None}


def test_reads_show_notes_after_a_write(served: Served) -> None:
    send(served, "/api/write/alias/add", ADD)
    status, payload = send(
        served, "/api/write/note/add", {"target": "alias", "target_id": 1, "text": "do zap"}
    )
    assert payload["ok"] is True
    conn = http.client.HTTPConnection(HOST, served.port, timeout=10)
    conn.request("GET", "/api/aliases")
    aliases = json.loads(conn.getresponse().read())
    conn.close()
    (alias,) = aliases["items"]
    assert [n["text"] for n in alias["notes"]] == ["do zap"]
