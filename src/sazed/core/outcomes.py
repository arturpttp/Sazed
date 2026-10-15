"""What happened when a command ran. Failures are values, not exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import get_args


@dataclass(frozen=True)
class AppOpened:
    app: str


@dataclass(frozen=True)
class AppClosed:
    app: str


@dataclass(frozen=True)
class VolumeSet:
    percent: int


@dataclass(frozen=True)
class VolumeChanged:
    percent: int


@dataclass(frozen=True)
class Muted:
    pass


@dataclass(frozen=True)
class Unmuted:
    pass


@dataclass(frozen=True)
class MediaToggled:
    pass


@dataclass(frozen=True)
class MediaNext:
    pass


@dataclass(frozen=True)
class MediaPrevious:
    pass


@dataclass(frozen=True)
class NowPlaying:
    title: str
    artist: str


@dataclass(frozen=True)
class NoMediaSession:
    pass


@dataclass(frozen=True)
class Locked:
    pass


@dataclass(frozen=True)
class ShuttingDown:
    pass


@dataclass(frozen=True)
class Restarting:
    pass


@dataclass(frozen=True)
class Suspending:
    pass


@dataclass(frozen=True)
class SigningOut:
    pass


@dataclass(frozen=True)
class ScreenshotSaved:
    file_name: str


@dataclass(frozen=True)
class SnipOpened:
    pass


@dataclass(frozen=True)
class SettingsOpened:
    page: str


@dataclass(frozen=True)
class UnknownSettingsPage:
    raw: str


@dataclass(frozen=True)
class BrightnessSet:
    percent: int


@dataclass(frozen=True)
class BrightnessChanged:
    percent: int


@dataclass(frozen=True)
class BrightnessUnsupported:
    pass


@dataclass(frozen=True)
class SearchOpened:
    query: str
    engine: str


@dataclass(frozen=True)
class ExampleLearned:
    text: str


@dataclass(frozen=True)
class AliasLearned:
    alias: str
    value: str


@dataclass(frozen=True)
class AlreadyKnown:
    pass


@dataclass(frozen=True)
class Forgotten:
    description: str


@dataclass(frozen=True)
class NothingToForget:
    pass


@dataclass(frozen=True)
class NothingToRepeat:
    pass


@dataclass(frozen=True)
class Cancelled:
    pass


@dataclass(frozen=True)
class AppNotFound:
    query: str
    suggestion: str | None


@dataclass(frozen=True)
class AppNotRunning:
    app: str


@dataclass(frozen=True)
class CannotCloseSite:
    app: str


@dataclass(frozen=True)
class AmbiguousSlot:
    slot: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class ActionFailed:
    """An adapter failed. `action` is a pt-BR infinitive phrase, e.g. "abrir Google Chrome"."""

    action: str


@dataclass(frozen=True)
class InvalidPercent:
    """A number outside 0-100 was given for a level or a step."""

    raw: str


Success = (
    AppOpened
    | AppClosed
    | VolumeSet
    | VolumeChanged
    | Muted
    | Unmuted
    | SearchOpened
    | MediaToggled
    | MediaNext
    | MediaPrevious
    | NowPlaying
    | Locked
    | ShuttingDown
    | Restarting
    | Suspending
    | SigningOut
    | ScreenshotSaved
    | SnipOpened
    | SettingsOpened
    | BrightnessSet
    | BrightnessChanged
    | ExampleLearned
    | AliasLearned
    | AlreadyKnown
    | Forgotten
    | NothingToForget
    | NothingToRepeat
    | Cancelled
)
Failure = (
    AppNotFound
    | AppNotRunning
    | AmbiguousSlot
    | ActionFailed
    | InvalidPercent
    | CannotCloseSite
    | NoMediaSession
    | UnknownSettingsPage
    | BrightnessUnsupported
)
Outcome = Success | Failure

_FAILURE_TYPES: tuple[type, ...] = get_args(Failure)
FAILURE_NAMES: frozenset[str] = frozenset(t.__name__ for t in _FAILURE_TYPES)


def is_failure(outcome: object) -> bool:
    return isinstance(outcome, _FAILURE_TYPES)
