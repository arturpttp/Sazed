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
