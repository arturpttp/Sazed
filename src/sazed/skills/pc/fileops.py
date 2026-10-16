"""Move, copy, rename and delete files and folders, create folders, and undo the last change.

Everything here is pure: the rules that keep changes inside the user's folders, the names, the
plans and their pt-BR descriptions. The disk is reached only through the `FileChanger` port.
Paths are Windows paths, handled with `ntpath` so the rules behave the same on any machine.
"""

from __future__ import annotations

import ntpath
import re
from collections.abc import Callable, Collection
from dataclasses import dataclass

from sazed.core.outcomes import Protected

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
