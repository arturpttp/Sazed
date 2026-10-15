import pytest

from sazed.adapters.windows.catalog import build_entries, is_excluded
from sazed.adapters.windows.launcher import WindowInfo, entry_matcher, root_pids, windows_to_close
from sazed.adapters.windows.opener import is_allowed_uri
from sazed.adapters.windows.store import build_store_entries
from sazed.skills.pc.apps import AppEntry


def lnk(target: str):  # type: ignore[no-untyped-def]
    return entry_matcher(AppEntry("X", target, "x.lnk"))


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
    assert root_pids(processes, lnk(chrome)) == [100, 200]


def test_squirrel_launcher_targets_match_the_real_app_under_their_folder() -> None:
    update = r"C:\Users\a\AppData\Local\Discord\Update.exe"
    processes = [
        (10, 1, r"C:\Users\a\AppData\Local\Discord\app-1.0.9\Discord.exe"),
        (11, 10, r"C:\Users\a\AppData\Local\Discord\app-1.0.9\Discord.exe"),
        (20, 1, r"C:\Users\a\AppData\Local\Other\Other.exe"),
    ]
    assert root_pids(processes, lnk(update)) == [10]


def test_ordinary_targets_do_not_match_neighbours_in_their_folder() -> None:
    charmap = r"C:\Windows\System32\charmap.exe"
    processes = [(10, 1, r"C:\Windows\System32\notepad.exe"), (11, 1, charmap)]
    assert root_pids(processes, lnk(charmap)) == [11]


@pytest.mark.parametrize(
    "name",
    ["Desinstalação do Foo", "Desinstalar Bar", "Uninstall Baz", "Leia-me", "Ajuda do Qux"],
)
def test_uninstallers_and_docs_are_excluded(name: str) -> None:
    assert is_excluded(name)


def test_a_normal_app_is_not_excluded() -> None:
    assert not is_excluded("Visual Studio Code")


CALC_FOLDER = (
    r"C:\Program Files\WindowsApps\Microsoft.WindowsCalculator_11.2607.0.0_x64__8wekyb3d8bbwe"
)


def test_store_entries_come_from_package_app_ids_only() -> None:
    items = [
        ("Calculator", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
        ("Google Chrome", "Chrome"),
        ("Configurar Java", r"{6D809377-6AF0-444B-8957-A3773F02200E}\Java\bin\javacpl.exe"),
        ("Desinstalar Foo", "Foo.Bar_1234567890abc!App"),
    ]
    folders = {"Microsoft.WindowsCalculator_8wekyb3d8bbwe": CALC_FOLDER}
    assert build_store_entries(items, folders.get) == [
        AppEntry(
            "Calculator",
            CALC_FOLDER,
            "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
            "store",
        )
    ]


def test_a_store_app_without_a_known_folder_can_still_be_opened() -> None:
    items = [("WhatsApp", "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App")]
    (entry,) = build_store_entries(items, lambda family: None)
    assert entry.target == ""
    assert entry.shortcut.endswith("!App")


def test_a_store_entry_matches_executables_inside_its_folder_only() -> None:
    matches = entry_matcher(AppEntry("Calculator", CALC_FOLDER, "shell:AppsFolder\\X!App", "store"))
    assert matches(CALC_FOLDER + r"\CalculatorApp.exe")
    assert not matches(CALC_FOLDER + "0" + r"\CalculatorApp.exe")  # a sibling folder
    assert not matches(r"C:\Windows\System32\ApplicationFrameHost.exe")
    assert not matches(None)


def test_a_store_entry_without_folder_matches_nothing() -> None:
    entry = AppEntry("W", "", "shell:AppsFolder\\W!App", "store")
    assert not entry_matcher(entry)(r"C:\x.exe")


def test_a_site_matches_no_process() -> None:
    site = AppEntry("YouTube", "https://youtube.com", "https://youtube.com", "site")
    assert not entry_matcher(site)(r"C:\Program Files\Vivaldi\vivaldi.exe")


def test_root_pids_takes_a_matcher() -> None:
    entry = AppEntry("Calculator", CALC_FOLDER, "shell:AppsFolder\\X!App", "store")
    procs = [(10, 1, CALC_FOLDER + r"\CalculatorApp.exe"), (11, 10, CALC_FOLDER + r"\Helper.exe")]
    assert root_pids(procs, entry_matcher(entry)) == [10]


def test_a_frame_window_hosting_the_app_is_closed() -> None:
    windows = [
        WindowInfo(hwnd=1, pid=900, child_pids=frozenset({900, 4376})),  # ApplicationFrameHost
        WindowInfo(hwnd=2, pid=900, child_pids=frozenset({900, 5000})),  # another UWP app
        WindowInfo(hwnd=3, pid=4376, child_pids=frozenset()),  # the app's own window
        WindowInfo(hwnd=4, pid=7, child_pids=frozenset()),
    ]
    assert windows_to_close(windows, {4376}) == [1, 3]


@pytest.mark.parametrize(
    "uri",
    [
        "https://www.youtube.com",
        "http://exemplo.com",
        "ms-settings:bluetooth",
        "ms-screenclip:",
        "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
    ],
)
def test_allowed_uris(uri: str) -> None:
    assert is_allowed_uri(uri)


@pytest.mark.parametrize(
    "uri", ["C:\\Windows\\System32\\cmd.exe", "file:///C:/x.bat", "calc", "javascript:alert(1)"]
)
def test_anything_else_is_refused(uri: str) -> None:
    assert not is_allowed_uri(uri)


def test_shutdown_and_restart_commands() -> None:
    from sazed.adapters.windows.power import power_command

    assert power_command("shutdown") == ["shutdown", "/s", "/t", "0"]
    assert power_command("restart") == ["shutdown", "/r", "/t", "0"]


def test_sign_out_command() -> None:
    from sazed.adapters.windows.power import power_command

    assert power_command("sign_out") == ["shutdown", "/l"]


def test_unknown_power_kind_is_refused() -> None:
    from sazed.adapters.windows.power import power_command

    with pytest.raises(ValueError):
        power_command("format_c")


def test_unique_name_never_overwrites() -> None:
    from sazed.adapters.windows.screen import unique_name

    assert unique_name("a.png", set()) == "a.png"
    assert unique_name("a.png", {"a.png"}) == "a (2).png"
    assert unique_name("a.png", {"a.png", "a (2).png"}) == "a (3).png"


def test_power_commands_never_force_apps_closed() -> None:
    # On Windows, any /t above 0 implies /f: apps would be killed without "save changes?".
    from sazed.adapters.windows.power import power_command

    for kind in ("shutdown", "restart", "sign_out"):
        command = power_command(kind)
        assert "/f" not in command
        if "/t" in command:
            assert command[command.index("/t") + 1] == "0"
