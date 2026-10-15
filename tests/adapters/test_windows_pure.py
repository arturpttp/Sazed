import pytest

from sazed.adapters.windows.catalog import build_entries, is_excluded
from sazed.adapters.windows.launcher import root_pids
from sazed.skills.pc.apps import AppEntry


def test_build_entries_drops_uninstallers_docs_and_non_executables() -> None:
    entries = build_entries(
        [
            ("Spotify", r"C:\Apps\Spotify.exe", r"C:\Start\Spotify.lnk"),
            ("Desinstalar Spotify", r"C:\Apps\unins000.exe", r"C:\Start\u.lnk"),
            ("Uninstall Steam", r"C:\Steam\uninstall.exe", r"C:\Start\s.lnk"),
            ("Leia-me", r"C:\Apps\readme.txt", r"C:\Start\r.lnk"),
            ("Site oficial", "https://example.com", r"C:\Start\w.lnk"),
        ]
    )
    assert entries == [AppEntry("Spotify", r"C:\Apps\Spotify.exe", r"C:\Start\Spotify.lnk")]


def test_build_entries_keeps_the_first_of_duplicate_names_and_sorts() -> None:
    entries = build_entries(
        [
            ("Steam", r"C:\User\Steam.exe", r"C:\U\Steam.lnk"),
            ("discord", r"C:\D\Update.exe", r"C:\U\Discord.lnk"),
            ("steam", r"C:\All\Steam.exe", r"C:\A\Steam.lnk"),
        ]
    )
    assert [(e.name, e.target) for e in entries] == [
        ("discord", r"C:\D\Update.exe"),
        ("Steam", r"C:\User\Steam.exe"),
    ]


def test_root_pids_ignore_child_processes_of_the_same_app() -> None:
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    processes = [
        (100, 1, chrome),
        (101, 100, chrome),
        (102, 100, chrome),
        (200, 1, chrome.upper()),
        (300, 1, r"C:\Windows\explorer.exe"),
        (400, 1, None),
    ]
    assert root_pids(processes, chrome) == [100, 200]


def test_squirrel_launcher_targets_match_the_real_app_under_their_folder() -> None:
    update = r"C:\Users\a\AppData\Local\Discord\Update.exe"
    processes = [
        (10, 1, r"C:\Users\a\AppData\Local\Discord\app-1.0.9\Discord.exe"),
        (11, 10, r"C:\Users\a\AppData\Local\Discord\app-1.0.9\Discord.exe"),
        (20, 1, r"C:\Users\a\AppData\Local\Other\Other.exe"),
    ]
    assert root_pids(processes, update) == [10]


def test_ordinary_targets_do_not_match_neighbours_in_their_folder() -> None:
    charmap = r"C:\Windows\System32\charmap.exe"
    processes = [(10, 1, r"C:\Windows\System32\notepad.exe"), (11, 1, charmap)]
    assert root_pids(processes, charmap) == [11]


@pytest.mark.parametrize(
    "name",
    ["Desinstalação do Foo", "Desinstalar Bar", "Uninstall Baz", "Leia-me", "Ajuda do Qux"],
)
def test_uninstallers_and_docs_are_excluded(name: str) -> None:
    assert is_excluded(name)


def test_a_normal_app_is_not_excluded() -> None:
    assert not is_excluded("Visual Studio Code")
