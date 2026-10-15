"""In-memory ports. Tests assert their state, not only the response text."""

from collections.abc import Sequence

from sazed.skills.pc.apps import AppEntry
from sazed.skills.pc.media import NowPlayingInfo


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
        from sazed.adapters.windows.screen import unique_name

        name = unique_name(file_name, self.existing)
        self.existing.add(name)
        self.saved.append(name)
        return name

    def open_snip(self) -> None:
        self.snips += 1
