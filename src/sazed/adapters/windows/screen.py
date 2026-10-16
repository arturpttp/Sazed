"""Screenshots with Pillow, and the snip overlay."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sazed.skills.pc.fileops import free_name

log = logging.getLogger(__name__)
FOLDERID_SCREENSHOTS = "{b7bede81-df94-4682-a7d8-57a52620b86f}"


def screenshots_dir() -> Path:
    try:
        import pywintypes
        from win32com.shell import shell  # type: ignore[import-untyped]

        return Path(shell.SHGetKnownFolderPath(pywintypes.IID(FOLDERID_SCREENSHOTS), 0, None))
    except Exception:
        log.warning("Screenshots known folder unavailable; using Pictures", exc_info=True)
        return Path.home() / "Pictures" / "Screenshots"


class WindowsScreen:
    def __init__(self, folder: Path | None = None) -> None:
        self._folder = folder

    def capture(self, file_name: str) -> str:
        from PIL import ImageGrab

        folder = self._folder or screenshots_dir()
        folder.mkdir(parents=True, exist_ok=True)
        name = free_name(file_name, {p.name for p in folder.iterdir()})
        ImageGrab.grab(all_screens=True).save(folder / name)
        return name

    def open_snip(self) -> None:
        os.startfile("ms-screenclip:")  # type: ignore[attr-defined]  # Windows only
