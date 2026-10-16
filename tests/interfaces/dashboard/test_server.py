import http.client
import json
import re
import threading
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from fakes.ports import FakeCatalog
from fakes.system import FakeProbe, broken_git
from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.coppermind import Episode, NewAlias, NewExample, Reaction
from sazed.core.types import IntentScore
from sazed.interfaces.dashboard.api import DashboardApi
from sazed.interfaces.dashboard.server import HOST, DashboardHandler, make_server
from sazed.interfaces.dashboard.sources import DevSources, ResourceSampler
from sazed.runtime.insight import CoppermindReader, config_view, skills_for_listing

NOW = datetime(2026, 10, 15, 12, 0)
SVG_NAMESPACE = b"http://www.w3.org/2000/svg"


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


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[int, DashboardApi]]:
    api = build_api(tmp_path)
    server = make_server(api, port=0)
    thread = threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True)
    thread.start()
    yield server.server_address[1], api
    server.shutdown()
    server.server_close()


def request(
    port: int, path: str, method: str = "GET", host: str | None = None
) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection(HOST, port, timeout=5)
    headers = {"Host": host} if host else {}
    conn.request(method, path, headers=headers)
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response.status, dict(response.getheaders()), body


def get_json(port: int, path: str) -> Any:
    status, _, body = request(port, path)
    assert status == 200, body
    return json.loads(body)


def test_binds_to_loopback_only(tmp_path: Path) -> None:
    server = make_server(build_api(tmp_path), port=0)
    try:
        assert HOST == "127.0.0.1"
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


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


def test_routes_list_is_the_one_tested() -> None:
    assert sorted(DashboardApi.ROUTES) == sorted(ENDPOINTS)


@pytest.mark.parametrize("path", ENDPOINTS)
def test_every_endpoint_answers_json(served: tuple[int, DashboardApi], path: str) -> None:
    status, headers, body = request(served[0], path)
    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    json.loads(body)


@pytest.mark.parametrize("path", ["/", "/app.js", "/style.css"])
def test_static_files(served: tuple[int, DashboardApi], path: str) -> None:
    status, headers, body = request(served[0], path)
    assert status == 200
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    # Offline: no URL to anywhere. The SVG namespace is an identifier, never fetched.
    urls = re.findall(rb"(?:https?:)?//[\w.-]+\.[a-z]{2,}[^\s\"')]*", body)
    assert [u for u in urls if u != SVG_NAMESPACE] == []


def test_page_is_pt_br(served: tuple[int, DashboardApi]) -> None:
    _, _, body = request(served[0], "/")
    assert b'lang="pt-BR"' in body


@pytest.mark.parametrize(
    "method", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "TRACE", "PROPFIND"]
)
def test_only_get_is_served(served: tuple[int, DashboardApi], method: str) -> None:
    status, headers, _ = request(served[0], "/api/episodes", method=method)
    assert status == 405
    assert headers["Allow"] == "GET"


def test_every_handler_method_other_than_get_refuses() -> None:
    names = {n for n in dir(DashboardHandler) if n.startswith("do_")}
    assert names == {"do_GET"}  # any other verb goes through __getattr__ → 405


def test_unknown_path_is_404(served: tuple[int, DashboardApi]) -> None:
    status, _, body = request(served[0], "/api/nada")
    assert status == 404
    assert "não existe" in json.loads(body)["error"]


@pytest.mark.parametrize("path", ["/../pyproject.toml", "/static/../server.py", "/server.py"])
def test_no_path_traversal(served: tuple[int, DashboardApi], path: str) -> None:
    status, _, body = request(served[0], path)
    assert status == 404
    assert b"import" not in body


@pytest.mark.parametrize("host", ["evil.example:80", "192.168.0.10"])
def test_foreign_host_header_is_refused(served: tuple[int, DashboardApi], host: str) -> None:
    status, _, _ = request(served[0], "/api/overview", host=host)
    assert status == 403


def test_localhost_host_header_is_accepted(served: tuple[int, DashboardApi]) -> None:
    status, _, _ = request(served[0], "/api/overview", host=f"localhost:{served[0]}")
    assert status == 200


def test_bad_query_is_a_pt_br_400(served: tuple[int, DashboardApi]) -> None:
    status, _, body = request(served[0], "/api/episodes?limit=muitos")
    assert status == 400
    assert json.loads(body)["error"] == "Parâmetro inválido: 'limit' deve ser um número inteiro."
    status, _, body = request(served[0], "/api/episodes?limit=9999")
    assert status == 400
    assert "entre 1 e 200" in json.loads(body)["error"]


def test_episodes_explain_the_reasoning(served: tuple[int, DashboardApi]) -> None:
    data = get_json(served[0], "/api/episodes")
    assert data["available"] is True and data["total"] == 2
    newest, oldest = data["items"]
    assert newest["decision_label"] == "não entendido"
    assert newest["failed"] is True
    assert "abaixo do limiar de confirmação" in newest["reason"]
    assert oldest["ranking"][0] == {"intent": "abrir_app", "score": 0.97}
    assert oldest["slots"] == {"app": "WhatsApp"}
    assert oldest["learned"] == ["exemplo 'abre o zap' → abrir_app", "apelido 'zap' → WhatsApp"]
    filtered = get_json(served[0], "/api/episodes?decision=Execute&q=zap")
    assert [e["utterance"] for e in filtered["items"]] == ["abre o zap"]


def test_learning_series(served: tuple[int, DashboardApi]) -> None:
    data = get_json(served[0], "/api/learning?days=7")
    assert len(data["activity"]) == 7
    assert data["activity"][-1]["day"] == "2026-10-15"
    assert data["activity"][-1]["executed"] == 1
    assert data["learned"][-1]["total_examples"] == 1


def test_capabilities_redact_and_list_skills(served: tuple[int, DashboardApi]) -> None:
    status, _, body = request(served[0], "/api/capabilities")
    assert status == 200
    assert b"sk-SEGREDO" not in body
    data = json.loads(body)
    rows = {r["key"]: r for r in data["config"]["rows"]}
    assert rows["aliases.api_key"]["value"] == "••• (oculto)"
    assert rows["aliases.api_key"]["origin"] == "arquivo"
    assert rows["nlu.t_exec"]["origin"] == "padrão"
    assert {s["id"] for s in data["skills"]} == {s.id for s in skills_for_listing()}
    assert {p["name"] for p in data["ports"]} >= {"AppCatalog"}


def test_catalog_search(served: tuple[int, DashboardApi]) -> None:
    data = get_json(served[0], "/api/catalog?q=chrome")
    assert [e["name"] for e in data["items"]] == ["Google Chrome"]
    assert data["total"] == 2


def test_overview(served: tuple[int, DashboardApi]) -> None:
    data = get_json(served[0], "/api/overview")
    assert data["coppermind"]["totals"]["commands"] == 2
    assert data["coppermind"]["learned"] == {"examples": 1, "aliases": 1}
    assert data["resources"]["sazed"]["running"] is True
    assert data["dev"]["plan"] is None
    assert len(data["recent"]) == 2


def test_missing_database_is_an_empty_state_and_is_not_created(tmp_path: Path) -> None:
    api = build_api(tmp_path, with_db=False)
    for path in ENDPOINTS:
        status, payload = api.handle(path, {})
        assert status == 200, path
        json.dumps(payload)
    status, payload = api.handle("/api/episodes", {})
    assert payload["available"] is False
    assert payload["message"].startswith("A mente de cobre ainda não existe")
    assert not (tmp_path / "data" / "coppermind.db").exists()


class ExplodingReader:
    def __getattr__(self, name: str) -> Any:
        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("SELECT secret FROM episodes -- internal detail")

        return boom


def test_an_unexpected_failure_never_leaks(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    api = build_api(tmp_path, reader=ExplodingReader())
    server = make_server(api, port=0)
    thread = threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True)
    thread.start()
    try:
        status, _, body = request(server.server_address[1], "/api/episodes")
        assert status == 500
        assert b"SELECT" not in body and b"Traceback" not in body
        assert json.loads(body)["error"].startswith("Peço desculpas")
        status, _, _ = request(server.server_address[1], "/api/resources")
        assert status == 200  # the other panels keep working
    finally:
        server.shutdown()
        server.server_close()
    assert "SELECT secret" in caplog.text  # logged for the developer instead
