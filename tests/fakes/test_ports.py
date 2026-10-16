import pytest

from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher


def test_catalog_builds_one_entry_per_name() -> None:
    names = [e.name for e in FakeCatalog(["Spotify", "Steam"]).entries()]
    assert names == ["Spotify", "Steam"]


def test_launch_records_and_counts_an_instance() -> None:
    (entry,) = FakeCatalog(["Spotify"]).entries()
    launcher = FakeLauncher()
    launcher.launch(entry)
    assert launcher.launched == ["Spotify"]
    assert launcher.instances(entry) == 1


def test_close_returns_instances_closed_and_clears_them() -> None:
    (entry,) = FakeCatalog(["Spotify"]).entries()
    launcher = FakeLauncher(running={"Spotify": 2})
    assert launcher.close(entry) == 2
    assert launcher.instances(entry) == 0
    assert launcher.closed == ["Spotify"]


def test_launcher_can_be_told_to_fail() -> None:
    (entry,) = FakeCatalog(["Spotify"]).entries()
    launcher = FakeLauncher(fail_with=OSError("boom"))
    with pytest.raises(OSError):
        launcher.launch(entry)
    assert launcher.launched == []


def test_audio_records_state() -> None:
    audio = FakeAudio(volume=40)
    audio.set_volume(70)
    audio.set_muted(True)
    assert (audio.get_volume(), audio.muted) == (70, True)


def test_launcher_can_hold_apps_that_ignore_close() -> None:
    (entry,) = FakeCatalog(["Spotify"]).entries()
    launcher = FakeLauncher(running={"Spotify": 1}, unclosable={"Spotify"})
    assert launcher.close(entry) == 0
    assert launcher.instances(entry) == 1


def test_fake_opener_records_what_was_opened() -> None:
    from fakes.ports import FakeOpener

    opener = FakeOpener()
    opener.open("https://a")
    opener.open("ms-settings:sound")
    assert opener.opened == ["https://a", "ms-settings:sound"]


def test_fake_media_records_calls_and_reports_no_session() -> None:
    from fakes.ports import FakeMedia
    from sazed.skills.pc.media import NowPlayingInfo

    media = FakeMedia(info=NowPlayingInfo("t", "a"))
    assert media.toggle() and media.next() and media.previous()
    assert media.calls == ["toggle", "next", "previous"]
    assert media.now_playing() == NowPlayingInfo("t", "a")
    silent = FakeMedia(session=False)
    assert not silent.toggle() and silent.now_playing() is None


def test_fake_power_records_calls() -> None:
    from fakes.ports import FakePower

    power = FakePower()
    power.lock()
    power.shutdown()
    assert power.calls == ["lock", "shutdown"]


def test_fake_screen_saves_unique_names_and_counts_snips() -> None:
    from fakes.ports import FakeScreen

    screen = FakeScreen(existing={"x.png"})
    assert screen.capture("x.png") == "x (2).png"
    screen.open_snip()
    assert screen.saved == ["x (2).png"] and screen.snips == 1


def test_fake_brightness() -> None:
    from fakes.ports import FakeBrightness

    b = FakeBrightness(40)
    assert b.get() == 40 and b.set(70) and b.level == 70
    assert FakeBrightness(None).get() is None
    refusing = FakeBrightness(40, accepts=False)
    assert not refusing.set(10) and refusing.level == 40


def test_fake_status_returns_what_it_was_given() -> None:
    from fakes.ports import FakeStatus

    status = FakeStatus(memory=(1, 2), cpu=3.0, disks=[("C:", 4, 5)])
    assert status.memory() == (1, 2) and status.cpu_percent() == 3.0
    assert status.disks() == [("C:", 4, 5)]


def test_fake_pc_ports_uses_the_given_fakes() -> None:
    from fakes.ports import FakeAudio, fake_pc_ports

    audio = FakeAudio(volume=7)
    ports = fake_pc_ports(["Spotify"], audio=audio)
    assert ports.audio is audio
    assert [e.name for e in ports.catalog.entries()] == ["Spotify"]


def _ref(hwnd: int, title: str = "x"):  # type: ignore[no-untyped-def]
    from sazed.skills.pc.windows import Rect, WindowRef

    return WindowRef(hwnd, title, "normal", Rect(0, 0, 100, 100), 1)


def test_fake_windows_lists_by_app_name_and_tracks_state() -> None:
    from fakes.ports import FakeWindows
    from sazed.skills.pc.windows import Monitor, Rect

    (entry,) = FakeCatalog(["Spotify"]).entries()
    fake = FakeWindows(
        {None: [_ref(1)], "Spotify": [_ref(2)]}, [Monitor(1, Rect(0, 0, 9, 9), True)]
    )
    assert [r.hwnd for r in fake.windows(None)] == [1]
    assert [r.hwnd for r in fake.windows(entry)] == [2]
    fake.minimize(2)
    assert fake.windows(entry)[0].state == "minimized"
    fake.maximize(2)
    assert fake.windows(entry)[0].state == "maximized"
    fake.place(2, Rect(1, 2, 3, 4))
    assert fake.windows(entry)[0].rect == Rect(1, 2, 3, 4)
    assert fake.windows(entry)[0].state == "normal"
    assert fake.calls == [("minimize", 2), ("maximize", 2), ("place", 2)]


def test_fake_windows_focus_can_be_refused() -> None:
    from fakes.ports import FakeWindows

    assert FakeWindows({}, [], focus_ok=False).focus(1) is False
    assert FakeWindows({}, []).focus(1) is True


def test_fake_search_filters_like_the_index_and_sorts_newest_first() -> None:
    from datetime import datetime

    from fakes.ports import FakeSearch
    from sazed.skills.pc.files import FileHit

    a = FileHit("C:/d/Relatório.docx", "Relatório.docx", "d", datetime(2026, 1, 1))
    b = FileHit("C:/d/relatorio.pdf", "relatorio.pdf", "d", datetime(2026, 1, 2))
    c = FileHit("C:/e/outro.pdf", "outro.pdf", "e", datetime(2026, 1, 3))
    search = FakeSearch([a, b, c])
    assert search.search(["relatorio"], [], 6) == [b, a]
    assert search.search(["relatorio"], [".pdf"], 6) == [b]
    assert search.newest("C:/d", datetime(2026, 1, 2), 5) == [b]
    assert search.calls[0] == (("relatorio",), ())


def test_fake_search_can_fail() -> None:
    import pytest

    from fakes.ports import FakeSearch
    from sazed.skills.pc.files import SearchError

    with pytest.raises(SearchError):
        FakeSearch([], fail=True).search(["x"], [], 6)


def test_fake_file_opener_records_and_knows_what_exists() -> None:
    from fakes.ports import FakeFileOpener

    opener = FakeFileOpener({"C:/a.pdf"})
    opener.open("C:/a.pdf")
    opener.reveal("C:/b.lnk")
    assert (opener.opened, opener.revealed) == (["C:/a.pdf"], ["C:/b.lnk"])
    assert opener.exists("C:/a.pdf") and not opener.exists("C:/b.lnk")


def test_fake_folders_resolve_and_list() -> None:
    from fakes.ports import FakeFolders

    folders = FakeFolders({"Downloads": "C:/d", "Projetos": None})
    assert list(folders.names()) == ["Downloads", "Projetos"]
    assert folders.resolve("Downloads") == "C:/d"
    assert folders.resolve("Projetos") is None
