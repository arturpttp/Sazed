"""Fake machine and git for the dashboard: one Sazed process, fixed CPU/RAM/disk numbers."""

from collections.abc import Sequence
from pathlib import Path

from sazed.interfaces.dashboard.processes import ProcInfo
from sazed.interfaces.dashboard.sources import GitUnavailable, ProcStats

SAZED_PID = 10
SAZED_RSS = 400 * 2**20


class FakeProbe:
    def __init__(self) -> None:
        self.procs = [ProcInfo(SAZED_PID, 1, "sazed.exe", ("sazed",))]
        self.stats: dict[int, ProcStats] = {
            SAZED_PID: ProcStats(rss=SAZED_RSS, cpu=12.5, created=100.0)
        }
        self.scans = 0
        self.cpu = 30.0

    def processes(self) -> list[ProcInfo]:
        self.scans += 1
        return list(self.procs)

    def process_stats(self, pid: int) -> ProcStats | None:
        return self.stats.get(pid)

    def cpu_percent(self) -> float:
        return self.cpu

    def cpu_count(self) -> int:
        return 12

    def memory(self) -> tuple[int, int, float]:
        return (6 * 2**30, 12 * 2**30, 50.0)

    def disks(self) -> list[tuple[str, int, int, float]]:
        return [("C:\\", 100, 400, 25.0)]

    def boot_time(self) -> float:
        return 0.0


def broken_git(root: Path, args: Sequence[str]) -> str:
    raise GitUnavailable("git não encontrado")
