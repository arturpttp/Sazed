from datetime import datetime

import pytest

from fakes.ports import FakeStatus
from sazed.core.outcomes import CpuStatus, DiskStatus, MemoryStatus
from sazed.core.skill import SkillContext
from sazed.skills.pc.status import StatusSkill, gigabytes, pt_number

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))
GB = 1024**3


@pytest.mark.parametrize(
    ("value", "places", "text"),
    [
        (5.24, 1, "5,2"),
        (1234.5, 1, "1.234,5"),
        (37.4, 0, "37"),
        (0.0, 1, "0,0"),
        (1000000, 0, "1.000.000"),
    ],
)
def test_numbers_use_pt_br_separators(value: float, places: int, text: str) -> None:
    assert pt_number(value, places) == text


def test_gigabytes() -> None:
    assert gigabytes(int(5.2 * GB)) == "5,2 GB"


def test_memory() -> None:
    status = FakeStatus(memory=(int(5.2 * GB), int(15.4 * GB)))
    outcome = StatusSkill(status).execute("status_memoria", {}, CTX)
    assert outcome == MemoryStatus("5,2 GB", "15,4 GB")


def test_cpu() -> None:
    assert StatusSkill(FakeStatus(cpu=37.4)).execute("status_cpu", {}, CTX) == CpuStatus("37%")


def test_disks() -> None:
    status = FakeStatus(disks=[("C:", 120 * GB, 476 * GB), ("D:", 1 * GB, 931 * GB)])
    assert StatusSkill(status).execute("status_disco", {}, CTX) == DiskStatus(
        ("C: 120,0 GB livres de 476,0 GB", "D: 1,0 GB livres de 931,0 GB")
    )
