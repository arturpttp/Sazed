"""Mute or unmute? Unmute phrases are listed; anything else under volume_mudo mutes. Pure."""

from sazed.core.types import SlotValue
from sazed.nlu.normalize import strip_accents

_UNMUTE = (
    "tira do mudo",
    "tirar do mudo",
    "desmuta",
    "desmutar",
    "desmute",
    "volta o som",
    "volta o audio",
    "ativa o som",
    "ativa o audio",
    "liga o som",
    "liga o audio",
)


def extract_mute(normalized: str) -> SlotValue:
    text = strip_accents(normalized)
    unmute = next((p for p in _UNMUTE if p in text), None)
    if unmute is not None:
        return SlotValue("mudo", False, unmute, 1.0)
    return SlotValue("mudo", True, text, 1.0)
