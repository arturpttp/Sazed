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
