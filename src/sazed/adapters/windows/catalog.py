"""Installed apps from Start Menu shortcuts (.lnk). Store (UWP) apps are not covered."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from sazed.skills.pc.apps import AppEntry

log = logging.getLogger(__name__)

EXCLUDED_WORDS = ("uninstall", "desinstalar", "remover", "readme", "leia-me", "help", "ajuda")
_PROGRAMS = Path("Microsoft") / "Windows" / "Start Menu" / "Programs"


def start_menu_dirs() -> list[Path]:
    roots = [os.environ.get("APPDATA"), os.environ.get("PROGRAMDATA")]
    return [Path(r) / _PROGRAMS for r in roots if r]


def build_entries(shortcuts: Iterable[tuple[str, str, str]]) -> list[AppEntry]:
    """(display name, target, shortcut path) → entries. The first of duplicate names wins."""
    seen: set[str] = set()
    entries: list[AppEntry] = []
    for name, target, shortcut in shortcuts:
        key = name.strip().lower()
        if any(word in key for word in EXCLUDED_WORDS):
            continue
        if not target.lower().endswith(".exe"):
            continue
        if key in seen:
            continue
        seen.add(key)
        entries.append(AppEntry(name.strip(), target, shortcut))
    return sorted(entries, key=lambda e: e.name.lower())


class StartMenuCatalog:
    def __init__(self, dirs: Sequence[Path] | None = None) -> None:
        self._dirs = list(dirs) if dirs is not None else start_menu_dirs()
        self._entries: list[AppEntry] | None = None

    def entries(self) -> Sequence[AppEntry]:
        if self._entries is None:
            self._entries = build_entries(self._scan())
        return list(self._entries)

    def _scan(self) -> Iterator[tuple[str, str, str]]:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        for directory in self._dirs:
            if not directory.exists():
                continue
            for link in sorted(directory.rglob("*.lnk")):
                try:
                    target = str(shell.CreateShortcut(str(link)).TargetPath)
                except Exception:
                    log.warning("could not resolve shortcut %s", link, exc_info=True)
                    continue
                yield link.stem, target, str(link)
