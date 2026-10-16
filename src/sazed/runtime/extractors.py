"""Which extractor fills which slot name."""

from collections.abc import Callable, Mapping, Sequence

from sazed.core.types import Extraction
from sazed.nlu.slots.app import extract_app
from sazed.nlu.slots.files import extract_file, extract_folder, extract_kind
from sazed.nlu.slots.mute import extract_mute
from sazed.nlu.slots.page import extract_page
from sazed.nlu.slots.percent import extract_percent
from sazed.nlu.slots.search import extract_engine, extract_query
from sazed.nlu.slots.target import extract_target
from sazed.nlu.slots.window import extract_monitor, extract_side

SlotExtractor = Callable[[str, Mapping[str, str]], Extraction | None]
"""(normalized utterance, aliases for this slot) -> extraction."""


def build_extractors(
    app_names: Sequence[str],
    engine_names: Sequence[str] = (),
    page_names: Sequence[str] = (),
    folder_names: Sequence[str] = (),
    folder_synonyms: Mapping[str, str] | None = None,
) -> dict[str, SlotExtractor]:
    names, engines, pages = list(app_names), list(engine_names), list(page_names)

    def app(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_app(text, names, aliases)

    def percent(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_percent(text)

    def mute(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_mute(text)

    def target(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_target(text)

    def query(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_query(text, engines)

    def engine(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_engine(text, engines)

    def page(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_page(text, pages)

    folders, synonyms = list(folder_names), dict(folder_synonyms or {})

    def side(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_side(text)

    def monitor(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_monitor(text)

    def folder(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_folder(text, folders, synonyms)

    def kind(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_kind(text)

    def file(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_file(text)

    return {
        "lado": side,
        "monitor": monitor,
        "pasta": folder,
        "tipo": kind,
        "arquivo": file,
        "pagina": page,
        "app": app,
        "percent": percent,
        "alvo": target,
        "mudo": mute,
        "consulta": query,
        "site": engine,
    }
