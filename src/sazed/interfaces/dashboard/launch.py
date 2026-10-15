"""`sazed painel`: build the dashboard from config.toml and serve it until Ctrl+C."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path

from sazed.interfaces.dashboard.api import DashboardApi
from sazed.interfaces.dashboard.server import HOST, make_server
from sazed.interfaces.dashboard.sources import DevSources, PsutilProbe, ResourceSampler
from sazed.runtime.config import DEFAULT_CONFIG_PATH, PROJECT_ROOT, ConfigError
from sazed.runtime.insight import (
    ConfigView,
    CoppermindReader,
    config_view,
    coppermind_path,
    default_catalog,
)
from sazed.runtime.logs import setup_logging

log = logging.getLogger(__name__)


def build_api(view: ConfigView, config_path: Path, root: Path) -> DashboardApi:
    return DashboardApi(
        view=view,
        config_path=config_path,
        reader=CoppermindReader(coppermind_path(view.config)),
        dev=DevSources(root),
        sampler=ResourceSampler(PsutilProbe(), own_pid=os.getpid()),
        catalog=default_catalog(),
        clock=datetime.now,  # the dashboard's only clock; everything below takes `now`
        wall=time.time,
    )


def say(text: str) -> None:
    """Flushed: with a piped stdout (a launcher, a log), unflushed text never shows up."""
    print(text, flush=True)


def _serve(server: ThreadingHTTPServer) -> None:
    server.serve_forever()


def run(
    config_path: Path | None,
    *,
    port: int,
    root: Path | None,
    out: Callable[[str], None] = say,
    serve: Callable[[ThreadingHTTPServer], None] = _serve,
) -> int:
    path = config_path or DEFAULT_CONFIG_PATH
    try:
        view = config_view(path)
    except ConfigError as err:
        out(str(err))
        return 2
    config = view.config
    setup_logging(config.data.dir / "logs", debug=config.logging.debug, filename="painel.log")
    api = build_api(view, path, root or PROJECT_ROOT)
    try:
        server = make_server(api, port)
    except OSError:
        log.exception("could not bind the dashboard to port %s", port)
        out(
            f"Não consegui abrir a porta {port}; talvez já esteja em uso. "
            "Escolha outra com --porta."
        )
        return 2
    out(
        f"Painel de Sazed em http://{HOST}:{server.server_address[1]}/ "
        "(somente leitura). Ctrl+C para encerrar."
    )
    try:
        serve(server)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    out("Painel encerrado.")
    return 0
