"""Known folders, the Windows Search index, and opening files without ever running a program."""

from __future__ import annotations

import logging
import ntpath
import os
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from sazed.nlu.normalize import strip_accents
from sazed.skills.pc.files import (
    KNOWN_FOLDERS,
    FileHit,
    SearchError,
    folders_sql,
    is_program,
    search_sql,
)

log = logging.getLogger(__name__)

# KNOWNFOLDERID values for the pt-BR names in KNOWN_FOLDERS.
FOLDER_IDS: dict[str, str] = {
    "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "Documentos": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "Área de Trabalho": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "Imagens": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "Vídeos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
    "Músicas": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "Capturas de Tela": "{B7BEDE81-DF94-4682-A7D8-57A52620B86F}",
}
CONNECTION = "Provider=Search.CollatorDSO;Extended Properties='Application=Windows';"


def _key(name: str) -> str:
    return strip_accents(name).casefold().strip()


def shell_folder(name: str) -> str | None:
    """The real path of a known folder (it follows a moved Downloads folder)."""
    import ctypes
    from ctypes import wintypes

    folder_id = FOLDER_IDS.get(name)
    if folder_id is None:
        return None

    class GUID(ctypes.Structure):
        _fields_ = [  # noqa: RUF012  # ctypes needs a class attribute
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    guid = GUID()
    ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
    if ole32.CLSIDFromString(ctypes.c_wchar_p(folder_id), ctypes.byref(guid)) != 0:
        return None
    path = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
    if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path)) != 0:
        return None
    try:
        return path.value
    finally:
        ole32.CoTaskMemFree(path)


class WindowsKnownFolders:
    def __init__(
        self,
        configured: Mapping[str, Path],
        lookup: Callable[[str], str | None] = shell_folder,
    ) -> None:
        self._configured = {_key(k): (k, Path(v)) for k, v in configured.items()}
        self._lookup = lookup
        known = {_key(n) for n in KNOWN_FOLDERS}
        extra = [name for key, (name, _) in self._configured.items() if key not in known]
        self._names = [*KNOWN_FOLDERS, *extra]
        for name, path in self._configured.values():
            if not path.is_dir():
                log.warning("configured folder %r does not exist: %s", name, path)

    def names(self) -> Sequence[str]:
        return list(self._names)

    def resolve(self, name: str) -> str | None:
        configured = self._configured.get(_key(name))
        if configured is not None:
            path = configured[1]
            return str(path) if path.is_dir() else None
        found = self._lookup(name)
        return found if found is not None and os.path.isdir(found) else None


def hit_from(path: str, modified: datetime) -> FileHit:
    folder = ntpath.basename(ntpath.dirname(path.replace("/", "\\")))
    return FileHit(path, ntpath.basename(path.replace("/", "\\")), folder, modified)


def hit_from_url(url: str, folder: str, modified: datetime) -> FileHit:
    """A row of the index: `System.ItemUrl` ("file:C:/…") and its folder's display name."""
    path = ntpath.normpath(url.removeprefix("file:"))
    return FileHit(path, ntpath.basename(path), folder, modified)


PARTIAL_DOWNLOADS = (".crdownload", ".part", ".partial", ".tmp", ".download")


def newest_from_listing(
    entries: Iterable[tuple[str, float]], since: datetime | None, limit: int
) -> list[FileHit]:
    """(path, mtime) pairs of one folder → newest first, from `since` on; never a download
    still in progress (a browser's partial file would open the "how to open it?" dialog)."""
    hits = [
        hit_from(path, datetime.fromtimestamp(mtime))
        for path, mtime in entries
        if not path.lower().endswith(PARTIAL_DOWNLOADS)
    ]
    hits = [h for h in hits if since is None or h.modified >= since]
    return sorted(hits, key=lambda h: h.modified, reverse=True)[:limit]


def _local(value: datetime) -> datetime:
    """The index reports UTC; Sazed works in naive local time."""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone().replace(tzinfo=None)


class WindowsFileSearch:
    def __init__(self, scopes: Sequence[str]) -> None:
        self._scopes = list(scopes)

    def _query(self, sql: str) -> list[FileHit]:
        import pythoncom
        import pywintypes
        import win32com.client

        pythoncom.CoInitialize()  # REPL and dashboard threads differ
        try:
            conn = win32com.client.Dispatch("ADODB.Connection")
            conn.Open(CONNECTION)
            try:
                rs = conn.Execute(sql)[0]
                hits: list[FileHit] = []
                while not rs.EOF:
                    url = str(rs.Fields.Item("System.ItemUrl").Value)
                    folder = str(rs.Fields.Item("System.ItemFolderNameDisplay").Value or "")
                    modified = _local(rs.Fields.Item("System.DateModified").Value)
                    hits.append(hit_from_url(url, folder, modified))
                    rs.MoveNext()
                return hits
            finally:
                conn.Close()
        except pywintypes.com_error as error:
            log.warning("Windows Search query failed: %s", error)
            raise SearchError(str(error)) from error
        finally:
            pythoncom.CoUninitialize()

    def search(self, words: Sequence[str], extensions: Sequence[str], limit: int) -> list[FileHit]:
        return self._query(search_sql(words, extensions, self._scopes, limit))

    def folders(self, words: Sequence[str], limit: int) -> list[FileHit]:
        hits = self._query(folders_sql(words, self._scopes, limit))
        # The index counts a .zip as a "compressed folder": only real folders are folders here.
        return [h for h in hits if os.path.isdir(h.path)]

    def newest(self, folder: str, since: datetime | None, limit: int) -> list[FileHit]:
        # One known folder: listing it is cheap and always current, while the index lags
        # behind a just-finished download (it opened the previous file). Never a disk scan.
        try:
            with os.scandir(folder) as entries:
                listing = [(e.path, e.stat().st_mtime) for e in entries if e.is_file()]
        except OSError as error:
            raise SearchError(str(error)) from error
        return newest_from_listing(listing, since, limit)


class WindowsFileOpener:
    def open(self, path: str) -> None:
        # The load-bearing guard: the skill checks first only to give a better answer.
        if not os.path.isdir(path) and is_program(path):
            raise ValueError(f"refusing to open a file that is not a known document: {path}")
        os.startfile(path)  # type: ignore[attr-defined]  # Windows only

    def reveal(self, path: str) -> None:
        subprocess.Popen(["explorer.exe", f"/select,{os.path.normpath(path)}"])

    def exists(self, path: str) -> bool:
        return os.path.exists(path)
