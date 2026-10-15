from datetime import datetime

import pytest

from fakes.ports import FakeOpener
from sazed.core.outcomes import SearchOpened
from sazed.core.skill import SkillContext
from sazed.core.types import SlotValue
from sazed.runtime.config import BUILTIN_ENGINES
from sazed.skills.pc.web import WebSkill, search_url

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("receitas de bolo", "https://x/?q=receitas+de+bolo"),
        ("pão & café", "https://x/?q=p%C3%A3o+%26+caf%C3%A9"),
        ("c# #1", "https://x/?q=c%23+%231"),
        ("a/b?c=d", "https://x/?q=a%2Fb%3Fc%3Dd"),
    ],
)
def test_search_url_encodes_the_whole_query(query: str, expected: str) -> None:
    assert search_url("https://x/?q={q}", query) == expected


def slots(query: str, site: str | None = None) -> dict[str, SlotValue]:
    found = {"consulta": SlotValue("consulta", query, query, 1.0)}
    if site is not None:
        found["site"] = SlotValue("site", site, site.lower(), 1.0)
    return found


def test_default_engine_is_used_without_a_place() -> None:
    opener = FakeOpener()
    skill = WebSkill(opener, BUILTIN_ENGINES, "google")
    assert skill.execute("pesquisar", slots("lofi"), CTX) == SearchOpened("lofi", "Google")
    assert opener.opened == ["https://www.google.com/search?q=lofi"]


def test_named_engine_is_used() -> None:
    opener = FakeOpener()
    WebSkill(opener, BUILTIN_ENGINES, "Google").execute("pesquisar", slots("lofi", "YouTube"), CTX)
    assert opener.opened == ["https://www.youtube.com/results?search_query=lofi"]
