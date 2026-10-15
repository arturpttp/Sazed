"""Match an app name in an utterance against the catalog and aliases. Pure."""

from collections.abc import Mapping, Sequence

from rapidfuzz import fuzz

from sazed.core.types import Ambiguous, Extraction, SlotValue, Unmatched
from sazed.nlu.normalize import normalize, strip_accents

MIN_SCORE = 80
SUGGEST_SCORE = 60
MARGIN = 3

COMMAND_WORDS = frozenset(
    [
        "abre",
        "abra",
        "abrir",
        "abri",
        "inicia",
        "inicie",
        "iniciar",
        "executa",
        "execute",
        "executar",
        "roda",
        "rode",
        "rodar",
        "liga",
        "ligar",
        "fecha",
        "feche",
        "fechar",
        "encerra",
        "encerre",
        "encerrar",
        "mata",
        "mate",
        "matar",
        "sai",
        "sair",
        "desliga",
        "desligar",
        "processo",
        "o",
        "a",
        "os",
        "as",
        "um",
        "uma",
        "do",
        "da",
        "dos",
        "das",
        "de",
        "no",
        "na",
        "pro",
        "pra",
        "para",
        "mim",
        "me",
        "por",
        "favor",
        "ai",
        "app",
        "aplicativo",
        "programa",
        "sazed",
        "pode",
        "poderia",
        "voce",
        "consegue",
        "quero",
        "que",
        "agora",
        "e",
    ]
)


def _key(text: str) -> str:
    return strip_accents(normalize(text))


def app_query(normalized: str) -> str:
    return " ".join(t for t in strip_accents(normalized).split() if t not in COMMAND_WORDS)


def _score(query: str, name_key: str) -> float:
    by_token = max((fuzz.ratio(query, token) for token in name_key.split()), default=0.0)
    return max(fuzz.token_set_ratio(query, name_key), by_token)


def extract_app(
    normalized: str, names: Sequence[str], aliases: Mapping[str, str]
) -> Extraction | None:
    query = app_query(normalized)
    if not query:
        return None

    known = set(names)
    alias_value = {_key(k): v for k, v in aliases.items()}.get(query)
    if alias_value is not None and alias_value in known:
        return SlotValue("app", alias_value, query, 1.0, exact=True)

    # token_set_ratio scores a contained name 100 ("whatsapp" in "whatsapp web"), so an
    # exact name must be decided before fuzzy scoring or it ties with every longer name.
    exact = [n for n in names if _key(n) == query]
    if len(exact) == 1:
        return SlotValue("app", exact[0], query, 1.0, exact=True)

    scored = sorted(((_score(query, _key(n)), n) for n in names), key=lambda sn: (-sn[0], sn[1]))
    if not scored:
        return Unmatched("app", query, None)
    best = scored[0][0]
    if best < MIN_SCORE:
        suggestion = scored[0][1] if best >= SUGGEST_SCORE else None
        return Unmatched("app", query, suggestion)
    top = tuple(n for s, n in scored if s >= best - MARGIN)
    if len(top) > 1:
        return Ambiguous("app", query, top[:5])
    return SlotValue("app", top[0], query, best / 100, exact=best == 100)
