"""Load the full app (real model and adapters) and report startup time and memory.

Uses a temporary data directory, so the real coppermind is never opened.
"""

import tempfile
import time
from pathlib import Path

import psutil

from sazed.runtime.config import Config, DataConfig
from sazed.runtime.wiring import build_default_app


def main() -> None:
    process = psutil.Process()
    with tempfile.TemporaryDirectory() as tmp:
        before = process.memory_info().rss
        start = time.perf_counter()
        app = build_default_app(Config(data=DataConfig(dir=Path(tmp))))
        loaded = time.perf_counter() - start
        rss = process.memory_info().rss
        examples = sum(len(spec.examples) for skill in app.skills for spec in skill.intents)
        print(
            f"skills {len(app.skills)}, seed examples {examples}; startup {loaded:.2f} s; "
            f"RSS +{(rss - before) / 2**20:.0f} MB (process {rss / 2**20:.0f} MB)"
        )
        app.close()


if __name__ == "__main__":
    main()
