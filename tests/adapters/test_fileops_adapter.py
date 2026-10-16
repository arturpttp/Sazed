"""WindowsFileChanger on a temporary folder (no Recycle Bin here: that is -m windows)."""

from pathlib import Path

import pytest

from sazed.adapters.windows.fileops import WindowsFileChanger, count_tree, move_across
from sazed.skills.pc.fileops import ChangeBusy


def make_tree(root: Path) -> Path:
    trip = root / "viagem"
    (trip / "fotos").mkdir(parents=True)
    (trip / "a.txt").write_bytes(b"x" * 10)
    (trip / "fotos" / "b.jpg").write_bytes(b"y" * 20)
    return trip


def test_state_of_a_file_a_folder_and_nothing(tmp_path: Path) -> None:
    changer = WindowsFileChanger()
    trip = make_tree(tmp_path)
    folder = changer.state(str(trip))
    assert folder is not None and folder.is_dir and (folder.count, folder.size) == (2, 30)
    one = changer.state(str(trip / "a.txt"))
    assert one is not None and not one.is_dir and (one.size, one.count) == (10, 0)
    assert changer.state(str(tmp_path / "nada")) is None
    assert changer.names_in(str(tmp_path)) == {"viagem"}


def test_counting_stops_at_the_bound(tmp_path: Path) -> None:
    trip = make_tree(tmp_path)
    assert count_tree(str(trip), limit=1)[0] == 1
    assert count_tree(str(trip), limit=100) == (2, 30)


def test_move_copy_rename_and_make_folder(tmp_path: Path) -> None:
    changer = WindowsFileChanger()
    trip = make_tree(tmp_path)
    docs = tmp_path / "docs"
    changer.make_folder(str(docs))
    assert docs.is_dir()
    changer.copy(str(trip), str(docs / "viagem"))
    assert (docs / "viagem" / "fotos" / "b.jpg").read_bytes() == b"y" * 20 and trip.exists()
    changer.copy(str(trip / "a.txt"), str(docs / "a.txt"))
    assert (docs / "a.txt").exists()
    changer.rename(str(docs / "a.txt"), str(docs / "b.txt"))
    assert (docs / "b.txt").exists() and not (docs / "a.txt").exists()
    changer.move(str(trip), str(docs / "viagem 2"))
    assert (docs / "viagem 2" / "a.txt").exists() and not trip.exists()


def test_make_folder_never_creates_parents(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        WindowsFileChanger().make_folder(str(tmp_path / "a" / "b"))


def test_a_file_open_in_another_program_is_busy(tmp_path: Path) -> None:
    target = tmp_path / "aberto.txt"
    target.write_text("x", encoding="utf-8")
    # Python opens a file without delete sharing on Windows: like a document open in Word.
    with target.open("r", encoding="utf-8"), pytest.raises(ChangeBusy):
        WindowsFileChanger().move(str(target), str(tmp_path / "movido.txt"))
    assert target.exists()


# a move to another drive: copy, verify, then remove — never lose the original ---------------


def test_a_cross_drive_move_copies_verifies_then_removes() -> None:
    calls: list[tuple[str, str]] = []
    sizes = {"src": 30, "dst": 30}
    move_across(
        "src",
        "dst",
        copy=lambda a, b: calls.append(("copy", b)),
        remove=lambda p: calls.append(("remove", p)),
        size_of=lambda p: sizes[p],
    )
    assert calls == [("copy", "dst"), ("remove", "src")]


def test_a_failed_copy_removes_the_partial_copy_and_keeps_the_original() -> None:
    calls: list[tuple[str, str]] = []

    def broken(a: str, b: str) -> None:
        raise OSError(28, "disco cheio")

    with pytest.raises(OSError):
        move_across(
            "src",
            "dst",
            copy=broken,
            remove=lambda p: calls.append(("remove", p)),
            size_of=lambda p: 30,
        )
    assert calls == [("remove", "dst")]


def test_a_copy_with_the_wrong_size_is_removed_and_the_original_kept() -> None:
    calls: list[tuple[str, str]] = []
    sizes = {"src": 30, "dst": 12}
    with pytest.raises(OSError):
        move_across(
            "src",
            "dst",
            copy=lambda a, b: None,
            remove=lambda p: calls.append(("remove", p)),
            size_of=lambda p: sizes[p],
        )
    assert calls == [("remove", "dst")]
