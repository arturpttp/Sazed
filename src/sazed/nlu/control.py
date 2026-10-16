"""Dialogue control phrases (yes, no, correction, forget, repeat, undo). Deterministic, pure.

Matching runs on accent-stripped text. Accent stripping preserves length for Latin text, so
the correction's `rest` is sliced from the original normalised text and keeps its accents.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from rapidfuzz import fuzz

from sazed.nlu.normalize import normalize, strip_accents


class ControlKind(Enum):
    CONFIRM = "confirm"
    DENY = "deny"
    CORRECT = "correct"
    FORGET = "forget"
    REPEAT = "repeat"
    UNDO = "undo"


@dataclass(frozen=True)
class Control:
    kind: ControlKind
    rest: str = ""


_CONFIRM = frozenset(
    {
        "sim",
        "pode",
        "pode sim",
        "isso",
        "isso mesmo",
        "claro",
        "confirmo",
        "confirma",
        "exato",
        "positivo",
        "sim por favor",
        "pode ser",
        "manda ver",
        "ok",
        "certo",
    }
)
_DENY = frozenset(
    {
        "nao",
        "nao obrigado",
        "negativo",
        "cancela",
        "cancelar",
        "deixa",
        "deixa pra la",
        "deixa para la",
        "melhor nao",
        "agora nao",
    }
)
_FORGET = frozenset({"esquece isso", "esqueca isso", "esquece", "esqueca", "pode esquecer"})
_UNDO = frozenset(
    {"desfaz isso", "desfaz", "desfazer", "volta atras", "desfaca isso", "desfaz o que voce fez"}
)
_REPEAT = frozenset({"de novo", "outra vez", "mais", "mais um pouco", "repete", "repita"})

# "não é o X" is deliberately absent: without punctuation it reads as a negation.
_CORRECT = re.compile(
    r"^(?:(?:nao\s+)?(?:eu\s+)?(?:quis|queria)\s+dizer\s+(?:o\s+|a\s+)?"
    r"|(?:nao\s+)?era\s+(?:pra\s+|para\s+)?(?:o\s+|a\s+)?"
    r"|e\s+(?:o|a)\s+)"
    r"(?P<rest>.+)$"
)

_ORDINALS = {
    "primeiro": 1,
    "primeira": 1,
    "segundo": 2,
    "segunda": 2,
    "terceiro": 3,
    "terceira": 3,
    "quarto": 4,
    "quarta": 4,
    "quinto": 5,
    "quinta": 5,
    "ultimo": -1,
    "ultima": -1,
}
_PICK_MIN = 85


def parse_control(normalized: str) -> Control | None:
    text = strip_accents(normalized)
    if text in _CONFIRM:
        return Control(ControlKind.CONFIRM)
    if text in _DENY:
        return Control(ControlKind.DENY)
    if text in _FORGET:
        return Control(ControlKind.FORGET)
    if text in _UNDO:
        return Control(ControlKind.UNDO)
    if text in _REPEAT:
        return Control(ControlKind.REPEAT)
    match = _CORRECT.match(text)
    if match:
        return Control(ControlKind.CORRECT, normalized[match.start("rest") :])
    return None


def pick_candidate(normalized: str, candidates: Sequence[str]) -> str | None:
    text = strip_accents(normalized)
    for token in text.split():
        if token.isdigit():
            n = int(token)
            return candidates[n - 1] if 1 <= n <= len(candidates) else None
        if token in _ORDINALS:
            n = _ORDINALS[token]
            if n == -1:
                return candidates[-1]
            return candidates[n - 1] if n <= len(candidates) else None
    scored = sorted(
        ((fuzz.token_set_ratio(text, strip_accents(normalize(c))), c) for c in candidates),
        key=lambda sc: -sc[0],
    )
    if not scored or scored[0][0] < _PICK_MIN:
        return None
    if len(scored) > 1 and scored[1][0] >= scored[0][0]:
        return None
    return scored[0][1]
