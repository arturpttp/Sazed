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
class MemoryStatus:
    free: str
    total: str


@dataclass(frozen=True)
class CpuStatus:
    percent: str


@dataclass(frozen=True)
class DiskStatus:
    disks: tuple[str, ...]


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


# Windows, folders and files (sub-project 2b)


@dataclass(frozen=True)
class WindowMinimized:
    app: str


@dataclass(frozen=True)
class WindowMaximized:
    app: str


@dataclass(frozen=True)
class WindowRestored:
    app: str


@dataclass(frozen=True)
class WindowFocused:
    app: str


@dataclass(frozen=True)
class WindowSnapped:
    app: str
    side: str


@dataclass(frozen=True)
class WindowMoved:
    app: str
    monitor: int


@dataclass(frozen=True)
class DesktopShown:
    pass


@dataclass(frozen=True)
class DesktopRestored:
    pass


@dataclass(frozen=True)
class FolderOpened:
    folder: str


@dataclass(frozen=True)
class FileOpened:
    name: str


@dataclass(frozen=True)
class ProgramRevealed:
    name: str


@dataclass(frozen=True)
class RecentFiles:
    count: int
    names: tuple[str, ...]


@dataclass(frozen=True)
class WindowNotFound:
    app: str
    offer_open: bool = False


@dataclass(frozen=True)
class NoWindow:
    pass


@dataclass(frozen=True)
class FocusRefused:
    app: str


@dataclass(frozen=True)
class NoSuchMonitor:
    number: int
    count: int


@dataclass(frozen=True)
class SingleMonitor:
    pass


@dataclass(frozen=True)
class SearchUnavailable:
    pass


@dataclass(frozen=True)
class FileNotFound:
    query: str
    kind: str


@dataclass(frozen=True)
class FolderNotFound:
    folder: str


@dataclass(frozen=True)
class FileGone:
    name: str


@dataclass(frozen=True)
class NothingRecent:
    pass


# File changes (sub-project 2c)


@dataclass(frozen=True)
class FileChangeProposed:
    action: str


@dataclass(frozen=True)
class FileMoved:
    name: str
    folder: str


@dataclass(frozen=True)
class FileCopied:
    name: str
    folder: str


@dataclass(frozen=True)
class FileRenamed:
    old: str
    new: str


@dataclass(frozen=True)
class FileRecycled:
    name: str


@dataclass(frozen=True)
class FolderCreated:
    name: str
    folder: str


@dataclass(frozen=True)
class ChangeUndone:
    action: str


@dataclass(frozen=True)
class Protected:
    name: str


@dataclass(frozen=True)
class IntoItself:
    name: str


@dataclass(frozen=True)
class BadName:
    name: str
    reason: str


@dataclass(frozen=True)
class NameTaken:
    name: str


@dataclass(frozen=True)
class PlanChanged:
    pass


@dataclass(frozen=True)
class FileBusy:
    action: str
    name: str


@dataclass(frozen=True)
class NoRecycleBin:
    name: str


@dataclass(frozen=True)
class NothingToUndo:
    pass


@dataclass(frozen=True)
class UndoStale:
    name: str


@dataclass(frozen=True)
class CopiedNotMoved:
    name: str
    folder: str


@dataclass(frozen=True)
class NotInRecycleBin:
    name: str


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
    | MemoryStatus
    | CpuStatus
    | DiskStatus
    | ExampleLearned
    | AliasLearned
    | AlreadyKnown
    | Forgotten
    | NothingToForget
    | NothingToRepeat
    | Cancelled
    | WindowMinimized
    | WindowMaximized
    | WindowRestored
    | WindowFocused
    | WindowSnapped
    | WindowMoved
    | DesktopShown
    | DesktopRestored
    | FolderOpened
    | FileOpened
    | ProgramRevealed
    | RecentFiles
    | FileChangeProposed
    | FileMoved
    | FileCopied
    | FileRenamed
    | FileRecycled
    | FolderCreated
    | ChangeUndone
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
    | WindowNotFound
    | NoWindow
    | FocusRefused
    | NoSuchMonitor
    | SingleMonitor
    | SearchUnavailable
    | FileNotFound
    | FolderNotFound
    | FileGone
    | NothingRecent
    | Protected
    | IntoItself
    | BadName
    | NameTaken
    | PlanChanged
    | FileBusy
    | NoRecycleBin
    | NothingToUndo
    | UndoStale
    | NotInRecycleBin
    | CopiedNotMoved
)
Outcome = Success | Failure

_FAILURE_TYPES: tuple[type, ...] = get_args(Failure)
FAILURE_NAMES: frozenset[str] = frozenset(t.__name__ for t in _FAILURE_TYPES)


def is_failure(outcome: object) -> bool:
    return isinstance(outcome, _FAILURE_TYPES)
