"""In-memory ports. Tests assert their state, not only the response text."""

from collections.abc import Sequence

from sazed.skills.pc.apps import AppEntry


class FakeCatalog:
    def __init__(self, names: Sequence[str]) -> None:
        self._entries = [AppEntry(n, f"C:/Apps/{n}.exe", f"C:/Start/{n}.lnk") for n in names]

    def entries(self) -> Sequence[AppEntry]:
        return list(self._entries)


class FakeLauncher:
    def __init__(
        self, running: dict[str, int] | None = None, fail_with: Exception | None = None
    ) -> None:
        self.running: dict[str, int] = dict(running or {})
        self.launched: list[str] = []
        self.closed: list[str] = []
        self.fail_with = fail_with

    def launch(self, entry: AppEntry) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.launched.append(entry.name)
        self.running[entry.name] = self.running.get(entry.name, 0) + 1

    def instances(self, entry: AppEntry) -> int:
        return self.running.get(entry.name, 0)

    def close(self, entry: AppEntry) -> int:
        self.closed.append(entry.name)
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
