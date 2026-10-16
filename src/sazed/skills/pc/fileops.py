"""Move, copy, rename and delete files and folders, create folders, and undo the last change.

Everything here is pure: the rules that keep changes inside the user's folders, the names, the
plans and their pt-BR descriptions. The disk is reached only through the `FileChanger` port.
Paths are Windows paths, handled with `ntpath` so the rules behave the same on any machine.
"""

from __future__ import annotations

import ntpath
import re
import unicodedata
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, Protocol

from sazed.core.outcomes import (
    AmbiguousSlot,
    BadName,
    ChangeUndone,
    CopiedNotMoved,
    FileBusy,
    FileChangeProposed,
    FileCopied,
    FileGone,
    FileMoved,
    FileNotFound,
    FileRecycled,
    FileRenamed,
    FolderCreated,
    FolderNotFound,
    IntoItself,
    NameTaken,
    NoRecycleBin,
    NothingRecent,
    NothingToUndo,
    NotInRecycleBin,
    Outcome,
    PlanChanged,
    Protected,
    SearchUnavailable,
    UndoStale,
)
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue, Unmatched
from sazed.skills.pc.files import (
    FOLDER_SYNONYMS,
    KIND_EXTENSIONS,
    KIND_PHRASES,
    KNOWN_FOLDERS,
    SEARCH_LIMIT,
    SHOWN_LIMIT,
    FileHit,
    FileSearch,
    KnownFolders,
    SearchError,
    file_label,
    is_exact,
)

INVALID_CHARACTERS = frozenset('\\/:*?"<>|')
RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{n}" for n in range(1, 10)]
    + [f"LPT{n}" for n in range(1, 10)]
)
_DRIVE_ROOT = re.compile(r"^[a-z]:\\?$")


@dataclass(frozen=True)
class Area:
    """Where changes may happen.

    `roots`: the user profile and the configured folders; items strictly inside them may change.
    `fixed`: folders that may hold changes but never change themselves (the roots and the known
    folders). `trees`: nothing inside them ever changes (AppData, Sazed's data and project).
    """

    roots: tuple[str, ...]
    fixed: tuple[str, ...]
    trees: tuple[str, ...]
    realpath: Callable[[str], str]


def _norm(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(path)).rstrip("\\") or "\\"


def is_inside(child: str, parent: str) -> bool:
    """Strictly inside (never equal), comparing whole path segments."""
    c, p = _norm(child), _norm(parent)
    return c != p and c.startswith(p.rstrip("\\") + "\\")


def _display(path: str) -> str:
    return ntpath.basename(path.rstrip("\\/")) or path


def _resolved(path: str, area: Area) -> str:
    return _norm(area.realpath(path))


def _all_resolved(paths: tuple[str, ...], area: Area) -> list[str]:
    # The area's folders go through realpath too: a candidate is resolved, so a folder
    # configured through a subst drive or junction would otherwise never match itself, and a
    # tree named through a link would not protect what is really inside it.
    return [_resolved(p, area) for p in paths]


def _in_tree(resolved: str, area: Area) -> bool:
    if "appdata" in resolved.split("\\"):
        return True
    return any(resolved == t or is_inside(resolved, t) for t in _all_resolved(area.trees, area))


def check_source(path: str, area: Area) -> Protected | None:
    """None when `path` may be moved, copied, renamed or deleted."""
    resolved = _resolved(path, area)
    if (
        _DRIVE_ROOT.match(resolved)
        or resolved in set(_all_resolved(area.fixed, area))
        or _in_tree(resolved, area)
        or not any(is_inside(resolved, root) for root in _all_resolved(area.roots, area))
    ):
        return Protected(_display(path))
    return None


def check_destination(folder: str, area: Area) -> Protected | None:
    """None when things may be put into `folder` (the known folders and roots included)."""
    resolved = _resolved(folder, area)
    roots = _all_resolved(area.roots, area)
    allowed = any(resolved == r or is_inside(resolved, r) for r in roots)
    if _DRIVE_ROOT.match(resolved) or _in_tree(resolved, area) or not allowed:
        return Protected(_display(folder))
    return None


def name_problem(name: str) -> str | None:
    """Why `name` cannot be a file or folder name (pt-BR), or None."""
    if not name.strip():
        return "o nome está vazio"
    if any(c in INVALID_CHARACTERS or ord(c) < 32 for c in name):
        return 'não pode ter os caracteres \\ / : * ? " < > |'
    if name.endswith((".", " ")):
        return "não pode terminar em ponto ou espaço"
    stem = name.split(".", 1)[0].strip().upper()
    if stem in RESERVED_NAMES:
        return f"'{stem}' é um nome reservado do Windows"
    return None


def _split(name: str) -> tuple[str, str]:
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        return name, ""
    return stem, f".{ext}"


def free_name(name: str, taken: Collection[str]) -> str:
    """`name`, or "name (2).ext", "(3)"… — never one already in `taken` (case ignored)."""
    used = {t.casefold() for t in taken}
    if name.casefold() not in used:
        return name
    stem, ext = _split(name)
    n = 2
    while f"{stem} ({n}){ext}".casefold() in used:
        n += 1
    return f"{stem} ({n}){ext}"


def keep_extension(old: str, new: str, *, is_dir: bool) -> str:
    """A renamed file keeps its extension unless the new name already ends with it."""
    if is_dir:
        return new
    ext = _split(old)[1]
    if not ext or new.casefold().endswith(ext.casefold()):
        return new
    return new + ext


ChangeKind = Literal["mover", "copiar", "renomear", "apagar", "criar", "restaurar"]


@dataclass(frozen=True)
class ItemState:
    path: str
    is_dir: bool
    size: int
    """Bytes; for a folder, the total of the files inside."""
    mtime: float
    count: int
    """Files inside a folder (0 for a file)."""


@dataclass(frozen=True)
class ChangePlan:
    kind: ChangeKind
    source: str | None
    """None when creating a folder or restoring from the Recycle Bin."""
    target: str
    """The final full path (for "apagar", the item that goes to the Recycle Bin)."""
    is_dir: bool
    before: ItemState | None
    """The source as planned: `apply` re-checks it, so a file changed meanwhile is left alone."""
    renamed_for_clash: bool = False
    undo_of: int | None = None
    """The change-log id this plan undoes."""
    recycle_ref: str | None = None


@dataclass(frozen=True)
class LoggedChange:
    id: int
    kind: ChangeKind
    source: str | None
    target: str
    is_dir: bool
    size: int
    mtime: float
    """Size and modification time of `target` right after the change (for undo checks)."""
    recycle_ref: str | None


def human_size(size: int) -> str:
    if size < 1024:
        return f"{size} bytes"
    value, units = size / 1024, ["KB", "MB", "GB", "TB"]
    while value >= 1024 and len(units) > 1:
        value, units = value / 1024, units[1:]
    text = f"{value:.1f}".replace(".", ",") if value < 10 else f"{round(value)}"
    return f"{text} {units[0]}"


def _name(path: str) -> str:
    return ntpath.basename(path.rstrip("\\/"))


def _parent(path: str) -> str:
    return ntpath.dirname(path.rstrip("\\/"))


def _label(folder: str, labels: Mapping[str, str]) -> str:
    known = {_norm(k): v for k, v in labels.items()}
    return known.get(_norm(folder), _name(folder) or folder)


def _item(name: str, state: ItemState | None, is_dir: bool) -> str:
    if not is_dir:
        return name
    if state is None:
        return f"a pasta {name}"
    files = "arquivo" if state.count == 1 else "arquivos"
    return f"a pasta {name} ({state.count} {files}, {human_size(state.size)})"


def plan_change(
    kind: ChangeKind,
    source: ItemState | None,
    folder: str | None,
    new_name: str | None,
    taken: Collection[str],
    area: Area,
    *,
    can_recycle: bool = True,
) -> ChangePlan | Outcome:
    """The exact change a command means, or why it cannot happen.

    `taken`: the names already in the folder the result lands in (for a rename, the item's
    own folder).
    """
    used = {t.casefold() for t in taken}
    if kind == "criar":
        if folder is None or new_name is None:
            raise ValueError("criar needs a folder and a name")
        problem = name_problem(new_name)
        if problem is not None:
            return BadName(new_name, problem)
        refused = check_destination(folder, area)
        if refused is not None:
            return refused
        if new_name.casefold() in used:
            return NameTaken(new_name)
        return ChangePlan("criar", None, ntpath.join(folder, new_name), True, None)
    if source is None:
        raise ValueError(f"{kind} needs an item")
    refused = check_source(source.path, area)
    if refused is not None:
        return refused
    name = _name(source.path)
    if kind == "apagar":
        if not can_recycle:
            return NoRecycleBin(name)
        return ChangePlan("apagar", source.path, source.path, source.is_dir, source)
    if kind == "renomear":
        if new_name is None:
            raise ValueError("renomear needs a name")
        problem = name_problem(new_name)
        if problem is not None:
            return BadName(new_name, problem)
        final = keep_extension(name, new_name, is_dir=source.is_dir)
        clash = final.casefold() in used and final.casefold() != name.casefold()
        if final == name or clash:
            return NameTaken(final)
        target = ntpath.join(_parent(source.path), final)
        return ChangePlan("renomear", source.path, target, source.is_dir, source)
    if folder is None:
        raise ValueError(f"{kind} needs a destination")
    refused = check_destination(folder, area)
    if refused is not None:
        return refused
    if source.is_dir and (_norm(folder) == _norm(source.path) or is_inside(folder, source.path)):
        return IntoItself(name)
    if kind == "mover" and _norm(folder) == _norm(_parent(source.path)):
        return NameTaken(name)
    final = free_name(name, taken)
    target = ntpath.join(folder, final)
    return ChangePlan(kind, source.path, target, source.is_dir, source, final != name)


def plan_undo(
    change: LoggedChange, now: ItemState | None, taken_at_origin: Collection[str]
) -> ChangePlan | Outcome:
    """How to revert `change`, given the current state of what it produced.

    `taken_at_origin`: the names now in the folder the item would go back to.
    """
    if change.kind == "apagar":
        if now is not None:  # something already stands where the item was
            return UndoStale(_name(change.target))
        return ChangePlan(
            "restaurar",
            None,
            change.target,
            change.is_dir,
            None,
            undo_of=change.id,
            recycle_ref=change.recycle_ref,
        )
    name = _name(change.target)
    if now is None or (now.size, now.mtime) != (change.size, change.mtime):
        return UndoStale(name)
    if change.kind in ("copiar", "criar"):
        return ChangePlan(
            "apagar", change.target, change.target, change.is_dir, now, undo_of=change.id
        )
    if change.source is None:
        raise ValueError(f"{change.kind} logged without a source")
    original = _name(change.source)
    others = {t.casefold() for t in taken_at_origin}
    if _norm(_parent(change.source)) == _norm(_parent(change.target)):
        others.discard(name.casefold())  # a rename: the item itself sits in that folder
    if original.casefold() in others:
        return UndoStale(name)
    return ChangePlan(
        change.kind, change.target, change.source, change.is_dir, now, undo_of=change.id
    )


def describe_plan(plan: ChangePlan, labels: Mapping[str, str]) -> str:
    """The pt-BR sentence the user confirms (without "Confirma?").

    `labels`: pt-BR names for known folders whose folder on disk is English ("Documents").
    """
    name = _name(plan.target if plan.source is None else plan.source)
    if plan.kind == "restaurar":
        return f"Tirar {name} da Lixeira de volta para {_label(_parent(plan.target), labels)}"
    if plan.undo_of is not None:
        if plan.kind == "apagar":
            where = _label(_parent(plan.target), labels)
            what = f"a pasta {name}" if plan.is_dir else f"a cópia {name}"
            return f"Mandar {what} (em {where}) para a Lixeira"
        if plan.kind == "renomear":
            return f"Voltar o nome de {name} para {_name(plan.target)}"
        if plan.source is not None:
            frm = _label(_parent(plan.source), labels)
            to = _label(_parent(plan.target), labels)
            return f"Devolver {_item(name, None, plan.is_dir)} de {frm} para {to}"
    item = _item(name, plan.before, plan.is_dir)
    if plan.kind == "apagar":
        return f"Mandar {item} para a Lixeira"
    if plan.kind == "criar":
        return f"Criar a pasta {_name(plan.target)} em {_label(_parent(plan.target), labels)}"
    if plan.kind == "renomear":
        return f"Renomear {item} para {_name(plan.target)}"
    if plan.source is None:
        raise ValueError(f"{plan.kind} without a source")
    verb = "Mover" if plan.kind == "mover" else "Copiar"
    frm, to = _label(_parent(plan.source), labels), _label(_parent(plan.target), labels)
    text = f"{verb} {item} de {frm} para {to}"
    if plan.renamed_for_clash:
        text += f". Já existe {name} lá; vou salvar como {_name(plan.target)}"
    return text


class MovedAsCopy(Exception):
    """A move to another drive copied the item but could not remove the original: there are
    now two. The skill logs and reports it as a copy."""


class ChangeBusy(Exception):
    """The item is open in another program, or permission was denied (adapter raises it)."""


class FileChanger(Protocol):
    def state(self, path: str) -> ItemState | None: ...
    def names_in(self, folder: str) -> set[str]: ...
    def move(self, src: str, dst: str) -> None: ...
    def copy(self, src: str, dst: str) -> None: ...
    def rename(self, src: str, dst: str) -> None: ...
    def make_folder(self, path: str) -> None: ...
    def can_recycle(self, item: ItemState) -> bool:
        """Whether the Recycle Bin will really take `item` (never a permanent delete)."""
        ...

    def recycle(self, path: str) -> str:
        """Send to the Recycle Bin; return a reference `restore` understands."""
        ...

    def restore(self, ref: str) -> bool:
        """Take the item back out of the Recycle Bin; False when it is no longer there."""
        ...


class ChangeLog(Protocol):
    def record(
        self, plan: ChangePlan, after: ItemState | None, recycle_ref: str | None, at: datetime
    ) -> int: ...
    def latest_open(self) -> LoggedChange | None: ...
    def mark_undone(self, change_id: int, at: datetime) -> None: ...


MOVE_EXAMPLES = (
    "move o relatório pra pasta documentos",
    "move o arquivo contrato pra área de trabalho",
    "manda o último download pra pasta documentos",
    "move a pasta viagem pra documentos",
    "leva a planilha de gastos pra pasta projetos",
    "transfere o pdf do boleto pra pasta documentos",
    "move a foto da praia pra pasta imagens",
    "passa o arquivo notas pra área de trabalho",
    "mova o currículo pra pasta documentos",
    "move o último print pra área de trabalho",
    "transfere a pasta projetos pra área de trabalho",
)
COPY_EXAMPLES = (
    "copia o relatório pra pasta documentos",
    "copia o arquivo contrato pra área de trabalho",
    "copia o último download pra pasta documentos",
    "copia a pasta viagem pra documentos",
    "copia a planilha de gastos pra pasta projetos",
    "duplica o pdf do boleto na pasta documentos",
    "faz uma cópia da foto da praia na pasta imagens",
    "copia o arquivo notas pra área de trabalho",
    "copie o currículo pra pasta documentos",
    "copia o último print pra área de trabalho",
    "duplica o último print na pasta imagens",
    "copia a pasta projetos pra área de trabalho",
)
RENAME_EXAMPLES = (
    "renomeia o relatório pra relatório final",
    "renomeia o arquivo contrato pra contrato assinado",
    "muda o nome da pasta viagem pra viagem antiga",
    "troca o nome da planilha de gastos pra gastos de outubro",
    "renomeia o último download pra boleto",
    "muda o nome do arquivo notas pra notas velhas",
    "renomeie a foto da praia pra praia de verão",
    "renomear o currículo pra currículo atualizado",
    "põe o nome do pdf do boleto como boleto pago",
    "renomeia a pasta projetos pra projetos antigos",
    "renomeia a pasta viagem pra viagem de férias",
    "troca o nome do último download pra fatura",
    "renomeia o último print pra erro na tela",
)
DELETE_EXAMPLES = (
    "apaga o relatório",
    "apaga o arquivo contrato",
    "deleta o último download",
    "apaga a pasta viagem",
    "apaga a pasta documentos",
    "deleta a pasta de imagens",
    "apaga a pasta downloads",
    "joga a planilha de gastos no lixo",
    "exclui o pdf do boleto",
    "manda a foto da praia pra lixeira",
    "remove o arquivo notas",
    "apague o currículo",
    "apaga o arquivo relatório",
    "deleta a planilha de gastos",
    "exclui a apresentação do projeto",
    "manda o relatório pro lixo",
    "joga o último download na lixeira",
    "joga o último print no lixo",
)
CREATE_EXAMPLES = (
    "cria uma pasta chamada viagem",
    "cria uma pasta nova na área de trabalho",
    "cria a pasta projetos em documentos",
    "faz uma pasta chamada fotos",
    "crie uma pasta chamada notas na área de trabalho",
    "cria uma nova pasta chamada orçamentos",
    "criar pasta chamada viagem em documentos",
    "cria uma pasta pra guardar as fotos",
    "faz uma pasta nova chamada contas",
    "cria uma pasta com o nome trabalho",
)

_VERBS: dict[str, str] = {
    "mover": "mover",
    "copiar": "copiar",
    "renomear": "renomear",
    "apagar": "apagar",
    "criar": "criar",
    "restaurar": "restaurar",
}
_KINDS: dict[str, ChangeKind] = {
    "arquivo_mover": "mover",
    "arquivo_copiar": "copiar",
    "arquivo_renomear": "renomear",
    "arquivo_apagar": "apagar",
    "pasta_criar": "criar",
}
DEFAULT_CREATE_FOLDER = "Área de Trabalho"
_ITEM = SlotSpec("item", True, "Qual arquivo ou pasta?")
_KIND_SLOT = SlotSpec("tipo", False, "De que tipo é o arquivo?")


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.strip())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    return " ".join(
        w for w in plain.split() if w not in ("a", "o", "de", "da", "do", "meus", "minhas")
    )


def _value(slots: Slots, name: str) -> str | None:
    found = slots.get(name)
    return str(found.value) if isinstance(found, SlotValue) else None


def _describe_intent(kind: ChangeKind) -> Callable[[Slots], str]:
    verb = _VERBS[kind]

    def describe(slots: Slots) -> str:
        item = _value(slots, "item")
        if item is None:
            return f"{verb} um arquivo"
        return f"{verb} {item.split(':', 1)[-1]}"

    return describe


class FileOpsSkill:
    id = "fileops"

    def __init__(
        self,
        folders: KnownFolders,
        search: FileSearch,
        changer: FileChanger,
        log: ChangeLog,
        area: Area,
    ) -> None:
        self._folders = folders
        self._search = search
        self._changer = changer
        self._log = log
        self._area = area
        self._pending: ChangePlan | None = None
        self._shown: dict[str, dict[str, str]] = {}
        """Per slot, the choices last listed (label → path): a pick arrives back as its label.
        Kept per slot: listing folders must not forget the file just picked."""
        destination = SlotSpec("destino", True, "Para qual pasta?")
        new_name = SlotSpec("novo_nome", True, "Qual o novo nome?")
        self.intents: tuple[IntentSpec, ...] = tuple(
            IntentSpec(
                intent_id,
                examples,
                specs,
                _describe_intent(_KINDS[intent_id]),
                learnable=False,
                confirms_itself=True,
            )
            for intent_id, examples, specs in (
                ("arquivo_mover", MOVE_EXAMPLES, (_ITEM, destination, _KIND_SLOT)),
                ("arquivo_copiar", COPY_EXAMPLES, (_ITEM, destination, _KIND_SLOT)),
                ("arquivo_renomear", RENAME_EXAMPLES, (_ITEM, new_name, _KIND_SLOT)),
                ("arquivo_apagar", DELETE_EXAMPLES, (_ITEM, _KIND_SLOT)),
                (
                    "pasta_criar",
                    CREATE_EXAMPLES,
                    (
                        SlotSpec("novo_nome", True, "Qual o nome da pasta?"),
                        SlotSpec("destino", False, "Em qual pasta?"),
                    ),
                ),
            )
        )

    # resolving -----------------------------------------------------------------------------

    def _labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for name in KNOWN_FOLDERS:
            path = self._folders.resolve(name)
            if path is not None:
                labels[path] = name
        return labels

    def _choose(self, slot: str, hits: Sequence[FileHit], now: datetime) -> str | Outcome:
        if len(hits) == 1:
            return hits[0].path
        shown: dict[str, str] = {}
        for found in hits[:SHOWN_LIMIT]:
            base = file_label(found, now)
            label, n = base, 2
            while label in shown:
                label, n = f"{base} #{n}", n + 1
            shown[label] = found.path
        self._shown[slot] = shown
        return AmbiguousSlot(slot, tuple(shown))

    def _known_folder(self, words: str) -> str | None:
        """The pt-BR name of a known or configured folder `words` names, if any."""
        key = _fold(words)
        for name in self._folders.names():
            if _fold(name) == key:
                return name
        for synonym, name in FOLDER_SYNONYMS.items():
            if _fold(synonym) == key:
                return name
        return None

    def _item_path(self, slots: Slots, now: datetime) -> str | Outcome:
        value = _value(slots, "item")
        if value is None:
            raise ValueError("a file change called without its item")
        picked = self._shown.get("item", {})
        if value in picked:
            return picked[value]
        how, _, words = value.partition(":")
        if how not in ("ultimo", "pasta", "arquivo"):
            # Never search a label as words: that proposed another file (final review I1).
            raise ValueError(f"unknown item {value!r}")
        try:
            if how == "ultimo":
                folder = self._folders.resolve(words)
                if folder is None:
                    return FolderNotFound(words)
                newest = self._search.newest(folder, None, 1)
                return newest[0].path if newest else NothingRecent()
            if how == "pasta":
                known = self._known_folder(words)
                if known is not None:  # "apaga a pasta downloads": the folder itself
                    return Protected(known)
                hits = self._search.folders(words.split(), SEARCH_LIMIT)
                allowed = [h for h in hits if check_source(h.path, self._area) is None]
                if hits and not allowed:
                    return Protected(hits[0].name)
                return self._choose("item", allowed, now) if allowed else FolderNotFound(words)
            kind = _value(slots, "tipo")
            extensions = KIND_EXTENSIONS.get(kind, ()) if kind is not None else ()
            hits = self._search.search(words.split(), extensions, SEARCH_LIMIT)
        except SearchError:
            return SearchUnavailable()
        allowed = [h for h in hits if check_source(h.path, self._area) is None]
        if hits and not allowed:
            return Protected(hits[0].name)
        hits = allowed
        if not hits:
            return FileNotFound(words, KIND_PHRASES.get(kind, KIND_PHRASES[None]))
        exact = [h for h in hits if is_exact(h, words)]
        return exact[0].path if len(exact) == 1 else self._choose("item", hits, now)

    def _destination(self, slots: Slots, default: str | None, now: datetime) -> str | Outcome:
        found = slots.get("destino")
        if isinstance(found, Unmatched):
            try:
                hits = self._search.folders(found.raw.split(), SEARCH_LIMIT)
            except SearchError:
                return SearchUnavailable()
            allowed = [h for h in hits if check_destination(h.path, self._area) is None]
            if hits and not allowed:
                return Protected(found.raw)
            if not allowed:
                return FolderNotFound(found.raw)
            return self._choose("destino", allowed, now)
        name = str(found.value) if isinstance(found, SlotValue) else default
        if name is None:
            raise ValueError("a file change called without its destination")
        picked = self._shown.get("destino", {})
        if name in picked:
            return picked[name]
        path = self._folders.resolve(name)
        return FolderNotFound(name) if path is None else path

    # proposing -----------------------------------------------------------------------------

    def _propose(self, plan: ChangePlan | Outcome) -> Outcome:
        if not isinstance(plan, ChangePlan):
            return plan
        self._pending = plan
        return FileChangeProposed(describe_plan(plan, self._labels()))

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        kind = _KINDS.get(intent_id)
        if kind is None:
            raise ValueError(f"unknown intent {intent_id}")
        self._pending = None
        new_name = _value(slots, "novo_nome")
        if kind == "criar":
            folder = self._destination(slots, DEFAULT_CREATE_FOLDER, ctx.now)
            if not isinstance(folder, str):
                return folder
            taken = self._changer.names_in(folder)
            return self._propose(plan_change("criar", None, folder, new_name, taken, self._area))
        path = self._item_path(slots, ctx.now)
        if not isinstance(path, str):
            return path
        source = self._changer.state(path)
        if source is None:
            return FileGone(_name(path))
        if kind == "apagar":
            can = self._changer.can_recycle(source)
            plan = plan_change("apagar", source, None, None, (), self._area, can_recycle=can)
            return self._propose(plan)
        if kind == "renomear":
            taken = self._changer.names_in(_parent(path))
            return self._propose(plan_change("renomear", source, None, new_name, taken, self._area))
        folder = self._destination(slots, None, ctx.now)
        if not isinstance(folder, str):
            return folder
        taken = self._changer.names_in(folder)
        return self._propose(plan_change(kind, source, folder, None, taken, self._area))

    def propose_undo(self, ctx: SkillContext) -> Outcome:
        self._pending = None
        change = self._log.latest_open()
        if change is None:
            return NothingToUndo()
        now = self._changer.state(change.target)
        origin = change.source if change.source is not None else change.target
        taken = self._changer.names_in(_parent(origin))
        return self._propose(plan_undo(change, now, taken))

    # applying ------------------------------------------------------------------------------

    def _still_valid(self, plan: ChangePlan) -> bool:
        """The disk still matches what the user confirmed."""
        if plan.source is not None and plan.before is not None:
            now = self._changer.state(plan.source)
            if now is None or (now.size, now.mtime) != (plan.before.size, plan.before.mtime):
                return False
            if plan.undo_of is None and check_source(plan.source, self._area) is not None:
                return False
        if plan.kind in ("mover", "copiar", "renomear", "criar", "restaurar"):
            occupant = self._changer.state(plan.target)
            same_item = plan.source is not None and _norm(plan.source) == _norm(plan.target)
            if occupant is not None and not same_item:
                return False
        if plan.kind in ("mover", "copiar", "criar") and plan.undo_of is None:
            return check_destination(_parent(plan.target), self._area) is None
        return True

    def apply_pending(self, ctx: SkillContext) -> Outcome:
        plan, self._pending = self._pending, None
        if plan is None or not self._still_valid(plan):
            return PlanChanged()
        labels = self._labels()
        action = describe_plan(plan, labels)
        name = _name(plan.source if plan.source is not None else plan.target)
        ref: str | None = None
        try:
            if plan.kind == "restaurar":
                if plan.recycle_ref is None or not self._changer.restore(plan.recycle_ref):
                    if plan.undo_of is not None:
                        self._log.mark_undone(plan.undo_of, ctx.now)
                    return NotInRecycleBin(name)
            elif plan.kind == "apagar":
                current = self._changer.state(plan.target)
                if current is None or not self._changer.can_recycle(current):
                    return NoRecycleBin(name)
                ref = self._changer.recycle(plan.target)
            elif plan.kind == "criar":
                self._changer.make_folder(plan.target)
            elif plan.source is not None:
                operation = {
                    "mover": self._changer.move,
                    "copiar": self._changer.copy,
                    "renomear": self._changer.rename,
                }[plan.kind]
                operation(plan.source, plan.target)
        except MovedAsCopy:
            as_copy = replace(plan, kind="copiar")
            self._log.record(as_copy, self._changer.state(plan.target), None, ctx.now)
            return CopiedNotMoved(_name(plan.target), _label(_parent(plan.target), labels))
        except ChangeBusy:
            return FileBusy(_VERBS[plan.kind], name)
        if plan.undo_of is not None:
            self._log.mark_undone(plan.undo_of, ctx.now)
            return ChangeUndone(action)
        after = None if plan.kind == "apagar" else self._changer.state(plan.target)
        self._log.record(plan, after, ref, ctx.now)
        final = _name(plan.target)
        folder = _label(_parent(plan.target), labels)
        if plan.kind == "mover":
            return FileMoved(final, folder)
        if plan.kind == "copiar":
            return FileCopied(final, folder)
        if plan.kind == "renomear":
            return FileRenamed(name, final)
        if plan.kind == "criar":
            return FolderCreated(final, folder)
        return FileRecycled(name)
