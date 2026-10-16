import pytest

from sazed.core.types import SlotValue, Unmatched
from sazed.nlu.slots.percent import extract_percent


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("volume em 30", 30),
        ("coloca o volume em 0", 0),
        ("volume em 100", 100),
        ("volume em trinta", 30),
        ("volume em trinta e cinco", 35),
        ("aumenta o volume em dez", 10),
        ("volume em quinze", 15),
        ("volume na metade", 50),
        ("volume no máximo", 100),
        ("volume no mínimo", 0),
        ("volume em cinco", 5),
    ],
)
def test_reads_numbers_and_words(text: str, value: int) -> None:
    result = extract_percent(text)
    assert isinstance(result, SlotValue)
    assert result.name == "percent"
    assert result.value == value


def test_no_number_gives_none() -> None:
    assert extract_percent("aumenta o volume") is None


def test_article_um_is_not_the_number_one() -> None:
    assert extract_percent("abaixa um pouco") is None


def test_out_of_range_number_is_unmatched_so_the_skill_can_explain() -> None:
    assert extract_percent("volume em 150") == Unmatched("percent", "150", None)
