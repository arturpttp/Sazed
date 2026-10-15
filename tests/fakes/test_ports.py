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
