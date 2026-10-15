import pytest

from sazed.core.types import SlotValue
from sazed.nlu.slots.search import extract_engine, extract_query

ENGINES = ["Google", "YouTube", "Wikipédia"]


@pytest.mark.parametrize(
    ("text", "query"),
    [
        ("pesquisa receitas de bolo", "receitas de bolo"),
        ("pesquisa lofi no youtube", "lofi"),
        ("procura sobre buracos negros na wikipedia", "buracos negros"),
        ("sazed busca por preço do dólar", "preço do dólar"),
        ("pesquisa pra mim horário do jogo", "horário do jogo"),
        ("lofi", "lofi"),  # a bare answer to "O que devo pesquisar?"
    ],
)
def test_query_is_the_text_after_the_trigger_without_the_engine(text: str, query: str) -> None:
    assert extract_query(text, ENGINES) == SlotValue("consulta", query, query, 1.0)


@pytest.mark.parametrize("text", ["pesquisa", "pesquisa no youtube", "busca por", ""])
def test_no_query_gives_none_so_sazed_asks(text: str) -> None:
    assert extract_query(text, ENGINES) is None


def test_engine_is_the_trailing_place() -> None:
    assert extract_engine("pesquisa lofi no youtube", ENGINES) == SlotValue(
        "site", "YouTube", "youtube", 1.0
    )
    assert extract_engine("procura gatos na wikipedia", ENGINES) == SlotValue(
        "site", "Wikipédia", "wikipedia", 1.0
    )


def test_a_place_in_the_middle_is_part_of_the_query() -> None:
    assert extract_engine("pesquisa vídeos no youtube de gatos", ENGINES) is None
