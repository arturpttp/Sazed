import pytest

from sazed.nlu.control import Control, ControlKind, parse_control, pick_candidate


@pytest.mark.parametrize("text", ["sim", "pode", "isso mesmo", "claro", "pode sim", "ok"])
def test_confirm(text: str) -> None:
    assert parse_control(text) == Control(ControlKind.CONFIRM)


@pytest.mark.parametrize("text", ["não", "nao", "cancela", "deixa pra lá", "melhor não"])
def test_deny(text: str) -> None:
    assert parse_control(text) == Control(ControlKind.DENY)


@pytest.mark.parametrize("text", ["esquece isso", "esqueça isso", "esquece"])
def test_forget(text: str) -> None:
    assert parse_control(text) == Control(ControlKind.FORGET)


@pytest.mark.parametrize("text", ["de novo", "outra vez", "mais", "mais um pouco"])
def test_repeat(text: str) -> None:
    assert parse_control(text) == Control(ControlKind.REPEAT)


@pytest.mark.parametrize(
    ("text", "rest"),
    [
        ("não era o discord", "discord"),
        ("era pra fechar", "fechar"),
        ("é o discord", "discord"),
        ("eu quis dizer spotify", "spotify"),
        ("não era o código", "código"),
    ],
)
def test_correction_keeps_the_rest_with_accents(text: str, rest: str) -> None:
    assert parse_control(text) == Control(ControlKind.CORRECT, rest)


@pytest.mark.parametrize("text", ["abre o chrome", "não é o discord", "e abre o spotify", ""])
def test_ordinary_commands_are_not_control(text: str) -> None:
    assert parse_control(text) is None


CANDIDATES = ("Claude Code", "Visual Studio Code")


@pytest.mark.parametrize(
    ("text", "choice"),
    [
        ("o segundo", "Visual Studio Code"),
        ("2", "Visual Studio Code"),
        ("primeiro", "Claude Code"),
        ("o último", "Visual Studio Code"),
        ("o visual studio", "Visual Studio Code"),
        ("claude", "Claude Code"),
    ],
)
def test_pick_candidate(text: str, choice: str) -> None:
    assert pick_candidate(text, CANDIDATES) == choice


@pytest.mark.parametrize("text", ["o terceiro", "5", "aumenta o volume", "code"])
def test_pick_candidate_refuses_unclear_answers(text: str) -> None:
    assert pick_candidate(text, CANDIDATES) is None
