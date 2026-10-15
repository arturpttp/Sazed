"""Which extractor fills which slot name."""

from collections.abc import Callable, Mapping, Sequence

from sazed.core.types import Extraction
from sazed.nlu.slots.app import extract_app
from sazed.nlu.slots.mute import extract_mute
from sazed.nlu.slots.percent import extract_percent
from sazed.nlu.slots.target import extract_target

SlotExtractor = Callable[[str, Mapping[str, str]], Extraction | None]
"""(normalized utterance, aliases for this slot) -> extraction."""


def build_extractors(app_names: Sequence[str]) -> dict[str, SlotExtractor]:
    names = list(app_names)

    def app(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_app(text, names, aliases)

    def percent(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_percent(text)

    def mute(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_mute(text)

    def target(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_target(text)

    return {"app": app, "percent": percent, "alvo": target, "mudo": mute}
