"""Read-only machine status in Sazed's voice. Numbers are formatted pt-BR here (pure)."""

from __future__ import annotations

from typing import Protocol

from sazed.core.outcomes import CpuStatus, DiskStatus, MemoryStatus, Outcome
from sazed.core.skill import IntentSpec, SkillContext
from sazed.core.types import Slots

_GB = 1024**3


class SystemStatus(Protocol):
    def memory(self) -> tuple[int, int]: ...
    def cpu_percent(self) -> float: ...
    def disks(self) -> list[tuple[str, int, int]]: ...


def pt_number(x: float, places: int) -> str:
    """1234.5 → "1.234,5": thousands with ".", decimals with ","."""
    return f"{x:,.{places}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


def gigabytes(n: int) -> str:
    return f"{pt_number(n / _GB, 1)} GB"


MEMORY_EXAMPLES = (
    "quanta memória está livre",
    "como está a memória",
    "quanta ram tem livre",
    "uso de memória",
    "memória disponível",
    "quanto de ram estou usando",
    "tem memória livre",
    "status da memória",
    "verifica a memória",
    "como está a ram",
)
CPU_EXAMPLES = (
    "como está a cpu",
    "uso do processador",
    "quanto a cpu está usando",
    "como está o processador",
    "status da cpu",
    "a cpu está pesada",
    "verifica o processador",
    "uso de cpu",
    "o processador está ocupado",
    "quanto de processamento está em uso",
)
DISK_EXAMPLES = (
    "quanto espaço tem no disco",
    "espaço livre no disco",
    "como está o armazenamento",
    "quanto de espaço sobrou",
    "status do disco",
    "verifica o espaço em disco",
    "o disco está cheio",
    "quanto espaço livre eu tenho",
    "armazenamento disponível",
    "espaço no hd",
)


class StatusSkill:
    id = "status"

    def __init__(self, status: SystemStatus) -> None:
        self._status = status
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec("status_memoria", MEMORY_EXAMPLES, (), lambda s: "verificar a memória"),
            IntentSpec("status_cpu", CPU_EXAMPLES, (), lambda s: "verificar o processador"),
            IntentSpec("status_disco", DISK_EXAMPLES, (), lambda s: "verificar o espaço em disco"),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id == "status_memoria":
            free, total = self._status.memory()
            return MemoryStatus(gigabytes(free), gigabytes(total))
        if intent_id == "status_cpu":
            return CpuStatus(f"{pt_number(self._status.cpu_percent(), 0)}%")
        if intent_id == "status_disco":
            return DiskStatus(
                tuple(
                    f"{mount} {gigabytes(free)} livres de {gigabytes(total)}"
                    for mount, free, total in self._status.disks()
                )
            )
        raise ValueError(f"unknown intent {intent_id}")
