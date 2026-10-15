import pytest

from sazed.interfaces.dashboard.processes import History, ProcInfo, is_sazed, sazed_tree

VENV = r"C:\repo\.venv\Scripts"
CFG = ["--config", r"C:\tmp\config.toml"]

# The real tree of `uv run sazed`, captured on 2026-10-15 (see the dashboard design note).
UV = ProcInfo(8228, 16908, "uv.exe", ("uv", "run", "sazed", *CFG))
TRAMPOLINE = ProcInfo(7440, 8228, "sazed.exe", (rf"{VENV}\sazed.exe", *CFG))
REDIRECT = ProcInfo(15988, 7440, "python.exe", (rf"{VENV}\python.exe", rf"{VENV}\sazed.exe", *CFG))
REAL = ProcInfo(23832, 15988, "python.exe", (r"C:\py\python.exe", rf"{VENV}\sazed.exe", *CFG))


@pytest.mark.parametrize(
    ("cmdline", "expected"),
    [
        (UV.cmdline, True),
        (TRAMPOLINE.cmdline, True),
        (REAL.cmdline, True),
        (("python", "-m", "sazed.interfaces.cli.main"), True),
        (("python", "-m", "sazed"), True),
        (("sazed", "aprendizado"), True),
        (("uv", "run", "sazed", "painel"), False),
        ((rf"{VENV}\sazed.exe", "painel", "--porta", "9000"), False),
        (("code", r"C:\Programacao\JARVIS\Sazed"), False),
        (("python", "-m", "pytest", r"C:\Programacao\JARVIS\Sazed\tests"), False),
        (("notepad.exe", "sazed.txt"), False),
        ((), False),
    ],
)
def test_is_sazed(cmdline: tuple[str, ...], expected: bool) -> None:
    assert is_sazed(cmdline) is expected


def test_tree_picks_the_leaf_as_the_main_process() -> None:
    other = ProcInfo(1, 0, "explorer.exe", ("explorer.exe",))
    tree = sazed_tree([other, UV, TRAMPOLINE, REDIRECT, REAL], own_pid=999)
    assert [p.pid for p in tree.main] == [REAL.pid]
    assert [p.pid for p in tree.chain] == [UV.pid, TRAMPOLINE.pid, REDIRECT.pid, REAL.pid]


def test_tree_excludes_the_dashboard_itself() -> None:
    me = ProcInfo(50, 0, "python.exe", (r"C:\py\python.exe", rf"{VENV}\sazed.exe", "x"))
    tree = sazed_tree([me], own_pid=50)
    assert tree.main == [] and tree.chain == []


def test_two_instances_are_two_main_processes() -> None:
    a = ProcInfo(10, 1, "sazed.exe", ("sazed",))
    b = ProcInfo(20, 2, "sazed.exe", ("sazed",))
    assert [p.pid for p in sazed_tree([a, b], own_pid=0).main] == [10, 20]


def test_history_keeps_the_newest_samples() -> None:
    history: History[int] = History(3)
    for n in range(5):
        history.add(n)
    assert history.items() == [2, 3, 4]
    with pytest.raises(ValueError):
        History(0)
