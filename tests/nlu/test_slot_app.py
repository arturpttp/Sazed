from sazed.core.types import Ambiguous, SlotValue, Unmatched
from sazed.nlu.slots.app import extract_app

NAMES = [
    "Google Chrome",
    "Spotify",
    "Discord",
    "Visual Studio Code",
    "Claude Code",
    "Bloco de Notas",
    "Steam",
]


def test_word_contained_in_a_single_name_is_an_exact_match() -> None:
    assert extract_app("abre o chrome", NAMES, {}) == SlotValue(
        "app", "Google Chrome", "chrome", 1.0, exact=True
    )


def test_command_and_filler_words_are_ignored() -> None:
    result = extract_app("pode abrir o spotify pra mim por favor", NAMES, {})
    assert isinstance(result, SlotValue) and result.value == "Spotify"


def test_accents_and_case_do_not_matter() -> None:
    result = extract_app("abre o blóco de notas", NAMES, {})
    assert isinstance(result, SlotValue) and result.value == "Bloco de Notas"


def test_typo_matches_but_is_not_exact() -> None:
    result = extract_app("abre o crome", NAMES, {})
    assert isinstance(result, SlotValue)
    assert result.value == "Google Chrome"
    assert result.exact is False


def test_word_shared_by_two_names_is_ambiguous() -> None:
    assert extract_app("abre o code", NAMES, {}) == Ambiguous(
        "app", "code", ("Claude Code", "Visual Studio Code")
    )


def test_weak_match_is_unmatched_with_a_suggestion() -> None:
    assert extract_app("abre o disc", NAMES, {}) == Unmatched("app", "disc", "Discord")


def test_nothing_close_is_unmatched_without_suggestion() -> None:
    assert extract_app("abre o photoshop", NAMES, {}) == Unmatched("app", "photoshop", None)


def test_alias_wins_and_is_exact() -> None:
    result = extract_app("abre o zap", NAMES + ["WhatsApp"], {"zap": "WhatsApp"})
    assert result == SlotValue("app", "WhatsApp", "zap", 1.0, exact=True)


def test_alias_keys_are_normalised() -> None:
    result = extract_app("abre o código", NAMES, {"Código": "Visual Studio Code"})
    assert isinstance(result, SlotValue) and result.value == "Visual Studio Code"


def test_alias_to_an_app_that_no_longer_exists_is_ignored() -> None:
    assert extract_app("abre o zap", NAMES, {"zap": "WhatsApp"}) == Unmatched("app", "zap", None)


def test_only_command_words_means_no_app_named() -> None:
    assert extract_app("abre o programa", NAMES, {}) is None


def test_an_exact_name_wins_over_a_longer_name_containing_it() -> None:
    names = ["WhatsApp", "WhatsApp Web"]
    assert extract_app("abre o whatsapp", names, {}) == SlotValue(
        "app", "WhatsApp", "whatsapp", 1.0, exact=True
    )
    assert extract_app("abre o whatsapp web", names, {}) == SlotValue(
        "app", "WhatsApp Web", "whatsapp web", 1.0, exact=True
    )
