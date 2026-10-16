"""Read which side of the screen and which monitor a window command names. Pure."""

from sazed.core.types import SlotValue
from sazed.nlu.normalize import strip_accents

_SIDES = {
    "esquerda": "esquerda",
    "esquerdo": "esquerda",
    "direita": "direita",
    "direito": "direita",
}
_SCREEN_WORDS = frozenset({"monitor", "tela"})
_OTHER = frozenset({"outro", "outra"})
_ORDINALS = {"primeiro": 1, "primeira": 1, "segundo": 2, "segunda": 2, "terceiro": 3, "terceira": 3}


def extract_side(normalized: str) -> SlotValue | None:
    for token in strip_accents(normalized).split():
        if token in _SIDES:
            return SlotValue("lado", _SIDES[token], token, 1.0)
    return None


def extract_monitor(normalized: str) -> SlotValue | None:
    tokens = strip_accents(normalized).split()
    for i, token in enumerate(tokens):
        if token not in _SCREEN_WORDS:
            continue
        after = tokens[i + 1] if i + 1 < len(tokens) else ""
        before = tokens[i - 1] if i > 0 else ""
        if after.isdigit():
            return SlotValue("monitor", int(after), f"{token} {after}", 1.0)
        if before in _ORDINALS:
            return SlotValue("monitor", _ORDINALS[before], f"{before} {token}", 1.0)
        if before in _OTHER:
            return SlotValue("monitor", "outro", f"{before} {token}", 1.0)
    return None
