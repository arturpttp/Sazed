"""Read a web search: the query after the trigger verb, and an optional trailing engine. Pure.

The query comes from normalised text, so punctuation is already gone ("c++" → "c").
"""

from collections.abc import Sequence

from sazed.core.types import SlotValue
from sazed.nlu.normalize import normalize, strip_accents

_TRIGGERS = frozenset(
    {
        "pesquisa",
        "pesquise",
        "pesquisar",
        "procura",
        "procure",
        "procurar",
        "busca",
        "busque",
        "buscar",
        "googla",
        "googlar",
    }
)
_LEADING = (("pra", "mim"), ("para", "mim"), ("por",), ("sobre",))
_PLACES = ("no", "na", "pelo", "pela")


def _engine_suffix(stripped: list[str], engines: Sequence[str]) -> tuple[str, int] | None:
    """(engine name, tokens to drop) when the text ends in "no/na <engine>"."""
    for name in sorted(engines, key=len, reverse=True):
        key = strip_accents(normalize(name)).split()
        n = len(key) + 1
        if len(stripped) >= n and stripped[-n] in _PLACES and stripped[-n + 1 :] == key:
            return name, n
    return None


def extract_engine(normalized: str, engines: Sequence[str]) -> SlotValue | None:
    stripped = strip_accents(normalized).split()
    found = _engine_suffix(stripped, engines)
    if found is None:
        return None
    name, n = found
    return SlotValue("site", name, " ".join(stripped[-n + 1 :]), 1.0)


def extract_query(normalized: str, engines: Sequence[str]) -> SlotValue | None:
    tokens = normalized.split()
    stripped = strip_accents(normalized).split()
    suffix = _engine_suffix(stripped, engines)
    if suffix is not None:
        tokens, stripped = tokens[: -suffix[1]], stripped[: -suffix[1]]
    start = next((i + 1 for i, t in enumerate(stripped) if t in _TRIGGERS), 0)
    # No trigger: the whole text is the query (a bare answer to "O que devo pesquisar?").
    tokens, stripped = tokens[start:], stripped[start:]
    for lead in _LEADING:
        if tuple(stripped[: len(lead)]) == lead:
            tokens, stripped = tokens[len(lead) :], stripped[len(lead) :]
            break
    query = " ".join(tokens)
    return SlotValue("consulta", query, query, 1.0) if query else None
