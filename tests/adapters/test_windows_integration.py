import time
from collections.abc import Callable
from pathlib import Path

import pytest

from sazed.adapters.windows.audio import PycawAudio
from sazed.adapters.windows.catalog import StartMenuCatalog
from sazed.adapters.windows.launcher import WindowsLauncher

pytestmark = pytest.mark.windows
CHARMAP = r"C:\Windows\System32\charmap.exe"


def wait_until(condition: Callable[[], bool], seconds: float = 8.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.2)
    return False


@pytest.fixture
def shortcut_dir(tmp_path: Path) -> Path:
    import win32com.client

    link = win32com.client.Dispatch("WScript.Shell").CreateShortcut(
        str(tmp_path / "Mapa Teste.lnk")
    )
    link.TargetPath = CHARMAP
    link.Save()
    return tmp_path


def test_catalog_resolves_a_shortcut(shortcut_dir: Path) -> None:
    (entry,) = StartMenuCatalog([shortcut_dir]).entries()
    assert entry.name == "Mapa Teste"
    assert entry.target.lower() == CHARMAP.lower()


def test_launch_counts_and_closes_a_real_app(shortcut_dir: Path) -> None:
    (entry,) = StartMenuCatalog([shortcut_dir]).entries()
    launcher = WindowsLauncher()
    assert launcher.instances(entry) == 0, "close Character Map before running this test"
    launcher.launch(entry)
    assert wait_until(lambda: launcher.instances(entry) == 1)
    assert wait_until(lambda: launcher.close(entry) >= 1 or launcher.instances(entry) == 0)
    assert wait_until(lambda: launcher.instances(entry) == 0)


def test_real_start_menu_has_apps() -> None:
    assert len(StartMenuCatalog().entries()) > 0


def test_volume_set_read_and_restore() -> None:
    audio = PycawAudio()
    original, was_muted = audio.get_volume(), audio.is_muted()
    try:
        audio.set_volume(37)
        assert audio.get_volume() == 37
        audio.set_muted(True)
        assert audio.is_muted() is True
    finally:
        audio.set_volume(original)
        audio.set_muted(was_muted)


def test_store_calculator_opens_and_closes() -> None:
    from sazed.adapters.windows.store import StoreCatalog

    entry = next(e for e in StoreCatalog().entries() if e.name == "Calculator")
    launcher = WindowsLauncher()
    launcher.launch(entry)
    try:
        assert wait_until(lambda: launcher.instances(entry) >= 1)
        assert launcher.close(entry) >= 1
        assert wait_until(lambda: launcher.instances(entry) == 0)
    finally:
        if launcher.instances(entry):
            launcher.close(entry)


def test_media_session_is_readable_and_toggling_twice_restores_it() -> None:
    from sazed.adapters.windows.media import WinRtMedia

    media = WinRtMedia()
    media.now_playing()  # must not raise, session or not
    if not media.toggle():
        pytest.skip("no media session open")
    time.sleep(1.0)
    assert media.toggle()  # back to how it was
