"""Read a 0-100 percentage from digits or pt-BR number words. Pure."""

from sazed.core.types import SlotValue
from sazed.nlu.normalize import strip_accents

_UNITS = {
    "zero": 0,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
}
_TEENS = {
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "catorze": 14,
    "quatorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
}
_TENS = {
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
    "sessenta": 60,
    "setenta": 70,
    "oitenta": 80,
    "noventa": 90,
}
_WORDS = {"metade": 50, "meio": 50, "maximo": 100, "tudo": 100, "cem": 100, "minimo": 0}
# "um"/"uma" are left out on purpose: in "abaixa um pouco" they are articles.
_UNITS_AFTER_E = {**_UNITS, "um": 1, "uma": 1}


def _value(n: int, raw: str) -> SlotValue | None:
    return SlotValue("percent", n, raw, 1.0) if 0 <= n <= 100 else None


def extract_percent(normalized: str) -> SlotValue | None:
    tokens = strip_accents(normalized).split()
    for token in tokens:
        if token.isdigit():
            return _value(int(token), token)
    for i, token in enumerate(tokens):
        if token in _WORDS:
            return _value(_WORDS[token], token)
        if token in _TENS:
            n = _TENS[token]
            if i + 2 < len(tokens) and tokens[i + 1] == "e" and tokens[i + 2] in _UNITS_AFTER_E:
                return _value(n + _UNITS_AFTER_E[tokens[i + 2]], " ".join(tokens[i : i + 3]))
            return _value(n, token)
        if token in _TEENS:
            return _value(_TEENS[token], token)
        if token in _UNITS:
            return _value(_UNITS[token], token)
    return None
