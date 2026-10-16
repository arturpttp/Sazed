"""Open known folders, find files by name through the Windows Search index, open recent files.

Nothing here changes a file or reads its content. The SQL for the index is built here, pure,
so the escaping is tested without Windows.
"""

from __future__ import annotations

import os
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class FileHit:
    path: str
    name: str
    folder: str
    """The name of the folder holding the file (shown in choices)."""
    modified: datetime


# A file found by a search is never run: these open their folder instead. Spec §6.
PROGRAM_EXTENSIONS: frozenset[str] = frozenset(
    [
        ".exe",
        ".com",
        ".bat",
        ".cmd",
        ".ps1",
        ".psm1",
        ".vbs",
        ".vbe",
        ".js",
        ".jse",
        ".wsf",
        ".wsh",
        ".msi",
        ".msp",
        ".scr",
        ".pif",
        ".lnk",
        ".url",
        ".hta",
        ".cpl",
        ".jar",
        ".reg",
        ".appref-ms",
    ]
)

KIND_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "planilha": (".xlsx", ".xls", ".ods", ".csv"),
    "pdf": (".pdf",),
    "documento": (".docx", ".doc", ".odt", ".rtf", ".pdf"),
    "apresentacao": (".pptx", ".ppt", ".odp"),
    "foto": (".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif"),
    "video": (".mp4", ".mkv", ".mov", ".avi", ".webm"),
    "musica": (".mp3", ".flac", ".wav", ".m4a", ".ogg"),
    "texto": (".txt", ".md"),
}

KIND_PHRASES: dict[str | None, str] = {
    None: "nenhum arquivo chamado",
    "planilha": "nenhuma planilha chamada",
    "pdf": "nenhum PDF chamado",
    "documento": "nenhum documento chamado",
    "apresentacao": "nenhuma apresentação chamada",
    "foto": "nenhuma foto chamada",
    "video": "nenhum vídeo chamado",
    "musica": "nenhuma música chamada",
    "texto": "nenhum texto chamado",
}

_COLUMNS = "System.ItemPathDisplay, System.DateModified"
_ORDER = "ORDER BY System.DateModified DESC"


def is_program(path: str) -> bool:
    name = os.path.basename(path).lower()
    return any(name.endswith(ext) for ext in PROGRAM_EXTENSIONS)


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _quote(text: str) -> str:
    return text.replace("'", "''")


def escape_sql_like(word: str) -> str:
    """Escape a word for a Windows Search `LIKE '%…%'`: quotes doubled, wildcards bracketed."""
    out = []
    for ch in word:
        if ch in "[%_":
            out.append(f"[{ch}]")
        else:
            out.append(ch)
    return _quote("".join(out))


def _like(word: str) -> str:
    forms = [word] if _plain(word) == word.casefold() else [word, _plain(word)]
    terms = [f"System.FileName LIKE '%{escape_sql_like(f)}%'" for f in forms]
    return terms[0] if len(terms) == 1 else "(" + " OR ".join(terms) + ")"


def search_sql(
    words: Sequence[str], extensions: Sequence[str], scopes: Sequence[str], limit: int
) -> str:
    scope = " OR ".join(f"SCOPE='file:{_quote(s)}'" for s in scopes)
    parts = [f"({scope})", "System.Kind <> 'folder'", *(_like(w) for w in words)]
    if extensions:
        kinds = " OR ".join(f"System.FileExtension = '{_quote(e)}'" for e in extensions)
        parts.append(f"({kinds})")
    where = " AND ".join(parts)
    return f"SELECT TOP {int(limit)} {_COLUMNS} FROM SYSTEMINDEX WHERE {where} {_ORDER}"


def newest_sql(folder: str, since: datetime | None, limit: int) -> str:
    parts = [f"DIRECTORY='file:{_quote(folder)}'", "System.Kind <> 'folder'"]
    if since is not None:
        parts.append(f"System.DateModified >= '{since:%Y-%m-%d %H:%M:%S}'")
    where = " AND ".join(parts)
    return f"SELECT TOP {int(limit)} {_COLUMNS} FROM SYSTEMINDEX WHERE {where} {_ORDER}"


def file_label(hit: FileHit, now: datetime) -> str:
    day = hit.modified.date()
    if day == now.date():
        when = f"hoje {hit.modified:%H:%M}"
    elif day == (now - timedelta(days=1)).date():
        when = "ontem"
    elif day.year == now.year:
        when = f"{hit.modified:%d/%m}"
    else:
        when = f"{hit.modified:%d/%m/%Y}"
    return f"{hit.name} ({hit.folder}, {when})"


def is_exact(hit: FileHit, query: str) -> bool:
    stem = os.path.splitext(hit.name)[0]
    return _plain(stem) == _plain(query)
