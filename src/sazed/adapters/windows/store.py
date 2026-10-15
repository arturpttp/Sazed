"""Store (UWP/MSIX) apps from shell:AppsFolder, with their package install folders."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Iterator, Sequence

from sazed.adapters.windows.catalog import is_excluded
from sazed.skills.pc.apps import AppEntry

log = logging.getLogger(__name__)

# "<PackageFamilyName>!<AppId>"; the family name ends in a 13-char publisher id.
_AUMID = re.compile(r"^(?P<family>[^\\/!]+_[a-z0-9]{13})![^\\/!]+$", re.IGNORECASE)


def build_store_entries(
    items: Iterable[tuple[str, str]], folder_of: Callable[[str], str | None]
) -> list[AppEntry]:
    """(display name, AppsFolder path) → Store entries.

    Desktop apps also appear in AppsFolder; they are skipped here because their .lnk entries
    come from StartMenuCatalog.
    """
    entries = []
    for name, path in items:
        match = _AUMID.match(path)
        if match is None or is_excluded(name):
            continue
        folder = folder_of(match["family"]) or ""
        entries.append(AppEntry(name.strip(), folder, f"shell:AppsFolder\\{path}", "store"))
    return sorted(entries, key=lambda e: e.name.casefold())


def _package_folder(family: str) -> str | None:
    try:
        from winrt.windows.management.deployment import PackageManager

        for package in PackageManager().find_packages_by_user_security_id_package_family_name(
            "", family
        ):
            return str(package.installed_location.path)
    except Exception:
        log.warning("could not resolve the install folder of %s", family, exc_info=True)
    return None


class StoreCatalog:
    def __init__(self) -> None:
        self._entries: list[AppEntry] | None = None

    def entries(self) -> Sequence[AppEntry]:
        if self._entries is None:
            self._entries = build_store_entries(self._scan(), _package_folder)
        return list(self._entries)

    def _scan(self) -> Iterator[tuple[str, str]]:
        import win32com.client

        folder = win32com.client.Dispatch("Shell.Application").NameSpace("shell:AppsFolder")
        for item in folder.Items():
            yield str(item.Name), str(item.Path)
