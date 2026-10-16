"""In-memory ports. Tests assert their state, not only the response text."""

import unicodedata
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from sazed.runtime.skills import PcPorts
from sazed.skills.pc.apps import AppEntry
from sazed.skills.pc.files import FileHit, SearchError
from sazed.skills.pc.media import NowPlayingInfo
from sazed.skills.pc.windows import Monitor, Rect, WindowRef


class FakeCatalog:
    def __init__(self, names: Sequence[str]) -> None:
        self._entries = [AppEntry(n, f"C:/Apps/{n}.exe", f"C:/Start/{n}.lnk") for n in names]

    def entries(self) -> Sequence[AppEntry]:
        return list(self._entries)


class FakeLauncher:
    def __init__(
        self,
        running: dict[str, int] | None = None,
        fail_with: Exception | None = None,
        unclosable: set[str] | None = None,
    ) -> None:
        self.running: dict[str, int] = dict(running or {})
        self.launched: list[str] = []
        self.closed: list[str] = []
        self.fail_with = fail_with
        self.unclosable = set(unclosable or ())

    def launch(self, entry: AppEntry) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.launched.append(entry.name)
        self.running[entry.name] = self.running.get(entry.name, 0) + 1

    def instances(self, entry: AppEntry) -> int:
        return self.running.get(entry.name, 0)

    def close(self, entry: AppEntry) -> int:
        self.closed.append(entry.name)
        if entry.name in self.unclosable:
            return 0
        return self.running.pop(entry.name, 0)


class FakeAudio:
    def __init__(self, volume: int = 50, muted: bool = False) -> None:
        self.volume = volume
        self.muted = muted

    def get_volume(self) -> int:
        return self.volume

    def set_volume(self, percent: int) -> None:
        self.volume = percent

    def set_muted(self, muted: bool) -> None:
        self.muted = muted


class FakeOpener:
    def __init__(self) -> None:
        self.opened: list[str] = []

    def open(self, uri: str) -> None:
        self.opened.append(uri)


class FakeMedia:
    def __init__(self, session: bool = True, info: NowPlayingInfo | None = None) -> None:
        self.session = session
        self.info = info
        self.calls: list[str] = []

    def _call(self, name: str) -> bool:
        if self.session:
            self.calls.append(name)
        return self.session

    def toggle(self) -> bool:
        return self._call("toggle")

    def next(self) -> bool:
        return self._call("next")

    def previous(self) -> bool:
        return self._call("previous")

    def now_playing(self) -> NowPlayingInfo | None:
        return self.info if self.session else None


class FakePower:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def lock(self) -> None:
        self.calls.append("lock")

    def shutdown(self) -> None:
        self.calls.append("shutdown")

    def restart(self) -> None:
        self.calls.append("restart")

    def sleep(self) -> None:
        self.calls.append("sleep")

    def sign_out(self) -> None:
        self.calls.append("sign_out")


class FakeScreen:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = set(existing or ())
        self.saved: list[str] = []
        self.snips = 0

    def capture(self, file_name: str) -> str:
        from sazed.skills.pc.fileops import free_name as unique_name

        name = unique_name(file_name, self.existing)
        self.existing.add(name)
        self.saved.append(name)
        return name

    def open_snip(self) -> None:
        self.snips += 1


class FakeBrightness:
    def __init__(self, level: int | None = 50, accepts: bool = True) -> None:
        self.level = level
        self.accepts = accepts

    def get(self) -> int | None:
        return self.level

    def set(self, percent: int) -> bool:
        if not self.accepts or self.level is None:
            return False
        self.level = percent
        return True


class FakeStatus:
    def __init__(
        self,
        memory: tuple[int, int] = (0, 1),
        cpu: float = 0.0,
        disks: list[tuple[str, int, int]] | None = None,
    ) -> None:
        self._memory, self._cpu, self._disks = memory, cpu, list(disks or [])

    def memory(self) -> tuple[int, int]:
        return self._memory

    def cpu_percent(self) -> float:
        return self._cpu

    def disks(self) -> list[tuple[str, int, int]]:
        return list(self._disks)


def fake_pc_ports(
    names: Sequence[str],
    *,
    launcher: FakeLauncher | None = None,
    audio: FakeAudio | None = None,
) -> PcPorts:
    return PcPorts(
        catalog=FakeCatalog(names),
        launcher=launcher or FakeLauncher(),
        audio=audio or FakeAudio(),
        media=FakeMedia(),
        power=FakePower(),
        screen=FakeScreen(),
        brightness=FakeBrightness(),
        opener=FakeOpener(),
        status=FakeStatus(),
        windows=FakeWindows({}, [Monitor(1, Rect(0, 0, 1920, 1040), True)]),
        folders=FakeFolders({}),
        files=FakeSearch([]),
        file_opener=FakeFileOpener(set()),
    )


class FakeWindows:
    """Windows per app name (None: every user window), frontmost first."""

    def __init__(
        self,
        windows: dict[str | None, list[WindowRef]],
        monitors: list[Monitor],
        *,
        focus_ok: bool = True,
    ) -> None:
        self._windows = {k: list(v) for k, v in windows.items()}
        self._monitors = list(monitors)
        self.focus_ok = focus_ok
        self.calls: list[tuple[str, int]] = []
        self.desktop_shown = False

    def windows(self, entry: AppEntry | None) -> list[WindowRef]:
        return list(self._windows.get(None if entry is None else entry.name, []))

    def monitors(self) -> list[Monitor]:
        return list(self._monitors)

    def _update(self, hwnd: int, **changes: object) -> None:
        for key, refs in self._windows.items():
            self._windows[key] = [replace(r, **changes) if r.hwnd == hwnd else r for r in refs]  # type: ignore[arg-type]

    def minimize(self, hwnd: int) -> None:
        self.calls.append(("minimize", hwnd))
        self._update(hwnd, state="minimized")

    def maximize(self, hwnd: int) -> None:
        self.calls.append(("maximize", hwnd))
        self._update(hwnd, state="maximized")

    def restore(self, hwnd: int) -> None:
        self.calls.append(("restore", hwnd))
        self._update(hwnd, state="normal")

    def focus(self, hwnd: int) -> bool:
        self.calls.append(("focus", hwnd))
        return self.focus_ok

    def place(self, hwnd: int, rect: Rect) -> None:
        self.calls.append(("place", hwnd))
        self._update(hwnd, rect=rect, state="normal")

    def show_desktop(self) -> None:
        self.desktop_shown = True

    def undo_show_desktop(self) -> None:
        self.desktop_shown = False


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


class FakeFolders:
    def __init__(self, folders: dict[str, str | None]) -> None:
        self._folders = dict(folders)

    def names(self) -> Sequence[str]:
        return list(self._folders)

    def resolve(self, name: str) -> str | None:
        return self._folders.get(name)


class FakeSearch:
    """Filters its hits the way the index does: every word in the name, accents ignored."""

    def __init__(self, hits: Sequence[FileHit], *, fail: bool = False) -> None:
        self._hits = sorted(hits, key=lambda h: h.modified, reverse=True)
        self.fail = fail
        self.calls: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def search(self, words: Sequence[str], extensions: Sequence[str], limit: int) -> list[FileHit]:
        self.calls.append((tuple(words), tuple(extensions)))
        if self.fail:
            raise SearchError("index off")
        found = [
            h
            for h in self._hits
            if all(_plain(w) in _plain(h.name) for w in words)
            and (not extensions or any(h.name.lower().endswith(e) for e in extensions))
        ]
        return found[:limit]

    def newest(self, folder: str, since: datetime | None, limit: int) -> list[FileHit]:
        if self.fail:
            raise SearchError("index off")
        found = [
            h
            for h in self._hits
            if h.path.rsplit("/", 1)[0] == folder and (since is None or h.modified >= since)
        ]
        return found[:limit]


class FakeFileOpener:
    def __init__(self, existing: set[str]) -> None:
        self._existing = set(existing)
        self.opened: list[str] = []
        self.revealed: list[str] = []

    def open(self, path: str) -> None:
        self.opened.append(path)

    def reveal(self, path: str) -> None:
        self.revealed.append(path)

    def exists(self, path: str) -> bool:
        return path in self._existing
