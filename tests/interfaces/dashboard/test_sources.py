import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from fakes.system import FakeProbe, broken_git
from sazed.interfaces.dashboard.sources import (
    DevSources,
    GitUnavailable,
    PsutilProbe,
    ResourceSampler,
    run_git,
)

PLAN = "# Plan\n### Task 1: First\n### Task 2: Second\n"


def make_repo(root: Path, *, ledger: str | None) -> None:
    plans = root / "docs" / "superpowers" / "plans"
    plans.mkdir(parents=True)
    (plans / "2026-10-14-old.md").write_text("### Task 1: Old\n", encoding="utf-8")
    (plans / "2026-10-15-new.md").write_text(PLAN, encoding="utf-8")
    proofs = root / "docs" / "superpowers" / "proofs"
    proofs.mkdir(parents=True)
    (proofs / "p.md").write_bytes(b"# Proofs \xe9 latin-1\n## 1. One\n")
    if ledger is not None:
        sdd = root / ".superpowers" / "sdd" / "2026-10-15-new"
        sdd.mkdir(parents=True)
        (sdd / "progress.md").write_text(ledger, encoding="utf-8")


def fake_git(output: str) -> object:
    def git(root: Path, args: Sequence[str]) -> str:
        return output if args[0] == "log" else "feat/x\n"

    return git


def test_dev_snapshot_reads_plan_ledger_proofs_and_commits(tmp_path: Path) -> None:
    make_repo(tmp_path, ledger="# SDD ledger — plan: x.md\nTask 1: complete\nTask 2: started\n")
    log = "abc\x1f2026-10-15T10:00:00-03:00\x1fArtur\x1ffeat: a\x1e\n"
    snap = DevSources(tmp_path, git=fake_git(log)).snapshot()
    assert snap["plan"]["name"] == "2026-10-15-new"
    assert snap["plan"]["ledger_plan"] == "x.md"
    assert [(t["number"], t["status"]) for t in snap["tasks"]] == [(1, "done"), (2, "active")]
    assert snap["current_task"]["number"] == 2
    assert (snap["done"], snap["total"]) == (1, 2)
    assert snap["commits"]["items"][0]["subject"] == "feat: a"
    assert snap["commits"]["branch"] == "feat/x"
    assert snap["proofs"][0]["title"] == "Proofs \ufffd latin-1"
    assert snap["proofs"][0]["sections"] == ["1. One"]


def test_dev_snapshot_without_ledger_or_git(tmp_path: Path) -> None:
    make_repo(tmp_path, ledger=None)
    snap = DevSources(tmp_path, git=broken_git).snapshot()
    assert snap["plan"] is None
    assert "registro" in snap["message"]
    assert snap["commits"]["available"] is False
    assert snap["commits"]["message"] == "git não encontrado"
    assert [p["name"] for p in snap["plans"]] == ["2026-10-15-new", "2026-10-14-old"]


def test_dev_snapshot_of_an_empty_folder(tmp_path: Path) -> None:
    snap = DevSources(tmp_path, git=broken_git).snapshot()
    assert snap["plans"] == [] and snap["proofs"] == [] and snap["plan"] is None


def test_run_git_against_a_folder_that_is_not_a_repository(tmp_path: Path) -> None:
    with pytest.raises(GitUnavailable):
        run_git(tmp_path, ["log", "-n", "1"])


def test_run_git_reads_this_repository() -> None:
    root = Path(__file__).resolve().parents[3]
    try:
        out = run_git(root, ["rev-parse", "--is-inside-work-tree"])
    except GitUnavailable:
        pytest.skip("git is not installed")
    assert out.strip() == "true"


def test_sampler_reports_sazed_and_the_system() -> None:
    sample = ResourceSampler(FakeProbe(), own_pid=999).sample(now=160.0)
    sazed = sample["sazed"]
    assert sazed["running"] is True
    (main,) = sazed["main"]
    assert (main["pid"], main["rss"], main["cpu"], main["uptime_s"]) == (
        10,
        400 * 2**20,
        12.5,
        60.0,
    )
    system = sample["system"]
    assert system["cpu"] == 30.0
    assert system["ram"] == {"used": 6 * 2**30, "total": 12 * 2**30, "percent": 50.0}
    assert system["disks"] == [{"mount": "C:\\", "used": 100, "total": 400, "percent": 25.0}]
    assert sample["history"][-1] == {
        "t": 160.0,
        "cpu": 30.0,
        "ram": 50.0,
        "sazed_rss": 400 * 2**20,
        "sazed_cpu": 12.5,
    }


def test_sampler_says_when_sazed_is_not_running() -> None:
    probe = FakeProbe()
    probe.procs = []
    sample = ResourceSampler(probe, own_pid=999).sample(now=1.0)
    assert sample["sazed"]["running"] is False
    assert sample["sazed"]["message"] == "Sazed não está em execução."
    assert sample["history"][-1]["sazed_rss"] is None


def test_sampler_reuses_a_sample_taken_less_than_a_second_ago() -> None:
    probe = FakeProbe()
    sampler = ResourceSampler(probe, own_pid=999)
    sampler.sample(now=10.0)
    probe.cpu = 99.0
    assert sampler.sample(now=10.5)["system"]["cpu"] == 30.0
    assert sampler.sample(now=11.2)["system"]["cpu"] == 99.0
    assert len(sampler.sample(now=11.3)["history"]) == 2


def test_sampler_rescans_processes_only_every_few_seconds() -> None:
    probe = FakeProbe()
    sampler = ResourceSampler(probe, own_pid=999, rescan_seconds=10)
    for t in (0.0, 2.0, 4.0, 6.0):
        sampler.sample(now=t)
    assert probe.scans == 1
    sampler.sample(now=10.5)
    assert probe.scans == 2


def test_sampler_drops_a_process_that_exited() -> None:
    probe = FakeProbe()
    sampler = ResourceSampler(probe, own_pid=999)
    sampler.sample(now=0.0)
    probe.stats = {}
    assert sampler.sample(now=2.0)["sazed"]["running"] is False


def test_history_is_bounded() -> None:
    sampler = ResourceSampler(FakeProbe(), own_pid=999, history=3)
    for t in range(6):
        sampler.sample(now=float(t * 2))
    assert [h["t"] for h in sampler.sample(now=10.0)["history"]] == [6.0, 8.0, 10.0]


def test_psutil_probe_reads_this_machine() -> None:
    probe = PsutilProbe()
    used, total, percent = probe.memory()
    assert 0 < used < total and 0 <= percent <= 100
    assert probe.cpu_count() >= 1
    import os

    stats = probe.process_stats(os.getpid())
    assert stats is not None and stats.rss > 0
    assert any(p.pid == os.getpid() for p in probe.processes())
    assert probe.process_stats(-1) is None


def test_git_missing_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(GitUnavailable) as caught:
        run_git(tmp_path, ["log"])
    assert str(caught.value) == "O git não está instalado ou não está no PATH."
