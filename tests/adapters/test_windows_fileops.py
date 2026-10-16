"""The real Recycle Bin: send a temporary file and folder there and bring them back."""

import uuid
from pathlib import Path

import pytest

from sazed.adapters.windows.fileops import WindowsFileChanger

pytestmark = pytest.mark.windows


@pytest.fixture
def scratch() -> Path:
    # Under the user's Documents, like real use; removed at the end.
    folder = Path.home() / "Documents" / f"sazed-teste-{uuid.uuid4().hex[:8]}"
    folder.mkdir()
    yield folder
    import shutil

    shutil.rmtree(folder, ignore_errors=True)


def test_the_users_drive_has_a_recycle_bin(scratch: Path) -> None:
    changer = WindowsFileChanger()
    item = scratch / "x.txt"
    item.write_text("x", encoding="utf-8")
    state = changer.state(str(item))
    assert state is not None and changer.can_recycle(state)


@pytest.mark.parametrize("kind", ["file", "folder"])
def test_recycle_then_restore(scratch: Path, kind: str) -> None:
    changer = WindowsFileChanger()
    if kind == "file":
        item = scratch / "relatório teste.txt"
        item.write_text("Sazed", encoding="utf-8")
    else:
        item = scratch / "pasta teste"
        (item / "sub").mkdir(parents=True)
        (item / "sub" / "x.txt").write_text("Sazed", encoding="utf-8")
    ref = changer.recycle(str(item))
    assert not item.exists()
    assert changer.restore(ref)
    assert item.exists()
    if kind == "folder":
        assert (item / "sub" / "x.txt").read_text(encoding="utf-8") == "Sazed"


def test_restoring_something_no_longer_in_the_bin_says_so(scratch: Path) -> None:
    changer = WindowsFileChanger()
    item = scratch / "some.txt"
    item.write_text("x", encoding="utf-8")
    ref = changer.recycle(str(item))
    assert changer.restore(ref)
    assert not changer.restore(ref)  # already back: nothing left in the bin for it


def test_restore_brings_back_the_copy_this_change_deleted(scratch: Path) -> None:
    import time

    changer = WindowsFileChanger()
    item = scratch / "mesmo nome.txt"
    item.write_text("primeiro", encoding="utf-8")
    first = changer.recycle(str(item))
    time.sleep(1.5)  # the bin keeps deletion times to the second
    item.write_text("segundo", encoding="utf-8")
    second = changer.recycle(str(item))
    assert changer.restore(second)
    assert item.read_text(encoding="utf-8") == "segundo"
    item.unlink()
    assert changer.restore(first)
    assert item.read_text(encoding="utf-8") == "primeiro"
