import pytest

from sazed.nlu.slots.mute import extract_mute


@pytest.mark.parametrize("text", ["muta", "silencia", "coloca no mudo", "tira o som"])
def test_mute_phrases_mean_true(text: str) -> None:
    assert extract_mute(text).value is True


@pytest.mark.parametrize(
    "text", ["tira do mudo", "desmuta", "volta o som", "ativa o som", "liga o áudio"]
)
def test_unmute_phrases_mean_false(text: str) -> None:
    result = extract_mute(text)
    assert result.name == "mudo"
    assert result.value is False
