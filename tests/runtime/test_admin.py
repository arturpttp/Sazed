from datetime import datetime
from pathlib import Path
from random import Random
from typing import get_args

import pytest

from fakes.clock import ManualClock
from fakes.embedder import HashingEmbedder
from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher
from sazed.core.coppermind import Episode, NewAlias, Reaction
from sazed.core.decisions import Decision
from sazed.runtime.admin import (
    DECISION_LABELS,
    REACTION_LABELS,
    LabelResult,
    failure_rows,
    forget_learned,
    intent_rows,
    label_episode,
    learned_rows,
)
from sazed.runtime.config import Config, DataConfig
from sazed.runtime.wiring import SazedApp, build_app

T0 = datetime(2026, 10, 14, 12, 0)


def boot(tmp_path: Path) -> SazedApp:
    return build_app(
        Config(data=DataConfig(dir=tmp_path)),
        embedder=HashingEmbedder(),
        catalog=FakeCatalog(["WhatsApp"]),
        launcher=FakeLauncher(),
        audio=FakeAudio(),
        clock=ManualClock(),
        rng=Random(0),
    )


def test_every_decision_and_reaction_has_a_pt_br_label() -> None:
    names = {t.__name__ for t in get_args(Decision)} | {"control", "error"}
    assert names <= set(DECISION_LABELS)
    assert set(Reaction) == set(REACTION_LABELS)


def test_learned_rows_describe_items_without_internal_ids(tmp_path: Path) -> None:
    app = boot(tmp_path)
    app.store.learn([], [NewAlias("app", "zap", "WhatsApp")], T0)
    (row,) = learned_rows(app)
    assert (row.ref, row.kind, row.text, row.meaning) == ("a1", "apelido", "zap", "WhatsApp")


def test_forget_learned_by_ref(tmp_path: Path) -> None:
    app = boot(tmp_path)
    app.store.learn([], [NewAlias("app", "zap", "WhatsApp")], T0)
    assert forget_learned(app, "a1") is not None
    assert app.store.aliases() == []
    assert forget_learned(app, "a1") is None
    assert forget_learned(app, "x9") is None
    assert forget_learned(app, "abc") is None


def test_failures_are_listed_with_labels(tmp_path: Path) -> None:
    app = boot(tmp_path)
    app.store.record_episode(Episode("liga o navegador", T0, (), {}, "NotUnderstood", None, ""))
    (row,) = failure_rows(app, 10)
    assert row.utterance == "liga o navegador"
    assert row.what == "não entendido"


def test_label_episode_learns_the_normalised_utterance(tmp_path: Path) -> None:
    app = boot(tmp_path)
    episode_id = app.store.record_episode(
        Episode("Liga o navegador!", T0, (), {}, "NotUnderstood", None, "")
    )
    assert label_episode(app, episode_id, "abrir_app") is LabelResult.LEARNED
    assert [(e.text, e.intent_id) for e in app.store.examples()] == [
        ("liga o navegador", "abrir_app")
    ]


def test_label_episode_refuses_unknown_intent_or_episode(tmp_path: Path) -> None:
    app = boot(tmp_path)
    episode_id = app.store.record_episode(Episode("x", T0, (), {}, "NotUnderstood", None, ""))
    assert label_episode(app, episode_id, "inexistente") is LabelResult.UNKNOWN
    assert label_episode(app, 999, "abrir_app") is LabelResult.UNKNOWN
    assert app.store.examples() == []


def test_intent_rows_describe_in_pt_br(tmp_path: Path) -> None:
    rows = dict(intent_rows(boot(tmp_path)))
    assert rows["abrir_app"] == "abrir um programa"


def test_labelling_a_known_phrase_again_is_reported_and_not_duplicated(tmp_path: Path) -> None:
    app = boot(tmp_path)
    ep = Episode("liga o navegador", T0, (), {}, "NotUnderstood", None, "")
    first, second = app.store.record_episode(ep), app.store.record_episode(ep)
    assert label_episode(app, first, "abrir_app") is LabelResult.LEARNED
    assert label_episode(app, second, "abrir_app") is LabelResult.ALREADY_KNOWN
    assert len(app.store.examples()) == 1


def test_labelling_a_phrase_that_belongs_to_another_intent_needs_force(tmp_path: Path) -> None:
    app = boot(tmp_path)
    ep = Episode("abre o chrome", T0, (), {}, "Execute", None, "")
    episode_id = app.store.record_episode(ep)
    assert label_episode(app, episode_id, "fechar_app") is LabelResult.CONFLICT
    assert app.store.examples() == []
    assert label_episode(app, episode_id, "fechar_app", force=True) is LabelResult.LEARNED
    assert [e.intent_id for e in app.store.examples()] == ["fechar_app"]


@pytest.mark.skip(reason="enabled in Task 14, when build_app includes PowerSkill")
def test_a_power_command_cannot_be_labelled(tmp_path: Path) -> None:
    app = boot(tmp_path)
    episode_id = app.store.record_episode(
        Episode("apaga tudo", T0, (), {}, "NotUnderstood", None, "")
    )
    assert label_episode(app, episode_id, "pc_desligar") is LabelResult.NOT_LEARNABLE
    assert app.store.examples() == []
