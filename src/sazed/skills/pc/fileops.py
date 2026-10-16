"""Move, copy, rename and delete files and folders, create folders, and undo the last change.

Everything here is pure: the rules that keep changes inside the user's folders, the names, the
plans and their pt-BR descriptions. The disk is reached only through the `FileChanger` port.
Paths are Windows paths, handled with `ntpath` so the rules behave the same on any machine.
"""

from __future__ import annotations

import ntpath
import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Literal

from sazed.core.outcomes import (
    BadName,
    IntoItself,
    NameTaken,
    NoRecycleBin,
    Outcome,
    Protected,
    UndoStale,
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


def _in_tree(resolved: str, area: Area) -> bool:
    if "appdata" in resolved.split("\\"):
        return True
    return any(resolved == _norm(t) or is_inside(resolved, t) for t in area.trees)


def check_source(path: str, area: Area) -> Protected | None:
    """None when `path` may be moved, copied, renamed or deleted."""
    resolved = _resolved(path, area)
    if (
        _DRIVE_ROOT.match(resolved)
        or resolved in {_norm(f) for f in area.fixed}
        or _in_tree(resolved, area)
        or not any(is_inside(resolved, root) for root in area.roots)
    ):
        return Protected(_display(path))
    return None


def check_destination(folder: str, area: Area) -> Protected | None:
    """None when things may be put into `folder` (the known folders and roots included)."""
    resolved = _resolved(folder, area)
    allowed = any(resolved == _norm(r) or is_inside(resolved, r) for r in area.roots)
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
