"""Play/pause, skip and "what's playing" through the system media session."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sazed.core.outcomes import (
    MediaNext,
    MediaPrevious,
    MediaToggled,
    NoMediaSession,
    NowPlaying,
    Outcome,
)
from sazed.core.skill import IntentSpec, SkillContext
from sazed.core.types import Slots


@dataclass(frozen=True)
class NowPlayingInfo:
    title: str
    artist: str


class MediaControl(Protocol):
    """False / None: there is no media session (nothing playing or paused anywhere)."""

    def toggle(self) -> bool: ...
    def next(self) -> bool: ...
    def previous(self) -> bool: ...
    def now_playing(self) -> NowPlayingInfo | None: ...


TOGGLE_EXAMPLES = (
    "pausa a música",
    "pausa o vídeo",
    "pausa",
    "continua a música",
    "despausa",
    "dá play",
    "play na música",
    "volta a tocar",
    "para a música",
    "retoma o vídeo",
)
NEXT_EXAMPLES = (
    "próxima música",
    "pula a música",
    "passa a música",
    "próxima faixa",
    "pula essa",
    "avança a música",
    "próximo vídeo",
    "pula pra próxima",
    "troca de música",
    "música seguinte",
)
PREVIOUS_EXAMPLES = (
    "música anterior",
    "volta a música",
    "faixa anterior",
    "volta uma música",
    "vídeo anterior",
    "toca a anterior",
    "volta pra música de antes",
    "põe a música anterior",
    "anterior",
    "retrocede a música",
)
NOW_EXAMPLES = (
    "o que está tocando",
    "que música é essa",
    "qual música está tocando",
    "que música está tocando",
    "qual é essa música",
    "o que tá tocando",
    "nome dessa música",
    "quem canta essa música",
    "que vídeo é esse",
    "qual o nome da música",
)


class MediaSkill:
    id = "media"

    def __init__(self, media: MediaControl) -> None:
        self._media = media
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "midia_tocar_pausar", TOGGLE_EXAMPLES, (), lambda s: "pausar ou continuar a mídia"
            ),
            IntentSpec(
                "midia_proxima",
                NEXT_EXAMPLES,
                (),
                lambda s: "passar para a próxima faixa",
                repeatable=True,
            ),
            IntentSpec(
                "midia_anterior",
                PREVIOUS_EXAMPLES,
                (),
                lambda s: "voltar para a faixa anterior",
                repeatable=True,
            ),
            IntentSpec("midia_tocando", NOW_EXAMPLES, (), lambda s: "dizer o que está tocando"),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id == "midia_tocando":
            info = self._media.now_playing()
            return NoMediaSession() if info is None else NowPlaying(info.title, info.artist)
        if intent_id == "midia_tocar_pausar":
            return MediaToggled() if self._media.toggle() else NoMediaSession()
        if intent_id == "midia_proxima":
            return MediaNext() if self._media.next() else NoMediaSession()
        if intent_id == "midia_anterior":
            return MediaPrevious() if self._media.previous() else NoMediaSession()
        raise ValueError(f"unknown intent {intent_id}")
