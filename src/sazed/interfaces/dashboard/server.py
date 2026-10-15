"""Thin HTTP layer: loopback only, GET only, static page plus the JSON endpoints in `api`."""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from sazed.interfaces.dashboard.api import DashboardApi

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
"""Never configurable: the dashboard shows private data and has no authentication."""

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self';"
        " connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _static(name: str) -> bytes:
    return resources.files("sazed.interfaces.dashboard").joinpath("static", name).read_bytes()


class DashboardHandler(BaseHTTPRequestHandler):
    api: DashboardApi
    server_version = "SazedPainel"
    sys_version = ""

    def __getattr__(self, name: str) -> Any:
        # BaseHTTPRequestHandler dispatches verb X to `do_X`; every verb but GET lands here.
        if name.startswith("do_"):
            return self._refuse_method
        raise AttributeError(name)

    def _refuse_method(self) -> None:
        self._send_json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"error": "O painel é somente leitura: apenas GET é aceito."},
            extra={"Allow": "GET"},
        )

    def _host_allowed(self) -> bool:
        address = self.server.server_address
        port = address[1] if isinstance(address, tuple) else None
        host = self.headers.get("Host", "")
        return host in {f"{HOST}:{port}", f"localhost:{port}"}

    def do_GET(self) -> None:  # noqa: N802 - the name is fixed by http.server
        if not self._host_allowed():  # blocks DNS rebinding from a web page
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Acesso negado."})
            return
        url = urlsplit(self.path)
        if url.path in STATIC:
            name, content_type = STATIC[url.path]
            self._send(HTTPStatus.OK, _static(name), content_type)
            return
        query = dict(parse_qsl(url.query, keep_blank_values=True))
        status, payload = self.api.handle(url.path, query)
        self._send_json(HTTPStatus(status), payload)

    def _send_json(
        self, status: HTTPStatus, payload: dict[str, Any], extra: dict[str, str] | None = None
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", extra)

    def _send(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        log.debug("%s - %s", self.address_string(), format % args)


def make_server(api: DashboardApi, port: int) -> ThreadingHTTPServer:
    handler = type("BoundDashboardHandler", (DashboardHandler,), {"api": api})
    server = ThreadingHTTPServer((HOST, port), handler)
    server.daemon_threads = True
    return server
