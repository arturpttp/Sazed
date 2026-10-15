from sazed.nlu.normalize import normalize, strip_accents


def test_lowercases_and_strips_punctuation() -> None:
    assert normalize("Abre o Chrome!!") == "abre o chrome"


def test_collapses_whitespace_and_drops_percent_sign() -> None:
    assert normalize("  volume   em 30% ") == "volume em 30"


def test_keeps_accents() -> None:
    assert normalize("Não, é o Discórdia.") == "não é o discórdia"


def test_strip_accents_removes_diacritics_only() -> None:
    assert strip_accents("não é ação") == "nao e acao"


def test_strip_accents_preserves_length_for_latin_text() -> None:
    text = "põe o volume no máximo"
    assert len(strip_accents(text)) == len(text)
