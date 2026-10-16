import pytest

from sazed.core.types import SlotValue, Unmatched
from sazed.nlu.normalize import normalize
from sazed.nlu.slots.files import extract_file, extract_folder, extract_kind

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
SYN = {
    "baixados": "Downloads",
    "download": "Downloads",
    "meus documentos": "Documentos",
    "desktop": "Área de Trabalho",
    "fotos": "Imagens",
    "prints": "Capturas de Tela",
    "print": "Capturas de Tela",
}


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("abre a pasta downloads", "Downloads"),
        ("abre meus documentos", "Documentos"),
        ("abre a área de trabalho", "Área de Trabalho"),
        ("abre o último print", "Capturas de Tela"),
        ("abre o último download", "Downloads"),
        ("abre a pasta projetos", "Projetos"),
        ("mostra a pasta de vídeos", "Vídeos"),
    ],
)
def test_folder(text: str, name: str) -> None:
    found = extract_folder(normalize(text), NAMES, SYN)
    assert isinstance(found, SlotValue) and (found.name, found.value) == ("pasta", name)


def test_unknown_folder_is_unmatched() -> None:
    assert isinstance(extract_folder("abre a pasta xyzzy", NAMES, SYN), Unmatched)


def test_no_folder_named() -> None:
    assert extract_folder("abre a pasta", NAMES, SYN) is None


@pytest.mark.parametrize(
    ("text", "words", "kind"),
    [
        ("abre o arquivo relatório", "relatório", None),
        ("acha a planilha de gastos", "gastos", "planilha"),
        ("abre o pdf do contrato", "contrato", "pdf"),
        ("abre a foto da praia", "praia", "foto"),
        ("encontra o documento proposta final", "proposta final", "documento"),
    ],
)
def test_file_and_kind(text: str, words: str, kind: str | None) -> None:
    n = normalize(text)
    assert extract_file(n) == SlotValue("arquivo", words, words, 1.0)
    found = extract_kind(n)
    assert (found.value if found else None) == kind


def test_only_command_words_is_no_file() -> None:
    assert extract_file(normalize("abre o arquivo")) is None
    assert extract_file(normalize("acha a planilha")) is None
