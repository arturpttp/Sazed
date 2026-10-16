"""The coppermind: persistent learned examples, aliases and episodes. Port only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from sazed.core.types import Ranking


class LearnedKind(Enum):
    EXAMPLE = "example"
    ALIAS = "alias"


@dataclass(frozen=True)
class LearnedItem:
    kind: LearnedKind
    id: int
    text: str
    target: str
    slot: str | None
    created_at: datetime


@dataclass(frozen=True)
class NewExample:
    text: str
    intent_id: str
    embedding: bytes
    origin: str


@dataclass(frozen=True)
class NewAlias:
    slot: str
    alias: str
    value: str


@dataclass(frozen=True)
class StoredExample:
    id: int
    text: str
    intent_id: str
    embedding: bytes


@dataclass(frozen=True)
class StoredAlias:
    id: int
    slot: str
    alias: str
    value: str


class Reaction(Enum):
    NONE = "none"
    CONFIRMED = "confirmed"
    DENIED = "denied"
    CORRECTED = "corrected"


@dataclass(frozen=True)
class Episode:
    utterance: str
    at: datetime
    ranking: Ranking
    slots: Mapping[str, str]
    decision: str
    intent_id: str | None
    outcome: str
    reaction: Reaction = Reaction.NONE


@dataclass(frozen=True)
class StoredEpisode:
    id: int
    episode: Episode


class NoteTarget(Enum):
    """What a note is attached to. Notes are for the user; Sazed itself never reads them."""

    EXAMPLE = "example"
    ALIAS = "alias"
    EPISODE = "episode"


@dataclass(frozen=True)
class Note:
    id: int
    target: NoteTarget
    target_id: int
    text: str
    created_at: datetime
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Snapshot:
    """Everything needed to put a forgotten item back exactly: its row and its notes."""

    kind: LearnedKind
    row: tuple[object, ...]
    notes: tuple[Note, ...]


class Coppermind(Protocol):
    def learn(
        self, examples: Sequence[NewExample], aliases: Sequence[NewAlias], now: datetime
    ) -> list[LearnedItem]: ...
    def examples(self) -> list[StoredExample]: ...
    def aliases(self) -> list[StoredAlias]: ...
    def learned(self) -> list[LearnedItem]: ...
    def forget(self, kind: LearnedKind, item_id: int) -> LearnedItem | None: ...
    def forget_latest(self) -> list[LearnedItem]: ...
    def record_episode(self, episode: Episode) -> int: ...
    def set_reaction(self, episode_id: int, reaction: Reaction) -> None: ...
    def episodes(self, limit: int) -> list[StoredEpisode]: ...
    def episode(self, episode_id: int) -> StoredEpisode | None: ...
    def recent_failures(self, limit: int) -> list[StoredEpisode]: ...
