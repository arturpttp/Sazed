"""Thin HTTP layer: loopback only. GET reads (static page plus `api`); POST writes (`writes`),
and only with the per-launch token, a same-origin Origin/Referer and a small JSON body."""

from __future__ import annotations

import hmac
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from sazed.interfaces.dashboard.api import DashboardApi
from sazed.interfaces.dashboard.writes import WRITE_ROUTES, WriteApi

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
"""Never configurable: the dashboard shows private data and has no login."""
MAX_BODY = 16 * 1024
TOKEN_HEADER = "X-Sazed-Token"
TOKEN_PLACEHOLDER = b"__SAZED_TOKEN__"

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
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
}
DENIED = "Acesso negado."


def _static(name: str) -> bytes:
    return resources.files("sazed.interfaces.dashboard").joinpath("static", name).read_bytes()


class DashboardHandler(BaseHTTPRequestHandler):
    api: DashboardApi
    writes: WriteApi | None
    token: str
    server_version = "SazedPainel"
    sys_version = ""

    def __getattr__(self, name: str) -> Any:
        # BaseHTTPRequestHandler dispatches verb X to `do_X`; every verb but GET and POST
        # lands here, so a new verb can never be served by accident.
        if name.startswith("do_"):
            return self._refuse_method
        raise AttributeError(name)

    def _refuse_method(self, allow: str | None = None) -> None:
        if allow is None:
            allow = "POST" if urlsplit(self.path).path in WRITE_ROUTES else "GET"
        self._send_json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"error": "Método não aceito: o painel só lê com GET e só grava com POST."},
            extra={"Allow": allow},
        )

    def _port(self) -> int | None:
        address = self.server.server_address
        return address[1] if isinstance(address, tuple) else None

    def _origins(self) -> set[str]:
        return {f"http://{HOST}:{self._port()}", f"http://localhost:{self._port()}"}

    def _host_allowed(self) -> bool:
        host = self.headers.get("Host", "")
        return host in {f"{HOST}:{self._port()}", f"localhost:{self._port()}"}

    # reads ---------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - the name is fixed by http.server
        if not self._host_allowed():  # blocks DNS rebinding from a web page
            self._send_json(HTTPStatus.FORBIDDEN, {"error": DENIED})
            return
        url = urlsplit(self.path)
        if url.path in WRITE_ROUTES:
            self._refuse_method(allow="POST")
            return
        if url.path in STATIC:
            name, content_type = STATIC[url.path]
            body = _static(name)
            if url.path == "/":
                body = body.replace(TOKEN_PLACEHOLDER, self.token.encode("ascii"))
            self._send(HTTPStatus.OK, body, content_type)
            return
        if url.path == "/api/editor":
            status = self.writes.status() if self.writes else {"state": "off", "message": None}
            self._send_json(
                HTTPStatus.OK, {"available": True, "writable": self.writes is not None, **status}
            )
            return
        query = dict(parse_qsl(url.query, keep_blank_values=True))
        status_code, payload = self.api.handle(url.path, query)
        self._send_json(HTTPStatus(status_code), payload)

    # writes --------------------------------------------------------------------

    def _write_refusal(self) -> tuple[HTTPStatus, str] | None:
        """Every check that must pass before a write body is even read."""
        if not self._host_allowed():
            return HTTPStatus.FORBIDDEN, DENIED
        token = self.headers.get(TOKEN_HEADER, "")
        if not hmac.compare_digest(token.encode("utf-8"), self.token.encode("utf-8")):
            return HTTPStatus.FORBIDDEN, f"{DENIED} Recarregue a página do painel."
        origin = self.headers.get("Origin")
        if origin is not None:
            if origin not in self._origins():
                return HTTPStatus.FORBIDDEN, DENIED
        else:
            referer = self.headers.get("Referer", "")
            if not any(referer.startswith(f"{o}/") for o in self._origins()):
                return HTTPStatus.FORBIDDEN, DENIED
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type != "application/json":
            return HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "O painel só aceita corpo em JSON."
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit():
            return HTTPStatus.LENGTH_REQUIRED, "Falta o tamanho do corpo da requisição."
        if int(length) > MAX_BODY:
            return HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "O corpo da requisição é grande demais."
        return None

    def do_POST(self) -> None:  # noqa: N802 - the name is fixed by http.server
        path = urlsplit(self.path).path
        if self.writes is None or path not in WRITE_ROUTES:
            if path in STATIC or path in DashboardApi.ROUTES or path == "/api/editor":
                self._refuse_method(allow="GET")
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Este endereço não existe."})
            return
        refusal = self._write_refusal()
        if refusal is not None:
            status, message = refusal
            log.warning("write refused (%s) for %s", status.value, path)
            self.close_connection = True  # the unread body must not be parsed as a request
            self._send_json(status, {"error": message})
            return
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        status_code, payload = self.writes.handle(path, raw)
        self._send_json(HTTPStatus(status_code), payload)

    # output --------------------------------------------------------------------

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


def make_server(
    api: DashboardApi, port: int, *, writes: WriteApi | None = None, token: str = ""
) -> ThreadingHTTPServer:
    """Without `writes` the dashboard is read-only and every POST is refused."""
    if writes is not None and len(token) < 16:
        raise ValueError("a writable dashboard needs a random token of at least 16 characters")
    attrs = {"api": api, "writes": writes, "token": token}
    handler = type("BoundDashboardHandler", (DashboardHandler,), attrs)
    server = ThreadingHTTPServer((HOST, port), handler)
    server.daemon_threads = True
    return server
