"""Logs go to a rotating file only. Nothing internal ever reaches the console."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path, *, debug: bool, filename: str = "sazed.log") -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / filename
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
        old.close()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    logging.captureWarnings(True)
    return path
