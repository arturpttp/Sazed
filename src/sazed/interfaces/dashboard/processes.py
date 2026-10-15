"""Find the running Sazed among the machine's processes, and keep sample history. Pure.

`uv run sazed` on Windows is a chain: uv.exe → sazed.exe (trampoline) → python.exe (venv
redirector) → python.exe (the real interpreter, which holds the memory). Every link matches;
the main process is a match with no matching child. The dashboard (`sazed painel`) is excluded.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import PureWindowsPath


@dataclass(frozen=True)
class ProcInfo:
    pid: int
    ppid: int
    name: str
    cmdline: tuple[str, ...]


@dataclass(frozen=True)
class SazedTree:
    main: list[ProcInfo]
    """Matches with no matching child: the processes doing the work."""
    chain: list[ProcInfo]
    """Every match, launchers included, ordered by parent before child."""


DASHBOARD_COMMAND = "painel"


def _stem(arg: str) -> str:
    return PureWindowsPath(arg).stem.lower()


def is_sazed(cmdline: Sequence[str]) -> bool:
    if not cmdline or DASHBOARD_COMMAND in cmdline:
        return False
    args = list(cmdline)
    first = _stem(args[0])
    if first == "sazed":
        return True
    if first in {"uv", "uvx"} and "run" in args:
        return "sazed" in args[args.index("run") + 1 :]
    if first.startswith("python") and len(args) > 1:
        if args[1] == "-m":
            return len(args) > 2 and (args[2] == "sazed" or args[2].startswith("sazed."))
        return _stem(args[1]) == "sazed"
    return False


def sazed_tree(processes: Iterable[ProcInfo], own_pid: int) -> SazedTree:
    matches = [p for p in processes if p.pid != own_pid and is_sazed(p.cmdline)]
    pids = {p.pid for p in matches}
    parents = {p.ppid for p in matches if p.ppid in pids}
    main = [p for p in matches if p.pid not in parents]
    by_pid = {p.pid: p for p in matches}

    def depth(p: ProcInfo) -> int:
        n = 0
        while p.ppid in by_pid and n < len(by_pid):
            p = by_pid[p.ppid]
            n += 1
        return n

    chain = sorted(matches, key=lambda p: (depth(p), p.pid))
    return SazedTree(main, chain)


class History[T]:
    """The newest `size` samples, oldest first."""

    def __init__(self, size: int) -> None:
        if size < 1:
            raise ValueError("size must be at least 1")
        self._items: deque[T] = deque(maxlen=size)

    def add(self, item: T) -> None:
        self._items.append(item)

    def items(self) -> list[T]:
        return list(self._items)
