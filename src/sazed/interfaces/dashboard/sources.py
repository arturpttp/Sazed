"""The dashboard's I/O: plan and ledger files, git, proofs, and machine resources.

This is the impure shell around the pure modules (`ledger`, `processes`, `stats`). Every
source fails into a typed pt-BR state for its own panel; nothing here may stop the server.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import psutil

from sazed.interfaces.dashboard.ledger import (
    GIT_LOG_FORMAT,
    choose_active_plan,
    current_task,
    parse_git_log,
    parse_ledger,
    parse_plan_tasks,
    proof_summary,
    task_statuses,
)
from sazed.interfaces.dashboard.processes import History, ProcInfo, sazed_tree

log = logging.getLogger(__name__)

PLANS_DIR = Path("docs/superpowers/plans")
PROOFS_DIR = Path("docs/superpowers/proofs")
LEDGERS_DIR = Path(".superpowers/sdd")
LEDGER_FILE = "progress.md"


class GitUnavailable(Exception):
    """git cannot answer. `str(error)` is a pt-BR message meant for the user."""


def run_git(root: Path, args: Sequence[str]) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        raise GitUnavailable("O git não está instalado ou não está no PATH.") from None
    except subprocess.TimeoutExpired:
        raise GitUnavailable("O git demorou demais para responder.") from None
    if done.returncode != 0:
        log.warning("git %s failed in %s: %s", args, root, done.stderr.strip())
        raise GitUnavailable("Não consegui ler o histórico do git nesta pasta.")
    return done.stdout


GitRunner = Callable[[Path, Sequence[str]], str]


def _read(path: Path) -> str:
    # One existing proofs file has a non-UTF-8 byte: never fail on it.
    return path.read_text(encoding="utf-8", errors="replace")


class DevSources:
    """Development progress of the agent building Sazed, read from `root` (the repo)."""

    def __init__(self, root: Path, *, git: GitRunner = run_git, commits: int = 30) -> None:
        self.root = root
        self._git = git
        self._commits = commits

    def _plans(self) -> list[Path]:
        folder = self.root / PLANS_DIR
        return sorted(folder.glob("*.md"), reverse=True) if folder.is_dir() else []

    def _ledger_names(self) -> set[str]:
        folder = self.root / LEDGERS_DIR
        if not folder.is_dir():
            return set()
        return {p.name for p in folder.iterdir() if (p / LEDGER_FILE).is_file()}

    def _commit_log(self) -> dict[str, Any]:
        try:
            text = self._git(self.root, ["log", f"--format={GIT_LOG_FORMAT}", f"-n{self._commits}"])
            branch = self._git(self.root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        except GitUnavailable as err:
            return {"available": False, "message": str(err), "items": [], "branch": None}
        items = [asdict(c) for c in parse_git_log(text)]
        return {"available": True, "items": items, "branch": branch}

    def _proofs(self) -> list[dict[str, Any]]:
        folder = self.root / PROOFS_DIR
        if not folder.is_dir():
            return []
        result = []
        for path in sorted(folder.glob("*.md"), reverse=True):
            title, sections = proof_summary(_read(path))
            result.append({"name": path.name, "title": title, "sections": sections})
        return result

    def snapshot(self) -> dict[str, Any]:
        plans = self._plans()
        active = choose_active_plan([p.stem for p in plans], self._ledger_names())
        snap: dict[str, Any] = {
            "root": str(self.root),
            "plans": [{"name": p.stem, "tasks": len(parse_plan_tasks(_read(p)))} for p in plans],
            "plan": None,
            "tasks": [],
            "current_task": None,
            "done": 0,
            "total": 0,
            "entries": [],
            "message": None,
            "commits": self._commit_log(),
            "proofs": self._proofs(),
        }
        if active is None:
            snap["message"] = (
                "Nenhum plano com registro de progresso (.superpowers/sdd/<plano>/progress.md)"
                f" em {self.root}."
            )
            return snap
        ledger = parse_ledger(_read(self.root / LEDGERS_DIR / active / LEDGER_FILE))
        tasks = task_statuses(
            parse_plan_tasks(_read(self.root / PLANS_DIR / f"{active}.md")), ledger
        )
        current = current_task(tasks)
        snap.update(
            plan={"name": active, "ledger_plan": ledger.plan},
            tasks=[asdict(t) for t in tasks],
            current_task=asdict(current) if current else None,
            done=sum(t.status == "done" for t in tasks),
            total=len(tasks),
            entries=[asdict(e) for e in ledger.entries],
        )
        return snap


# resources -----------------------------------------------------------------------


@dataclass(frozen=True)
class ProcStats:
    rss: int
    cpu: float
    """Percent of one core, as psutil reports it (can exceed 100)."""
    created: float


class SystemProbe(Protocol):
    def processes(self) -> list[ProcInfo]: ...
    def process_stats(self, pid: int) -> ProcStats | None: ...
    def cpu_percent(self) -> float: ...
    def cpu_count(self) -> int: ...
    def memory(self) -> tuple[int, int, float]: ...
    def disks(self) -> list[tuple[str, int, int, float]]: ...
    def boot_time(self) -> float: ...


class PsutilProbe:
    def __init__(self) -> None:
        self._procs: dict[int, psutil.Process] = {}

    def processes(self) -> list[ProcInfo]:
        found = []
        for p in psutil.process_iter(["pid", "ppid", "name", "cmdline"]):
            info = p.info
            found.append(
                ProcInfo(
                    int(info["pid"]),
                    int(info["ppid"] or 0),
                    str(info["name"] or ""),
                    tuple(info["cmdline"] or ()),
                )
            )
        return found

    def process_stats(self, pid: int) -> ProcStats | None:
        try:
            proc = self._procs.get(pid) or psutil.Process(pid)
            self._procs[pid] = proc
            with proc.oneshot():
                return ProcStats(proc.memory_info().rss, proc.cpu_percent(), proc.create_time())
        except (psutil.Error, ValueError):
            self._procs.pop(pid, None)
            return None

    def cpu_percent(self) -> float:
        return float(psutil.cpu_percent(interval=None))

    def cpu_count(self) -> int:
        return psutil.cpu_count() or 1

    def memory(self) -> tuple[int, int, float]:
        mem = psutil.virtual_memory()
        return (mem.total - mem.available, mem.total, float(mem.percent))

    def disks(self) -> list[tuple[str, int, int, float]]:
        found = []
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts or not part.fstype:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            found.append((part.mountpoint, usage.used, usage.total, float(usage.percent)))
        return found

    def boot_time(self) -> float:
        return float(psutil.boot_time())


NOT_RUNNING = "Sazed não está em execução."


class ResourceSampler:
    """Samples while the page polls. Thread-safe; at most one real sample per second."""

    def __init__(
        self,
        probe: SystemProbe,
        own_pid: int,
        *,
        history: int = 150,
        rescan_seconds: float = 10.0,
    ) -> None:
        self._probe = probe
        self._own_pid = own_pid
        self._history: History[dict[str, Any]] = History(history)
        self._rescan = rescan_seconds
        self._lock = threading.Lock()
        self._last: dict[str, Any] | None = None
        self._last_at = float("-inf")
        self._scanned_at = float("-inf")
        self._main: list[ProcInfo] = []
        self._chain: list[ProcInfo] = []

    def _scan(self, now: float) -> None:
        if now - self._scanned_at < self._rescan:
            return
        tree = sazed_tree(self._probe.processes(), self._own_pid)
        self._main, self._chain = tree.main, tree.chain
        self._scanned_at = now

    def sample(self, now: float) -> dict[str, Any]:
        with self._lock:
            if self._last is not None and now - self._last_at < 1.0:
                return self._last
            self._scan(now)
            main: list[dict[str, Any]] = []
            for proc in self._main:
                stats = self._probe.process_stats(proc.pid)
                if stats is None:
                    continue
                main.append(
                    {
                        "pid": proc.pid,
                        "rss": stats.rss,
                        "cpu": stats.cpu,
                        "uptime_s": max(0.0, now - stats.created),
                        "cmdline": " ".join(proc.cmdline),
                    }
                )
            if len(main) < len(self._main):
                self._scanned_at = float("-inf")  # something exited: look again next time
            own = self._probe.process_stats(self._own_pid)
            used, total, percent = self._probe.memory()
            cpu = self._probe.cpu_percent()
            sazed_rss = sum(m["rss"] for m in main) if main else None
            sazed_cpu = sum(m["cpu"] for m in main) if main else None
            self._history.add(
                {
                    "t": now,
                    "cpu": cpu,
                    "ram": percent,
                    "sazed_rss": sazed_rss,
                    "sazed_cpu": sazed_cpu,
                }
            )
            self._last = {
                "sazed": {
                    "running": bool(main),
                    "message": None if main else NOT_RUNNING,
                    "main": main,
                    "chain": [{"pid": p.pid, "name": p.name} for p in self._chain],
                },
                "dashboard": {"pid": self._own_pid, "rss": own.rss if own else None},
                "system": {
                    "cpu": cpu,
                    "cpu_count": self._probe.cpu_count(),
                    "ram": {"used": used, "total": total, "percent": percent},
                    "disks": [
                        {"mount": m, "used": u, "total": t, "percent": p}
                        for m, u, t, p in self._probe.disks()
                    ],
                    "boot_time": self._probe.boot_time(),
                },
                "history": self._history.items(),
            }
            self._last_at = now
            return self._last
