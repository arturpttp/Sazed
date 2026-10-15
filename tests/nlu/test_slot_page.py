import pytest

from sazed.core.types import SlotValue, Unmatched
from sazed.nlu.slots.page import extract_page
from sazed.skills.pc.settings import PAGE_NAMES


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("abre as configurações de bluetooth", "bluetooth"),
        ("abre as configurações de som", "som"),
        ("mostra as configurações de tela", "tela"),
        ("quero mudar o plano de fundo", "plano de fundo"),
        ("abre as configurações do wi fi", "wi-fi"),
        ("configurações de atualizações", "atualizações"),
    ],
)
def test_page_names_are_found(text: str, name: str) -> None:
    result = extract_page(text, PAGE_NAMES)
    assert isinstance(result, SlotValue) and result.value == name


def test_no_page_named_gives_none() -> None:
    assert extract_page("abre as configurações", PAGE_NAMES) is None


def test_an_unknown_page_is_unmatched() -> None:
    result = extract_page("abre as configurações de teletransporte", PAGE_NAMES)
    assert isinstance(result, Unmatched)
