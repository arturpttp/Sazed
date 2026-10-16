"""WindowsFileChanger on a temporary folder (no Recycle Bin here: that is -m windows)."""

from pathlib import Path

import pytest

from sazed.adapters.windows.fileops import WindowsFileChanger, count_tree, move_across
from sazed.skills.pc.fileops import ChangeBusy, MovedAsCopy


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


# a move to another drive: copy, verify, then send the original to the bin ----------------


class Disk:
    """Records calls; `files` is what exists."""

    def __init__(self, files: set[str], sizes: dict[str, int] | None = None) -> None:
        self.files = set(files)
        self.sizes = sizes or {}
        self.calls: list[tuple[str, str]] = []

    def copy(self, a: str, b: str) -> None:
        self.calls.append(("copy", b))
        self.files.add(b)

    def remove_copy(self, path: str) -> None:
        self.calls.append(("remove_copy", path))
        self.files.discard(path)

    def discard(self, path: str) -> None:
        self.calls.append(("discard", path))
        self.files.discard(path)

    def size_of(self, path: str) -> int:
        return self.sizes.get(path, 30)

    def run(self, **overrides: object) -> None:
        kwargs = {
            "copy": self.copy,
            "remove_copy": self.remove_copy,
            "discard_source": self.discard,
            "size_of": self.size_of,
            "exists": lambda p: p in self.files,
            **overrides,
        }
        move_across("src", "dst", **kwargs)  # type: ignore[arg-type]


def test_a_cross_drive_move_copies_verifies_then_sends_the_original_to_the_bin() -> None:
    disk = Disk({"src"})
    disk.run()
    assert disk.calls == [("copy", "dst"), ("discard", "src")]
    assert disk.files == {"dst"}


def test_a_failed_copy_removes_only_its_own_partial_copy() -> None:
    disk = Disk({"src"})

    def broken(a: str, b: str) -> None:
        disk.files.add(b)  # half written
        raise OSError(28, "disco cheio")

    with pytest.raises(OSError):
        disk.run(copy=broken)
    assert disk.calls == [("remove_copy", "dst")]
    assert disk.files == {"src"}


def test_a_copy_with_the_wrong_size_is_removed_and_the_original_kept() -> None:
    disk = Disk({"src"}, sizes={"src": 30, "dst": 12})
    with pytest.raises(OSError):
        disk.run()
    assert disk.calls == [("copy", "dst"), ("remove_copy", "dst")]
    assert disk.files == {"src"}


def test_something_already_at_the_destination_is_never_touched() -> None:
    # Final review I3: the rollback removed a folder it had not created.
    disk = Disk({"src", "dst"})
    with pytest.raises(FileExistsError):
        disk.run()
    assert disk.calls == [] and disk.files == {"src", "dst"}


def test_when_the_original_cannot_be_removed_the_copy_stays_and_says_so() -> None:
    # Final review I2: reported "nothing happened" while a full copy existed.
    disk = Disk({"src"})

    def stuck(path: str) -> None:
        raise ChangeBusy(path)

    with pytest.raises(MovedAsCopy):
        disk.run(discard_source=stuck)
    assert disk.files == {"src", "dst"}
    assert ("remove_copy", "dst") not in disk.calls


# The Recycle Bin must really take the item: otherwise Windows deletes it for good -----------


def test_an_item_that_fits_the_bin_may_be_recycled() -> None:
    from sazed.adapters.windows.fileops import fits_in_bin

    assert fits_in_bin(size=10 * 2**20, count=3, capacity=50 * 2**30, nuke=False)


@pytest.mark.parametrize(
    ("size", "count", "capacity", "nuke"),
    [
        (60 * 2**30, 1, 50 * 2**30, False),  # bigger than the bin: Windows would destroy it
        (10, 1, 50 * 2**30, True),  # the bin is turned off for this drive
        (10, 100_000, 50 * 2**30, False),  # the count was capped: the size is unknown
        (10, 1, None, False),  # the bin's size could not be read
    ],
)
def test_anything_the_bin_might_not_take_is_refused(
    size: int, count: int, capacity: int | None, nuke: bool
) -> None:
    from sazed.adapters.windows.fileops import fits_in_bin

    assert not fits_in_bin(size=size, count=count, capacity=capacity, nuke=nuke)


def test_recycling_asks_windows_to_warn_instead_of_deleting_for_good() -> None:
    from win32com.shell import shellcon

    from sazed.adapters.windows.fileops import RECYCLE_FLAGS

    assert RECYCLE_FLAGS & shellcon.FOF_ALLOWUNDO
    assert RECYCLE_FLAGS & shellcon.FOF_WANTNUKEWARNING
