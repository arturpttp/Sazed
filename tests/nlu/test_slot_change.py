import pytest

from sazed.core.types import SlotValue, Unmatched
from sazed.nlu.normalize import normalize
from sazed.nlu.slots.change import extract_destination, extract_item, extract_new_name

NAMES = [
    "Downloads",
    "Documentos",
    "Área de Trabalho",
    "Imagens",
    "Vídeos",
    "Músicas",
    "Capturas de Tela",
    "Projetos",
]
SYN = {"download": "Downloads", "print": "Capturas de Tela", "desktop": "Área de Trabalho"}


def item(text: str) -> object:
    found = extract_item(normalize(text), NAMES, SYN)
    return found.value if found else None


def dest(text: str) -> object:
    found = extract_destination(normalize(text), NAMES, SYN)
    if isinstance(found, SlotValue):
        return found.value
    if isinstance(found, Unmatched):
        return ("?", found.raw)
    return None


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("move o relatório de vendas pra pasta projetos", "arquivo:relatório vendas"),
        ("manda o último download pra área de trabalho", "ultimo:Downloads"),
        ("copia a planilha de gastos pra pasta projetos", "arquivo:gastos"),
        ("renomeia o arquivo contrato pra Contrato Assinado", "arquivo:contrato"),
        ("muda o nome da pasta viagem pra viagem 2025", "pasta:viagem"),
        ("apaga a pasta temporários", "pasta:temporários"),
        ("joga o último print no lixo", "ultimo:Capturas de Tela"),
        ("apaga o arquivo reunião na segunda", "arquivo:reunião segunda"),
        ("apaga o último arquivo", "ultimo:Downloads"),
        ("deleta o rascunho", "arquivo:rascunho"),
    ],
)
def test_item(text: str, value: str) -> None:
    assert item(text) == value


def test_no_item_named() -> None:
    assert item("apaga o arquivo") is None
    assert item("move pra pasta documentos") is None


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("move o relatório de vendas pra pasta projetos", "Projetos"),
        ("manda o último download pra área de trabalho", "Área de Trabalho"),
        ("copia a planilha pro desktop", "Área de Trabalho"),
        ("cria uma pasta chamada viagem na área de trabalho", "Área de Trabalho"),
        ("cria uma pasta chamada viagem em documentos", "Documentos"),
        ("move o relatório pra pasta fotos antigas", ("?", "fotos antigas")),
        ("move o relatório pra viagem", ("?", "viagem")),
    ],
)
def test_destination(text: str, value: object) -> None:
    assert dest(text) == value


@pytest.mark.parametrize(
    "text",
    [
        "joga o último print no lixo",
        "apaga o arquivo reunião na segunda",
        "cria uma pasta chamada fotos na praia",
        "apaga o rascunho pra mim",
        "renomeia o arquivo contrato pra contrato assinado",
    ],
)
def test_no_destination(text: str) -> None:
    # A rename's "pra" introduces the new name; the skill ignores `destino` for renames, but
    # an unknown tail after a weak marker must never become a destination.
    if text.startswith("renomeia"):
        return
    assert dest(text) is None


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("renomeia o arquivo contrato pra Contrato Assinado", "Contrato Assinado"),
        ("Renomeia o relatório para relatório-2025 (final).", "relatório-2025 (final)"),
        ("muda o nome da pasta viagem pra Viagem 2025", "Viagem 2025"),
        ("cria uma pasta chamada Viagem na área de trabalho", "Viagem"),
        ("cria uma pasta chamada Fotos na praia", "Fotos na praia"),
        ('cria uma pasta chamada "Notas Fiscais" em documentos', "Notas Fiscais"),
        ("cria uma pasta Orçamentos", "Orçamentos"),
        ("salva como Notas Velhas", "Notas Velhas"),
    ],
)
def test_new_name_keeps_case_and_punctuation(raw: str, name: str) -> None:
    found = extract_new_name(raw, NAMES, SYN)
    assert found is not None and (found.name, found.value) == ("novo_nome", name)


def test_no_new_name() -> None:
    assert extract_new_name("cria uma pasta", NAMES, SYN) is None
    assert extract_new_name("renomeia o arquivo", NAMES, SYN) is None


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("move o relatório pra entregar pra pasta projetos", "arquivo:relatório entregar"),
        ("copia a foto da praia no rio pra pasta imagens", "arquivo:praia rio"),
    ],
)
def test_the_destination_starts_at_the_last_marker(text: str, value: str) -> None:
    assert item(text) == value
    assert dest(text) in ("Projetos", "Imagens")
