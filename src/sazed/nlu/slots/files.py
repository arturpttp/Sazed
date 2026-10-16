"""Read a folder name, a file name and a file type from a command. Pure."""

from collections.abc import Mapping, Sequence

from sazed.core.types import SlotValue, Unmatched
from sazed.nlu.normalize import normalize, strip_accents
from sazed.nlu.slots.app import MIN_SCORE, name_score

_VERBS = frozenset(
    [
        "abre",
        "abra",
        "abrir",
        "acha",
        "ache",
        "achar",
        "encontra",
        "encontre",
        "encontrar",
        "localiza",
        "localize",
        "localizar",
        "procura",
        "procure",
        "procurar",
        "mostra",
        "mostre",
        "mostrar",
    ]
)
_FILLERS = frozenset(
    [
        "o",
        "a",
        "os",
        "as",
        "um",
        "uma",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "meu",
        "minha",
        "meus",
        "minhas",
        "pra",
        "para",
        "mim",
        "me",
        "por",
        "favor",
        "ai",
        "aquele",
        "aquela",
        "chamado",
        "chamada",
        "sazed",
        "e",
        "no",
        "na",
        "agora",
    ]
)
KIND_WORDS: dict[str, str] = {
    "planilha": "planilha",
    "planilhas": "planilha",
    "excel": "planilha",
    "pdf": "pdf",
    "documento": "documento",
    "doc": "documento",
    "word": "documento",
    "apresentacao": "apresentacao",
    "slides": "apresentacao",
    "powerpoint": "apresentacao",
    "foto": "foto",
    "fotos": "foto",
    "imagem": "foto",
    "video": "video",
    "videos": "video",
    "musica": "musica",
    "audio": "musica",
    "texto": "texto",
    "txt": "texto",
}
_FILE_STOP = _VERBS | _FILLERS | {"arquivo", "arquivos"} | frozenset(KIND_WORDS)
_FOLDER_STOP = (
    _VERBS
    | _FILLERS
    | frozenset(["pasta", "pastas", "ultimo", "ultima", "ultimos", "recente", "recentes"])
)


def _key(text: str) -> str:
    return strip_accents(normalize(text))


def _folder_query(text: str) -> str:
    return " ".join(t for t in _key(text).split() if t not in _FOLDER_STOP)


def extract_folder(
    normalized: str, names: Sequence[str], synonyms: Mapping[str, str]
) -> SlotValue | Unmatched | None:
    query = _folder_query(normalized)
    if not query:
        return None
    for synonym, name in synonyms.items():
        if _folder_query(synonym) == query and name in names:
            return SlotValue("pasta", name, query, 1.0)
    exact = [n for n in names if _folder_query(n) == query]
    if exact:
        return SlotValue("pasta", exact[0], query, 1.0)
    # A name inside a longer phrase ("o último print que eu tirei"): longest name first.
    tokens = query.split()
    keyed = [(_folder_query(s), n) for s, n in synonyms.items() if n in names]
    keyed += [(_folder_query(n), n) for n in names]
    for key, name in sorted(keyed, key=lambda kn: -len(kn[0].split())):
        words = key.split()
        if words and any(
            tokens[i : i + len(words)] == words for i in range(len(tokens) - len(words) + 1)
        ):
            return SlotValue("pasta", name, key, 1.0)
    scored = sorted(((name_score(query, _key(n)), n) for n in names), key=lambda sn: -sn[0])
    if not scored or scored[0][0] < MIN_SCORE:
        return Unmatched("pasta", query, None)
    return SlotValue("pasta", scored[0][1], query, scored[0][0] / 100, exact=False)


def extract_kind(normalized: str) -> SlotValue | None:
    for token in strip_accents(normalized).split():
        if token in KIND_WORDS:
            return SlotValue("tipo", KIND_WORDS[token], token, 1.0)
    return None


def extract_file(normalized: str) -> SlotValue | None:
    """The words naming the file, accents kept (they are shown and searched as typed)."""
    words = [t for t in normalized.split() if strip_accents(t) not in _FILE_STOP]
    if not words:
        return None
    name = " ".join(words)
    return SlotValue("arquivo", name, name, 1.0)
