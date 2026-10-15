"""Match a Settings page name. Pure; same scoring as app names."""

from collections.abc import Sequence

from sazed.core.types import SlotValue, Unmatched
from sazed.nlu.normalize import normalize, strip_accents
from sazed.nlu.slots.app import MIN_SCORE, name_score

_STOP = frozenset(
    {
        "abre",
        "abra",
        "abrir",
        "mostra",
        "mostre",
        "mostrar",
        "configuracoes",
        "configuracao",
        "config",
        "ajustes",
        "painel",
        "de",
        "do",
        "da",
        "das",
        "dos",
        "o",
        "a",
        "as",
        "os",
        "windows",
        "quero",
        "mudar",
        "muda",
        "me",
        "pra",
        "para",
        "sazed",
        "pode",
        "por",
        "favor",
        "e",
        "no",
        "na",
    }
)


def _key(text: str) -> str:
    return strip_accents(normalize(text))


def extract_page(normalized: str, names: Sequence[str]) -> SlotValue | Unmatched | None:
    query = " ".join(t for t in _key(normalized).split() if t not in _STOP)
    if not query:
        return None
    exact = [n for n in names if _key(n) == query]
    if exact:
        return SlotValue("pagina", exact[0], query, 1.0)
    scored = sorted(((name_score(query, _key(n)), n) for n in names), key=lambda sn: -sn[0])
    best_score, best = scored[0] if scored else (0.0, "")
    if best_score < MIN_SCORE:
        return Unmatched("pagina", query, None)
    return SlotValue("pagina", best, query, best_score / 100, exact=False)
