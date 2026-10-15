"""Text normalisation. Accents are kept for the embedder and stripped only for matching."""

import re
import unicodedata

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str) -> str:
    return " ".join(_PUNCTUATION.sub(" ", text.lower()).split())


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))
