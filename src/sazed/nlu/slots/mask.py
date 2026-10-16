"""Replace the words that named a thing with a placeholder before a phrase is learned. Pure.

e5 weighs the object over the verb: a learned phrase that kept "projetos" would pull every
other command about that folder toward the learned intent.
"""

from collections.abc import Collection

from sazed.nlu.normalize import strip_accents
from sazed.nlu.slots.app import COMMAND_WORDS


def mask_words(normalized: str, words: Collection[str], placeholder: str) -> str:
    """Replace the span from the first to the last named word ("gastos de outubro")."""
    named = {strip_accents(w) for w in words} - COMMAND_WORDS
    tokens = normalized.split()
    hits = [i for i, t in enumerate(tokens) if strip_accents(t) in named]
    if not hits:
        return normalized
    before, after = tokens[: hits[0]], tokens[hits[-1] + 1 :]
    middle = [] if before and before[-1] == placeholder else [placeholder]
    return " ".join(before + middle + after)
