from random import Random
from typing import get_args

import pytest

from sazed.core.decisions import AskSlot, Confirm, ConfirmReason, Decision
from sazed.core.outcomes import AppNotFound, AppOpened, Outcome
from sazed.core.persona import Prompt, render
from sazed.core.persona.definition import EXTRA_FIELDS, TEMPLATES, keys_for_type
from sazed.core.persona.render import format_fields, template_key
from support.samples import sample_instance

ALL_TYPES: tuple[type, ...] = get_args(Outcome) + get_args(Decision)
KEY_TO_TYPE = {key: cls for cls in ALL_TYPES for key in keys_for_type(cls)}
ALL_KEYS = sorted(KEY_TO_TYPE) + sorted(p.value for p in Prompt)


def _values_for(key: str) -> dict[str, str]:
    cls = KEY_TO_TYPE.get(key)
    base = format_fields(sample_instance(cls)) if cls is not None else {}
    extra = {name: "Exemplo" for name in EXTRA_FIELDS.get(key, ())}
    return {**base, **extra, "mestre": "Mestre Artur"}


def test_template_keys_are_exactly_the_reachable_ones() -> None:
    assert set(TEMPLATES) == set(ALL_KEYS)


@pytest.mark.parametrize("key", ALL_KEYS)
def test_every_variant_formats_with_the_fields_it_will_receive(key: str) -> None:
    assert TEMPLATES[key], f"{key} has no template"
    for template in TEMPLATES[key]:
        text = template.format(**_values_for(key))
        assert "{" not in text and "}" not in text


@pytest.mark.parametrize("key", ALL_KEYS)
def test_every_key_addresses_the_master_in_at_least_one_variant(key: str) -> None:
    assert any("{mestre}" in t for t in TEMPLATES[key])


@pytest.mark.parametrize("cls", ALL_TYPES)
def test_render_fills_the_configured_name(cls: type) -> None:
    item = sample_instance(cls)
    extra = {n: "Exemplo" for n in EXTRA_FIELDS.get(template_key(item), ())}
    texts = {render(item, nome="Artur", rng=Random(seed), extra=extra) for seed in range(40)}
    assert any("Mestre Artur" in t for t in texts)
    assert not any("{" in t for t in texts)


def test_rendering_is_deterministic_for_a_seed() -> None:
    a = render(AppOpened("Spotify"), nome="Artur", rng=Random(3))
    b = render(AppOpened("Spotify"), nome="Artur", rng=Random(3))
    assert a == b


def test_rng_reaches_every_variant() -> None:
    texts = {render(AppOpened("Spotify"), nome="Artur", rng=Random(s)) for s in range(60)}
    assert len(texts) == len(TEMPLATES["AppOpened"])


def test_app_not_found_with_suggestion_offers_it() -> None:
    text = render(AppNotFound("disc", "Discord"), nome="Artur", rng=Random(0))
    assert "Discord" in text and "disc" in text


def test_destructive_confirm_uses_its_own_template() -> None:
    item = Confirm("fechar_app", {}, ConfirmReason.DESTRUCTIVE)
    text = render(item, nome="Artur", rng=Random(0), extra={"acao": "fechar Spotify"})
    assert text in {
        t.format(acao="fechar Spotify", mestre="Mestre Artur")
        for t in TEMPLATES["ConfirmDestructive"]
    }


def test_ask_slot_with_candidates_numbers_them() -> None:
    item = AskSlot("abrir_app", {}, "app", ("Claude Code", "Visual Studio Code"), "code")
    text = render(item, nome="Artur", rng=Random(0), extra={"pergunta": "Qual programa?"})
    assert "1) Claude Code, 2) Visual Studio Code" in text


def test_missing_extra_is_a_programming_error() -> None:
    with pytest.raises(KeyError):
        render(Confirm("abrir_app", {}, ConfirmReason.LOW_SCORE), nome="Artur", rng=Random(0))


def test_now_playing_without_artist_omits_it() -> None:
    from sazed.core.outcomes import NowPlaying

    text = render(NowPlaying("Lofi Radio", ""), nome="Artur", rng=Random(0))
    assert "Lofi Radio" in text
    assert ", de" not in text


def test_window_not_found_offers_to_open_only_when_asked() -> None:
    from sazed.core.outcomes import WindowNotFound

    plain = render(WindowNotFound("Spotify"), nome="Artur", rng=Random(0))
    offer = render(WindowNotFound("Spotify", offer_open=True), nome="Artur", rng=Random(0))
    assert plain == "Spotify não está aberto, Mestre Artur."
    assert offer == "Spotify não está aberto, Mestre Artur. Devo abrir?"


def test_recent_files_lists_names_numbered() -> None:
    from sazed.core.outcomes import RecentFiles

    text = render(RecentFiles(2, ("a.pdf", "b.zip")), nome="Artur", rng=Random(0))
    assert text == "Hoje você baixou 2 arquivos, Mestre Artur: 1) a.pdf, 2) b.zip."


def test_file_not_found_names_the_kind() -> None:
    from sazed.core.outcomes import FileNotFound

    text = render(FileNotFound("gastos", "nenhuma planilha chamada"), nome="Artur", rng=Random(0))
    assert text == "Não encontrei nenhuma planilha chamada 'gastos', Mestre Artur."
