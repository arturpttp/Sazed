"""Machine status from psutil."""

from __future__ import annotations

import psutil

CPU_SAMPLE_SECONDS = 0.3


class PsutilStatus:
    def memory(self) -> tuple[int, int]:
        vm = psutil.virtual_memory()
        return int(vm.available), int(vm.total)

    def cpu_percent(self) -> float:
        return float(psutil.cpu_percent(interval=CPU_SAMPLE_SECONDS))

    def disks(self) -> list[tuple[str, int, int]]:
        found = []
        for part in psutil.disk_partitions(all=False):
            if "fixed" not in part.opts:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            found.append((part.mountpoint.rstrip("\\"), int(usage.free), int(usage.total)))
        return found
