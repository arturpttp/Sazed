from collections import Counter

import pytest

from fakes.ports import fake_pc_ports
from sazed.core.skill import IntentSpec
from sazed.nlu.normalize import normalize
from sazed.runtime.config import Config
from sazed.runtime.skills import build_skills

SPECS: list[IntentSpec] = [
    spec for skill in build_skills(fake_pc_ports([]), Config()).skills for spec in skill.intents
]


def test_intent_ids_are_unique() -> None:
    assert [i for i, n in Counter(s.id for s in SPECS).items() if n > 1] == []


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_each_intent_has_enough_seed_examples(spec: IntentSpec) -> None:
    assert len(spec.examples) >= 8


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_seed_examples_are_already_normalised(spec: IntentSpec) -> None:
    assert [e for e in spec.examples if normalize(e) != e] == []


def test_no_example_belongs_to_two_intents() -> None:
    counts = Counter(e for s in SPECS for e in s.examples)
    assert [e for e, n in counts.items() if n > 1] == []


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_every_slot_has_a_pt_br_question(spec: IntentSpec) -> None:
    assert all(s.question.endswith("?") for s in spec.slots)


def test_only_level_steps_track_skips_and_window_moves_are_repeatable() -> None:
    assert {s.id for s in SPECS if s.repeatable} == {
        "janela_minimizar",
        "janela_encaixar",
        "janela_mover_monitor",
        "volume_aumentar",
        "volume_diminuir",
        "brilho_aumentar",
        "brilho_diminuir",
        "midia_proxima",
        "midia_anterior",
    }


def test_only_opening_and_closing_apps_use_the_learning_placeholder() -> None:
    # Learned app phrases store "programa" in place of the app. A seed of another intent
    # holding that word makes every learned open/close phrase "conflict" with it (2b: "me
    # mostra o programa" made "inicia aí o programa pra mim" rank focus, so nothing was learned).
    from sazed.nlu.slots.app import PLACEHOLDER

    users = {s.id for s in SPECS for e in s.examples if PLACEHOLDER in e.split()}
    assert users <= {"abrir_app", "fechar_app"}
