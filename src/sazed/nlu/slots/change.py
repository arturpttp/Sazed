"""Read what a file change is about: the item, the destination folder, and a new name. Pure.

The item is encoded as one string, because skills may not import `nlu`:
"ultimo:<Folder>" (the newest file of a folder), "pasta:<words>" (a folder by name) or
"arquivo:<words>" (a file by name). `FileOpsSkill` decodes it.

Splitting item from destination: "pra/para/pro" always start the destination; "na/no/em" do
only when a folder follows (a known one, "a pasta …", or "lixo/lixeira"), so "reunião na
segunda" stays a file name.
"""

import re
from collections.abc import Mapping, Sequence

from sazed.core.types import SlotValue, Unmatched
from sazed.nlu.normalize import strip_accents
from sazed.nlu.slots.files import KIND_WORDS, extract_folder

_STRONG = frozenset({"pra", "para", "pro"})
_WEAK = frozenset({"na", "no", "em", "nos", "nas"})
_BIN = frozenset({"lixo", "lixeira"})
_VERBS = frozenset(
    [
        "move",
        "mova",
        "mover",
        "manda",
        "mande",
        "mandar",
        "leva",
        "leve",
        "levar",
        "transfere",
        "transfira",
        "transferir",
        "passa",
        "passe",
        "coloca",
        "coloque",
        "copia",
        "copie",
        "copiar",
        "duplica",
        "duplique",
        "renomeia",
        "renomeie",
        "renomear",
        "muda",
        "mude",
        "mudar",
        "troca",
        "troque",
        "apaga",
        "apague",
        "apagar",
        "deleta",
        "delete",
        "deletar",
        "exclui",
        "exclua",
        "excluir",
        "remove",
        "remova",
        "remover",
        "joga",
        "jogue",
        "jogar",
        "cria",
        "crie",
        "criar",
        "faz",
        "faca",
        "joga",
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
        "do",
        "da",
        "dos",
        "das",
        "de",
        "meu",
        "minha",
        "meus",
        "minhas",
        "mim",
        "me",
        "por",
        "favor",
        "ai",
        "aquele",
        "aquela",
        "esse",
        "essa",
        "este",
        "esta",
        "isso",
        "sazed",
        "e",
        "agora",
        "nome",
        "chamado",
        "chamada",
        "arquivo",
        "arquivos",
    ]
)
_LATEST = frozenset({"ultimo", "ultima", "mais", "recente", "novo", "nova"})
_DEFAULT_LATEST = "Downloads"


def _split_at_destination(
    tokens: list[str], names: Sequence[str], synonyms: Mapping[str, str]
) -> tuple[list[str], list[str]]:
    """(item tokens, destination tokens) — destination empty when there is none."""
    plain = [strip_accents(t) for t in tokens]
    for i in range(len(tokens) - 1, -1, -1):
        if plain[i] not in _STRONG and plain[i] not in _WEAK:
            continue
        tail = tokens[i + 1 :]
        tail_plain = plain[i + 1 :]
        if not tail:
            continue
        if plain[i] in _STRONG or _folderish(tail, tail_plain, names, synonyms):
            return tokens[:i], tail
    return tokens, []


def _folderish(
    tail: list[str], tail_plain: list[str], names: Sequence[str], synonyms: Mapping[str, str]
) -> bool:
    if set(tail_plain) & _BIN or "pasta" in tail_plain[:2]:
        return True
    return isinstance(extract_folder(" ".join(tail), names, synonyms), SlotValue)


def _content(tokens: list[str], extra_stop: frozenset[str] = frozenset()) -> list[str]:
    stop = _VERBS | _FILLERS | _WEAK | _STRONG | extra_stop
    return [t for t in tokens if strip_accents(t) not in stop]


def extract_item(
    normalized: str, folder_names: Sequence[str], synonyms: Mapping[str, str]
) -> SlotValue | None:
    item, _ = _split_at_destination(normalized.split(), folder_names, synonyms)
    words = _content(item)
    plain = [strip_accents(w) for w in words]
    if not words:
        return None
    if plain[0] in _LATEST:
        rest = [w for w, p in zip(words, plain, strict=True) if p not in _LATEST]
        found = extract_folder(" ".join(rest), folder_names, synonyms) if rest else None
        folder = str(found.value) if isinstance(found, SlotValue) else _DEFAULT_LATEST
        return SlotValue("item", f"ultimo:{folder}", " ".join(words), 1.0)
    if plain[0] in ("pasta", "pastas"):
        name = " ".join(words[1:])
        return SlotValue("item", f"pasta:{name}", name, 1.0) if name else None
    named = _content(words, frozenset(KIND_WORDS))
    if not named:
        return None
    name = " ".join(named)
    return SlotValue("item", f"arquivo:{name}", name, 1.0)


def extract_destination(
    normalized: str, folder_names: Sequence[str], synonyms: Mapping[str, str]
) -> SlotValue | Unmatched | None:
    _, tail = _split_at_destination(normalized.split(), folder_names, synonyms)
    plain = [strip_accents(t) for t in tail]
    if not tail or set(plain) & _BIN:
        return None
    found = extract_folder(" ".join(tail), folder_names, synonyms)
    if isinstance(found, SlotValue):
        return SlotValue("destino", found.value, found.raw, found.confidence)
    words = [t for t, p in zip(tail, plain, strict=True) if p not in _FILLERS and p != "pasta"]
    if not words:
        return None
    return Unmatched("destino", " ".join(words), None)


_NAME_MARK = re.compile(r"\b(chamad[ao]|pra|para|como)\s+", re.IGNORECASE)
_FOLDER_WORD = re.compile(r"\bpasta\s+", re.IGNORECASE)
_TRAILING = " .!?\"'“”‘’"


def extract_new_name(
    raw: str, folder_names: Sequence[str], synonyms: Mapping[str, str]
) -> SlotValue | None:
    """The new name as typed (case, accents, punctuation kept), from the original text."""
    mark = _NAME_MARK.search(raw)
    if mark is None:
        mark = _FOLDER_WORD.search(raw)  # "cria uma pasta Orçamentos"
    if mark is None:
        return None
    rest = raw[mark.end() :]
    tokens = rest.split()
    plain = [strip_accents(t.lower().strip(_TRAILING)) for t in tokens]
    # A destination after a weak marker ends the name ("Viagem na área de trabalho").
    for i in range(len(tokens) - 1, 0, -1):
        if plain[i] in _WEAK | _STRONG:
            tail = [p for p in plain[i + 1 :] if p]
            if tail and _folderish(tail, tail, folder_names, synonyms):
                tokens = tokens[:i]
                break
    name = " ".join(tokens).strip(_TRAILING)
    if not name:
        return None
    return SlotValue("novo_nome", name, name, 1.0)


def bare_name(raw: str) -> SlotValue | None:
    """A bare answer to "Qual nome?": the whole text is the name."""
    name = raw.strip(_TRAILING)
    return SlotValue("novo_nome", name, name, 1.0) if name else None
