"""Web search in the default browser. Opening sites goes through the app catalog instead."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import Protocol
from urllib.parse import quote_plus

from sazed.core.outcomes import Outcome, SearchOpened
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue


class UriOpener(Protocol):
    def open(self, uri: str) -> None: ...


SEARCH_EXAMPLES = (
    "pesquisa receitas de bolo",
    "pesquisa no google como fazer pão",
    "procura vídeos de gatos no youtube",
    "busca o preço do dólar",
    "pesquise sobre buracos negros",
    "procura na internet horário do jogo",
    "pesquisa lofi no youtube",
    "busca na wikipédia a revolução francesa",
    "faz uma pesquisa sobre python",
    "pesquisar notícias de hoje",
)


def search_url(template: str, query: str) -> str:
    # quote_plus encodes everything but letters, digits and _.-~: no query can escape {q}.
    return template.replace("{q}", quote_plus(query))


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()


def _query_label(slots: Slots) -> str:
    query = slots.get("consulta")
    return f"'{query.value}'" if isinstance(query, SlotValue) else "algo"


class WebSkill:
    id = "web"

    def __init__(self, opener: UriOpener, engines: Mapping[str, str], default: str) -> None:
        self._opener = opener
        self._engines = dict(engines)
        self._default = default
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "pesquisar",
                SEARCH_EXAMPLES,
                (
                    SlotSpec("consulta", True, "O que devo pesquisar?"),
                    SlotSpec("site", False, "Onde devo pesquisar?"),
                ),
                describe=lambda s: f"pesquisar {_query_label(s)}",
            ),
        )

    def _engine(self, name: str) -> tuple[str, str]:
        for key, template in self._engines.items():
            if _fold(key) == _fold(name):
                return key, template
        raise ValueError(f"unknown search engine {name!r}")  # config validation prevents it

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id != "pesquisar":
            raise ValueError(f"unknown intent {intent_id}")
        query = slots.get("consulta")
        if not isinstance(query, SlotValue):
            raise ValueError("pesquisar called without its required slot 'consulta'")
        site = slots.get("site")
        wanted = str(site.value) if isinstance(site, SlotValue) else self._default
        name, template = self._engine(wanted)
        self._opener.open(search_url(template, str(query.value)))
        return SearchOpened(str(query.value), name)
