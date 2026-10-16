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
from typing import Protocol

from sazed.core.outcomes import (
    AmbiguousSlot,
    FileGone,
    FileNotFound,
    FileOpened,
    FolderNotFound,
    FolderOpened,
    NothingRecent,
    Outcome,
    ProgramRevealed,
    RecentFiles,
    SearchUnavailable,
)
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue, Unmatched


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

# ItemPathDisplay is a localised display path ("C:\Usuários\…\Documentos") that does not exist
# on disk; ItemUrl ("file:C:/Users/…") is the real one (seen on this machine, 2026-10-16).
_COLUMNS = "System.ItemUrl, System.ItemFolderNameDisplay, System.DateModified"
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


# Folders known by name, in pt-BR. Wiring maps each to the user's real folder.
KNOWN_FOLDERS: tuple[str, ...] = (
    "Downloads",
    "Documentos",
    "Área de Trabalho",
    "Imagens",
    "Vídeos",
    "Músicas",
    "Capturas de Tela",
)
FOLDER_SYNONYMS: dict[str, str] = {
    "baixados": "Downloads",
    "download": "Downloads",
    "meus documentos": "Documentos",
    "desktop": "Área de Trabalho",
    "fotos": "Imagens",
    "minhas fotos": "Imagens",
    "musica": "Músicas",
    "print": "Capturas de Tela",
    "prints": "Capturas de Tela",
    "capturas": "Capturas de Tela",
    "screenshots": "Capturas de Tela",
}
DOWNLOADS = "Downloads"
SHOWN_LIMIT = 5
SEARCH_LIMIT = SHOWN_LIMIT + 1
RECENT_LIMIT = 50
RECENT_NAMES = 10


class KnownFolders(Protocol):
    def names(self) -> Sequence[str]: ...
    def resolve(self, name: str) -> str | None:
        """The folder's path; None when it is configured but does not exist."""
        ...


class SearchError(Exception):
    """The Windows Search index could not be queried."""


class FileSearch(Protocol):
    def search(self, words: Sequence[str], extensions: Sequence[str], limit: int) -> list[FileHit]:
        """Files whose name contains every word, newest first. Raises SearchError."""
        ...

    def newest(self, folder: str, since: datetime | None, limit: int) -> list[FileHit]:
        """Files directly in `folder`, newest first. Raises SearchError."""
        ...


class FileOpener(Protocol):
    def open(self, path: str) -> None: ...
    def reveal(self, path: str) -> None:
        """Open the file's folder with the file selected."""
        ...

    def exists(self, path: str) -> bool: ...


OPEN_FOLDER_EXAMPLES = (
    "abre a pasta downloads",
    "abre a pasta documentos",
    "abre a pasta meus documentos",
    "abre a pasta de imagens",
    "mostra a pasta de músicas",
    "abre a pasta de vídeos",
    "abrir pasta de músicas",
    "abre a pasta dos prints",
    "entra na pasta downloads",
    "abre o explorador na pasta documentos",
)
OPEN_FILE_EXAMPLES = (
    "abre o arquivo relatório",
    "acha o arquivo contrato",
    "encontra a planilha de gastos",
    "abre o arquivo pdf do boleto",
    "procura o arquivo currículo",
    "abre o documento proposta",
    "localiza a foto da praia",
    "abre a apresentação do projeto",
    "acha o arquivo",
    "abre o arquivo documentos",
    "abre a foto da viagem",
    "abre o arquivo chamado orçamento",
)
OPEN_RECENT_EXAMPLES = (
    "abre o último download",
    "abre o último print",
    "abre o arquivo que baixei por último",
    "abre a última captura de tela",
    "abre o download mais recente",
    "abre o último arquivo baixado",
    "mostra o último print",
    "abre o print que tirei",
    "abre a última coisa que baixei",
    "abre o último arquivo da pasta downloads",
)
LIST_RECENT_EXAMPLES = (
    "quais arquivos baixei hoje",
    "o que eu baixei hoje",
    "lista os downloads de hoje",
    "mostra o que baixei hoje",
    "quais downloads fiz hoje",
    "o que tem de novo nos downloads",
    "quais arquivos chegaram hoje",
    "me diz o que eu baixei hoje",
    "lista o que baixei",
    "quantos arquivos baixei hoje",
)


def _value(slots: Slots, name: str) -> str | None:
    found = slots.get(name)
    return str(found.value) if isinstance(found, SlotValue) else None


def _describe(verb: str, slots: Slots, name: str) -> str:
    value = _value(slots, name)
    return verb if value is None else f"{verb} {value}"


def _labels(hits: Sequence[FileHit], now: datetime) -> dict[str, str]:
    """Label → path; a repeated label gets a number so every choice stays distinct."""
    shown: dict[str, str] = {}
    for hit in hits:
        base = file_label(hit, now)
        label, n = base, 2
        while label in shown:
            label, n = f"{base} #{n}", n + 1
        shown[label] = hit.path
    return shown


class FilesSkill:
    id = "files"

    def __init__(self, folders: KnownFolders, search: FileSearch, opener: FileOpener) -> None:
        self._folders = folders
        self._search = search
        self._opener = opener
        self._shown: dict[str, str] = {}
        """The choices last listed (label → path): a pick arrives back as its label."""
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "abrir_pasta",
                OPEN_FOLDER_EXAMPLES,
                (SlotSpec("pasta", True, "Qual pasta devo abrir?"),),
                lambda s: _describe("abrir a pasta", s, "pasta"),
            ),
            IntentSpec(
                "abrir_arquivo",
                OPEN_FILE_EXAMPLES,
                (
                    SlotSpec("arquivo", True, "Qual arquivo devo abrir?"),
                    SlotSpec("tipo", False, "De que tipo é o arquivo?"),
                ),
                lambda s: _describe("abrir o arquivo", s, "arquivo"),
            ),
            IntentSpec(
                "abrir_recente",
                OPEN_RECENT_EXAMPLES,
                (SlotSpec("pasta", False, "De qual pasta?"),),
                lambda s: "abrir o arquivo mais recente",
            ),
            IntentSpec(
                "listar_recentes",
                LIST_RECENT_EXAMPLES,
                (),
                lambda s: "dizer o que você baixou hoje",
            ),
        )

    def _open_hit(self, path: str) -> Outcome:
        name = os.path.basename(path)
        if not self._opener.exists(path):
            return FileGone(name)
        if is_program(path):
            self._opener.reveal(path)
            return ProgramRevealed(name)
        self._opener.open(path)
        return FileOpened(name)

    def _folder(self, slots: Slots, default: str | None) -> tuple[str, str] | Outcome:
        found = slots.get("pasta")
        if isinstance(found, Unmatched):
            return FolderNotFound(found.raw)
        name = str(found.value) if isinstance(found, SlotValue) else default
        if name is None:
            raise ValueError("abrir_pasta called without its required slot 'pasta'")
        path = self._folders.resolve(name)
        return FolderNotFound(name) if path is None else (name, path)

    def _find(self, slots: Slots, now: datetime) -> Outcome:
        query = _value(slots, "arquivo")
        if query is None:
            raise ValueError("abrir_arquivo called without its required slot 'arquivo'")
        if query in self._shown:
            return self._open_hit(self._shown[query])
        kind = _value(slots, "tipo")
        extensions = KIND_EXTENSIONS.get(kind, ()) if kind is not None else ()
        try:
            hits = self._search.search(query.split(), extensions, SEARCH_LIMIT)
        except SearchError:
            return SearchUnavailable()
        if not hits:
            return FileNotFound(query, KIND_PHRASES.get(kind, KIND_PHRASES[None]))
        exact = [h for h in hits if is_exact(h, query)]
        if len(hits) == 1 or len(exact) == 1:
            return self._open_hit((exact or hits)[0].path)
        self._shown = _labels(hits[:SHOWN_LIMIT], now)
        return AmbiguousSlot("arquivo", tuple(self._shown))

    def _recent(self, intent_id: str, slots: Slots, now: datetime) -> Outcome:
        listing = intent_id == "listar_recentes"
        folder = self._folder({} if listing else slots, DOWNLOADS)
        if not isinstance(folder, tuple):
            return folder
        since = now.replace(hour=0, minute=0, second=0, microsecond=0) if listing else None
        try:
            hits = self._search.newest(folder[1], since, RECENT_LIMIT if listing else 1)
        except SearchError:
            return SearchUnavailable()
        if not hits:
            return NothingRecent()
        if not listing:
            return self._open_hit(hits[0].path)
        return RecentFiles(len(hits), tuple(h.name for h in hits[:RECENT_NAMES]))

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id == "abrir_pasta":
            folder = self._folder(slots, None)
            if not isinstance(folder, tuple):
                return folder
            self._opener.open(folder[1])
            return FolderOpened(folder[0])
        if intent_id == "abrir_arquivo":
            return self._find(slots, ctx.now)
        if intent_id in ("abrir_recente", "listar_recentes"):
            return self._recent(intent_id, slots, ctx.now)
        raise ValueError(f"unknown intent {intent_id}")
