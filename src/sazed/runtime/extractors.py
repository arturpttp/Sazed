"""Which extractor fills which slot name."""

from collections.abc import Callable, Mapping, Sequence

from sazed.core.types import Extraction
from sazed.nlu.slots.app import extract_app
from sazed.nlu.slots.mute import extract_mute
from sazed.nlu.slots.percent import extract_percent
from sazed.nlu.slots.search import extract_engine, extract_query
from sazed.nlu.slots.target import extract_target

SlotExtractor = Callable[[str, Mapping[str, str]], Extraction | None]
"""(normalized utterance, aliases for this slot) -> extraction."""


def build_extractors(
    app_names: Sequence[str],
    engine_names: Sequence[str] = (),
    page_names: Sequence[str] = (),
) -> dict[str, SlotExtractor]:
    names, engines = list(app_names), list(engine_names)

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

    return {
        "app": app,
        "percent": percent,
        "alvo": target,
        "mudo": mute,
        "consulta": query,
        "site": engine,
    }
