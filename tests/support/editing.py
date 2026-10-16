"""Build the editor's app from fakes, counting how often the "model" was loaded."""

from random import Random

from fakes.clock import ManualClock
from fakes.embedder import HashingEmbedder
from fakes.ports import fake_pc_ports
from sazed.runtime.config import Config
from sazed.runtime.wiring import SazedApp, build_app

NAMES = ["WhatsApp", "Discord"]


class AppFactory:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = 0
        self.error = error
        self.app: SazedApp | None = None

    def __call__(self, config: Config) -> SazedApp:
        self.calls += 1
        if self.error is not None:
            raise self.error
        self.app = build_app(
            config,
            embedder=HashingEmbedder(),
            ports=fake_pc_ports(NAMES),
            clock=ManualClock(),
            rng=Random(0),
        )
        return self.app
