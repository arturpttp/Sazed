"""Read the level to end at: the number right after "para"/"pra"/"pro"/"até". Pure.

"abaixa o volume para 100" names a level, not a step: the user wants 100%, whatever the
current volume is. "aumenta o volume em 20" is a step and is left to the percent slot.
"""

from sazed.core.types import SlotValue
from sazed.nlu.normalize import strip_accents
from sazed.nlu.slots.percent import extract_percent

_TO = frozenset({"para", "pra", "pro", "ate"})
_ARTICLES = frozenset({"o", "a"})


def extract_target(normalized: str) -> SlotValue | None:
    tokens = strip_accents(normalized).split()
    for i, token in enumerate(tokens):
        if token not in _TO:
            continue
        rest = tokens[i + 1 :]
        if rest and rest[0] in _ARTICLES:
            rest = rest[1:]
        found = extract_percent(" ".join(rest))
        # The number must come right after the preposition: "aumenta 10 pra mim" is no level.
        if found is not None and " ".join(rest).startswith(found.raw):
            return SlotValue("alvo", found.value, found.raw, 1.0)
    return None
