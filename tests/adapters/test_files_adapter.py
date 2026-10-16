import os
from datetime import datetime
from pathlib import Path

import pytest

from sazed.adapters.windows.files import (
    WindowsFileOpener,
    WindowsKnownFolders,
    hit_from,
    hit_from_url,
    newest_from_listing,
)
from sazed.skills.pc.files import KNOWN_FOLDERS, PROGRAM_EXTENSIONS


@pytest.mark.parametrize("ext", sorted(PROGRAM_EXTENSIONS))
def test_the_opener_refuses_a_program_even_if_the_skill_did_not(
    ext: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[str] = []
    monkeypatch.setattr(os, "startfile", started.append, raising=False)
    with pytest.raises(ValueError):
        WindowsFileOpener().open(f"C:/x/evil{ext}")
    assert started == []


def test_the_opener_opens_a_document(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    monkeypatch.setattr(os, "startfile", started.append, raising=False)
    WindowsFileOpener().open("C:/x/a.pdf")
    assert started == ["C:/x/a.pdf"]


def test_hit_from_a_path_names_the_file_and_its_folder() -> None:
    hit = hit_from(r"C:\Users\A\Downloads\a.pdf", datetime(2026, 10, 16))
    assert (hit.name, hit.folder) == ("a.pdf", "Downloads")


def test_an_index_url_becomes_a_real_path_with_the_display_folder() -> None:
    url = "file:C:/Users/A/Documents/meu relatório.docx"
    hit = hit_from_url(url, "Documentos", datetime(2026, 1, 1))
    assert hit.path == r"C:\Users\A\Documents\meu relatório.docx"
    assert (hit.name, hit.folder) == ("meu relatório.docx", "Documentos")


def test_newest_from_listing_sorts_filters_and_limits() -> None:
    t = datetime(2026, 10, 16, 12).timestamp()
    entries = [("C:/d/a.txt", t - 10), ("C:/d/b.txt", t), ("C:/d/old.txt", t - 86400 * 2)]
    hits = newest_from_listing(entries, datetime(2026, 10, 15), 5)
    assert [h.name for h in hits] == ["b.txt", "a.txt"]
    assert [h.name for h in newest_from_listing(entries, None, 1)] == ["b.txt"]


def test_known_folders_use_the_shell_and_config_overrides(tmp_path: Path) -> None:
    shell = {"Downloads": str(tmp_path)}
    projetos = tmp_path / "p"
    projetos.mkdir()
    folders = WindowsKnownFolders(
        {"Projetos": projetos, "Sumida": tmp_path / "nao-existe"}, lookup=shell.get
    )
    assert list(folders.names()) == [*KNOWN_FOLDERS, "Projetos", "Sumida"]
    assert folders.resolve("Downloads") == str(tmp_path)
    assert folders.resolve("Projetos") == str(projetos)
    assert folders.resolve("Sumida") is None
    assert folders.resolve("Vídeos") is None  # the shell did not know it


def test_a_configured_folder_with_a_known_name_overrides_it(tmp_path: Path) -> None:
    folders = WindowsKnownFolders({"downloads": tmp_path}, lookup=lambda name: "C:/elsewhere")
    assert folders.resolve("Downloads") == str(tmp_path)
    assert list(folders.names()) == list(KNOWN_FOLDERS)
