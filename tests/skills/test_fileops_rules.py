import pytest

from sazed.core.outcomes import Protected
from sazed.skills.pc.fileops import (
    INVALID_CHARACTERS,
    RESERVED_NAMES,
    Area,
    check_destination,
    check_source,
    free_name,
    is_inside,
    keep_extension,
    name_problem,
)

PROFILE = r"C:\Users\a"
KNOWN = [rf"{PROFILE}\Downloads", rf"{PROFILE}\Documents", rf"{PROFILE}\Desktop"]
PROJECTS = r"D:\Projetos"
LINKS = {
    rf"{PROFILE}\Documents\atalho": r"C:\Windows\System32",
    rf"{PROFILE}\Documents\fora": r"D:\outra coisa",
}


def fake_realpath(path: str) -> str:
    import ntpath

    path = ntpath.normpath(path)
    for link, target in LINKS.items():
        if path.lower() == link.lower() or path.lower().startswith(link.lower() + "\\"):
            return target + path[len(link) :]
    return path


AREA = Area(
    roots=(PROFILE, PROJECTS),
    fixed=(PROFILE, PROJECTS, *KNOWN),
    trees=(rf"{PROFILE}\AppData", r"C:\Programacao\JARVIS\Sazed"),
    realpath=fake_realpath,
)


@pytest.mark.parametrize(
    "path",
    [
        rf"{PROFILE}\Downloads\relatório.docx",
        rf"{PROFILE}\Documents\pasta\x.txt",
        rf"{PROFILE}\documents\X.TXT",  # case does not matter
        rf"{PROJECTS}\site\index.html",
        rf"{PROFILE}\Downloads\viagem",  # a folder inside a known folder
    ],
)
def test_items_inside_the_users_folders_may_change(path: str) -> None:
    assert check_source(path, AREA) is None


@pytest.mark.parametrize(
    "path",
    [
        *AREA.fixed,  # the roots and the known folders themselves
        *(p + "\\" for p in AREA.fixed),  # with a trailing separator
        *(p.upper() for p in AREA.fixed),  # in another case
        "C:\\",
        "D:",
        r"C:\Windows\notepad.exe",
        r"C:\Users\outro\Documents\x.txt",
        rf"{PROFILE}\AppData\Roaming\x.json",
        rf"{PROFILE}\appdata\local\Sazed\coppermind.db",
        r"C:\Programacao\JARVIS\Sazed\CLAUDE.md",
        rf"{PROFILE}\Documents\..\..\b\x.txt",  # .. walks out of the profile
        rf"{PROFILE}\Documents\atalho\cmd.exe",  # a junction pointing at System32
        rf"{PROFILE}\Documents\fora\x.txt",  # a link to another drive outside the area
    ],
)
def test_anything_else_is_protected(path: str) -> None:
    assert isinstance(check_source(path, AREA), Protected)


def test_known_folders_and_roots_are_valid_destinations() -> None:
    for folder in AREA.fixed:
        assert check_destination(folder, AREA) is None
    assert check_destination(rf"{PROFILE}\Downloads\viagem", AREA) is None


@pytest.mark.parametrize(
    "folder",
    [r"C:\Windows", rf"{PROFILE}\AppData\Local", r"C:\Programacao\JARVIS\Sazed\src", "C:\\"],
)
def test_protected_trees_are_never_destinations(folder: str) -> None:
    assert isinstance(check_destination(folder, AREA), Protected)


SUBST_LINKS = {
    r"S:": r"C:\unidade",  # a subst drive
    rf"{PROFILE}\dados-sazed": rf"{PROFILE}\Documents\sazed",  # Sazed's data through a junction
}


def subst_realpath(path: str) -> str:
    import ntpath

    path = ntpath.normpath(path)
    for link, target in SUBST_LINKS.items():
        if path.lower() == link.lower() or path.lower().startswith(link.lower() + "\\"):
            return target + path[len(link) :]
    return path


# The area names folders as configured; the rules see where they really are.
LINKED_AREA = Area(
    roots=(PROFILE, r"S:\alvo"),
    fixed=(PROFILE, r"S:\alvo", *KNOWN),
    trees=(rf"{PROFILE}\AppData", rf"{PROFILE}\dados-sazed"),
    realpath=subst_realpath,
)


def test_a_folder_configured_through_a_subst_drive_is_a_destination_and_holds_sources() -> None:
    assert check_destination(r"S:\alvo", LINKED_AREA) is None
    assert check_source(r"S:\alvo\x.txt", LINKED_AREA) is None
    assert isinstance(check_source(r"S:\alvo", LINKED_AREA), Protected)  # still fixed itself


def test_a_tree_named_through_a_link_still_protects_what_is_really_inside_it() -> None:
    inside = rf"{PROFILE}\Documents\sazed\coppermind.db"
    assert isinstance(check_source(inside, LINKED_AREA), Protected)
    assert isinstance(check_destination(rf"{PROFILE}\Documents\sazed", LINKED_AREA), Protected)


def test_is_inside_is_strict_and_separator_aware() -> None:
    assert is_inside(r"C:\a\b", r"C:\a")
    assert not is_inside(r"C:\a", r"C:\a")
    assert not is_inside(r"C:\ab\c", r"C:\a")


@pytest.mark.parametrize("name", ["", "   "])
def test_an_empty_name_is_refused(name: str) -> None:
    assert name_problem(name) is not None


@pytest.mark.parametrize("char", sorted(INVALID_CHARACTERS))
def test_every_invalid_character_is_refused(char: str) -> None:
    assert name_problem(f"a{char}b") is not None


@pytest.mark.parametrize("name", sorted(RESERVED_NAMES))
def test_reserved_names_are_refused_with_and_without_extension(name: str) -> None:
    assert name_problem(name.lower()) is not None
    assert name_problem(f"{name}.txt") is not None


@pytest.mark.parametrize("name", ["nome.", "nome ", "a\tb"])
def test_trailing_dot_space_and_control_characters_are_refused(name: str) -> None:
    assert name_problem(name) is not None


@pytest.mark.parametrize("name", ["Contrato Assinado", "relatório-2025 (final).pdf", "console"])
def test_good_names_pass(name: str) -> None:
    assert name_problem(name) is None


def test_free_name_numbers_files_folders_and_ignores_case() -> None:
    assert free_name("a.docx", set()) == "a.docx"
    assert free_name("a.docx", {"A.DOCX"}) == "a (2).docx"
    assert free_name("a.docx", {"a.docx", "a (2).docx"}) == "a (3).docx"
    assert free_name("viagem", {"viagem"}) == "viagem (2)"  # no extension
    assert free_name(".gitignore", {".gitignore"}) == ".gitignore (2)"


def test_rename_keeps_the_extension_once() -> None:
    assert keep_extension("contrato.pdf", "contrato assinado", is_dir=False) == (
        "contrato assinado.pdf"
    )
    assert keep_extension("contrato.pdf", "final.PDF", is_dir=False) == "final.PDF"
    assert keep_extension("viagem", "viagem 2025", is_dir=True) == "viagem 2025"
    assert keep_extension("notas", "notas velhas", is_dir=False) == "notas velhas"
