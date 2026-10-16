"""Real known folders and the real Windows Search index."""

import time
import uuid
from pathlib import Path

import pytest

from sazed.adapters.windows.files import WindowsFileSearch, WindowsKnownFolders

pytestmark = pytest.mark.windows


def test_known_folders_exist_on_this_machine() -> None:
    folders = WindowsKnownFolders({})
    downloads = folders.resolve("Downloads")
    assert downloads is not None and Path(downloads).is_dir()
    assert Path(downloads).name.lower() == "downloads"
    for name in folders.names():
        path = folders.resolve(name)
        assert path is None or Path(path).is_dir()


def test_the_index_finds_a_new_file_by_name() -> None:
    documents = WindowsKnownFolders({}).resolve("Documentos")
    assert documents is not None
    token = f"sazed2b{uuid.uuid4().hex[:10]}"
    target = Path(documents) / f"{token} relatório.txt"  # a space and an accent
    target.write_text("teste", encoding="utf-8")
    try:
        search = WindowsFileSearch([str(Path.home())])
        deadline = time.monotonic() + 30
        hits = search.search([token], [], 6)
        while not hits and time.monotonic() < deadline:
            time.sleep(1)
            hits = search.search([token], [], 6)
        if not hits:
            pytest.skip("the index did not pick the file up within 30 s")
        assert [h.name for h in hits] == [target.name]
        assert Path(hits[0].path) == target
        assert Path(hits[0].path).exists()
        assert search.search([token], [".pdf"], 6) == []
    finally:
        target.unlink()


def test_newest_in_downloads_does_not_fail() -> None:
    downloads = WindowsKnownFolders({}).resolve("Downloads")
    assert downloads is not None
    WindowsFileSearch([str(Path.home())]).newest(downloads, None, 3)
