import pytest

from sazed.nlu.normalize import normalize
from sazed.nlu.slots.window import extract_monitor, extract_side


@pytest.mark.parametrize(
    ("text", "side"),
    [
        ("joga o chrome pra esquerda", "esquerda"),
        ("encaixa na direita", "direita"),
        ("manda pro lado esquerdo", "esquerda"),
        ("coloca à direita", "direita"),
        ("encaixa o spotify no lado direito da tela", "direita"),
    ],
)
def test_side(text: str, side: str) -> None:
    found = extract_side(normalize(text))
    assert found is not None and (found.name, found.value) == ("lado", side)


def test_no_side() -> None:
    assert extract_side("minimiza o chrome") is None


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("manda pro outro monitor", "outro"),
        ("joga pra outra tela", "outro"),
        ("manda o chrome pro monitor 2", 2),
        ("pro segundo monitor", 2),
        ("pra tela 1", 1),
        ("move pro primeiro monitor", 1),
    ],
)
def test_monitor(text: str, value: object) -> None:
    found = extract_monitor(normalize(text))
    assert found is not None and (found.name, found.value) == ("monitor", value)


def test_no_monitor() -> None:
    assert extract_monitor(normalize("joga o chrome pra esquerda")) is None
    assert extract_monitor(normalize("aumenta o volume em 2")) is None
