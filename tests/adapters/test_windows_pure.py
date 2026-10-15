from sazed.adapters.windows.catalog import build_entries
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
