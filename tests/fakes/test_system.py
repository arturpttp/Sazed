from pathlib import Path

import pytest

from fakes.system import SAZED_PID, SAZED_RSS, FakeProbe, broken_git
from sazed.interfaces.dashboard.processes import is_sazed
from sazed.interfaces.dashboard.sources import GitUnavailable


def test_fake_probe_has_one_sazed_process_with_stats() -> None:
    probe = FakeProbe()
    (proc,) = probe.processes()
    assert proc.pid == SAZED_PID and is_sazed(proc.cmdline)
    stats = probe.process_stats(SAZED_PID)
    assert stats is not None and stats.rss == SAZED_RSS
    assert probe.process_stats(12345) is None
    assert probe.scans == 1
    used, total, percent = probe.memory()
    assert used / total * 100 == percent


def test_broken_git_raises_the_typed_failure() -> None:
    with pytest.raises(GitUnavailable):
        broken_git(Path("."), ["log"])
