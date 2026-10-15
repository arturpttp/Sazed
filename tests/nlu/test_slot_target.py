import pytest

from sazed.core.types import SlotValue
from sazed.nlu.slots.target import extract_target


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("abaixa o volume para 100", 100),
        ("aumenta o volume pra 20", 20),
        ("abaixa o volume pra zero", 0),
        ("sobe o som até 80", 80),
        ("aumenta pro máximo", 100),
        ("abaixa o volume para o mínimo", 0),
        ("aumenta o volume pra trinta e cinco", 35),
        ("abaixa para 100 por cento", 100),
    ],
)
def test_a_number_after_para_is_the_level_to_end_at(text: str, value: int) -> None:
    result = extract_target(text)
    assert isinstance(result, SlotValue)
    assert result.name == "alvo"
    assert result.value == value


@pytest.mark.parametrize(
    "text",
    [
        "aumenta o volume em 20",  # a step, not a level
        "abaixa o volume",
        "aumenta pra mim",  # "pra" without a number
        "abaixa o volume para 150",  # out of range: ask instead of clamping
    ],
)
def test_no_level_gives_none(text: str) -> None:
    assert extract_target(text) is None


def test_the_number_must_follow_the_preposition() -> None:
    assert extract_target("aumenta 10 pra mim") is None
