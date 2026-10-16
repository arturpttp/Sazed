"""Adding, fixing and forgetting learned items from outside the conversation (the dashboard)."""

import sqlite3
from datetime import datetime
from pathlib import Path
from random import Random

import pytest

from fakes.clock import ManualClock
from fakes.embedder import HashingEmbedder
from fakes.ports import fake_pc_ports
from sazed.core.coppermind import LearnedKind, NewAlias, NoteTarget
from sazed.runtime.admin import (
    AliasResult,
    LabelResult,
    add_alias,
    edit_alias,
    edit_example,
    forget_learned,
    learn_example,
)
from sazed.runtime.config import Config, DataConfig
from sazed.runtime.wiring import SazedApp, build_app

NAMES = ["WhatsApp", "Google Chrome", "Discord"]
FRESH = "me mostra o mensageiro verde"
T = datetime(2026, 10, 15, 12, 0)


@pytest.fixture
def app(tmp_path: Path) -> SazedApp:
    return build_app(
        Config(data=DataConfig(dir=tmp_path)),
        embedder=HashingEmbedder(),
        ports=fake_pc_ports(NAMES),
        clock=ManualClock(),
        rng=Random(0),
    )


def on_disk(app: SazedApp, sql: str) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(app.config.data.dir / "coppermind.db")
    try:
        return list(conn.execute(sql).fetchall())
    finally:
        conn.close()


# examples ----------------------------------------------------------------------


def test_learn_example_normalises_and_saves(app: SazedApp) -> None:
    assert (
        learn_example(app, "  Me MOSTRA o mensageiro verde!! ", "abrir_app") is LabelResult.LEARNED
    )
    assert on_disk(app, "SELECT text, intent_id, origin FROM learned_examples") == [
        (FRESH, "abrir_app", "painel")
    ]
    assert app.index.scores(FRESH)["abrir_app"] == pytest.approx(1.0)  # live index updated


def test_learn_example_masks_the_app_name_as_live_learning_does(app: SazedApp) -> None:
    assert learn_example(app, "bota o whatsapp pra rodar", "abrir_app") is LabelResult.LEARNED
    assert on_disk(app, "SELECT text FROM learned_examples") == [("bota o programa pra rodar",)]


def test_editing_an_example_masks_the_app_name(app: SazedApp) -> None:
    learn_example(app, FRESH, "abrir_app")
    (old,) = app.store.examples()
    assert edit_example(app, old.id, "derruba o discord", "fechar_app") is LabelResult.LEARNED
    assert on_disk(app, "SELECT text, intent_id FROM learned_examples") == [
        ("derruba o programa", "fechar_app")
    ]


def test_learn_example_refuses_a_power_intent(app: SazedApp) -> None:
    assert learn_example(app, "apaga tudo agora", "pc_desligar") is LabelResult.NOT_LEARNABLE
    assert on_disk(app, "SELECT COUNT(*) FROM learned_examples") == [(0,)]


def test_learn_example_reports_a_duplicate(app: SazedApp) -> None:
    assert learn_example(app, "abre o chrome", "abrir_app") is LabelResult.ALREADY_KNOWN
    assert on_disk(app, "SELECT COUNT(*) FROM learned_examples") == [(0,)]


def test_a_conflict_needs_force(app: SazedApp) -> None:
    assert learn_example(app, "fecha o chrome", "abrir_app") is LabelResult.CONFLICT
    assert on_disk(app, "SELECT COUNT(*) FROM learned_examples") == [(0,)]
    assert learn_example(app, "fecha o chrome", "abrir_app", force=True) is LabelResult.LEARNED
    assert on_disk(app, "SELECT text, intent_id FROM learned_examples") == [
        ("fecha o programa", "abrir_app")
    ]


@pytest.mark.parametrize(("text", "intent"), [("", "abrir_app"), ("?!", "abrir_app")])
def test_learn_example_refuses_empty_text(app: SazedApp, text: str, intent: str) -> None:
    assert learn_example(app, text, intent) is LabelResult.EMPTY


def test_learn_example_refuses_an_unknown_intent(app: SazedApp) -> None:
    assert learn_example(app, FRESH, "voar") is LabelResult.UNKNOWN


def test_edit_example_changes_text_and_intent_atomically(app: SazedApp) -> None:
    learn_example(app, FRESH, "abrir_app")
    app.store.add_note(NoteTarget.EXAMPLE, 1, "nota", datetime(2026, 10, 15))
    assert edit_example(app, 1, "fecha o mensageiro verde", "fechar_app") is LabelResult.LEARNED
    assert on_disk(app, "SELECT id, text, intent_id FROM learned_examples") == [
        (1, "fecha o mensageiro verde", "fechar_app")
    ]
    assert on_disk(app, "SELECT target_id, text FROM notes") == [(1, "nota")]
    scores = app.index.scores("fecha o mensageiro verde")
    assert scores["fechar_app"] == pytest.approx(1.0)
    assert app.index.scores(FRESH)["abrir_app"] < 0.99  # the old text left the index


def test_edit_example_judges_without_the_old_version(app: SazedApp) -> None:
    learn_example(app, FRESH, "abrir_app")
    # Only the intent changes: the old example (same text) must not count as a conflict.
    assert edit_example(app, 1, FRESH, "fechar_app") is LabelResult.LEARNED


def test_a_refused_edit_leaves_index_and_store_untouched(app: SazedApp) -> None:
    learn_example(app, FRESH, "abrir_app")
    assert edit_example(app, 1, FRESH, "pc_desligar") is LabelResult.NOT_LEARNABLE
    assert edit_example(app, 1, "fecha o chrome", "abrir_app") is LabelResult.CONFLICT
    assert on_disk(app, "SELECT text, intent_id FROM learned_examples") == [(FRESH, "abrir_app")]
    assert app.index.scores(FRESH)["abrir_app"] == pytest.approx(1.0)


def test_edit_of_a_missing_example(app: SazedApp) -> None:
    assert edit_example(app, 7, FRESH, "abrir_app") is LabelResult.UNKNOWN


# aliases -----------------------------------------------------------------------


def test_add_alias_resolves_the_catalog_name(app: SazedApp) -> None:
    assert add_alias(app.store, NAMES, " Zap ", "whatsapp", T) is AliasResult.SAVED
    assert on_disk(app, "SELECT slot, alias, value FROM slot_aliases") == [
        ("app", "zap", "WhatsApp")
    ]


@pytest.mark.parametrize(
    ("alias", "target", "result"),
    [
        ("zap", "Telegram", AliasResult.APP_UNKNOWN),
        ("", "WhatsApp", AliasResult.EMPTY),
        ("!!", "WhatsApp", AliasResult.EMPTY),
    ],
)
def test_add_alias_refusals(app: SazedApp, alias: str, target: str, result: AliasResult) -> None:
    assert add_alias(app.store, NAMES, alias, target, T) is result
    assert on_disk(app, "SELECT COUNT(*) FROM slot_aliases") == [(0,)]


def test_add_alias_never_overwrites_an_existing_one(app: SazedApp) -> None:
    app.store.learn([], [NewAlias("app", "zap", "WhatsApp")], datetime(2026, 10, 15))
    assert add_alias(app.store, NAMES, "Záp", "Discord", T) is AliasResult.EXISTS
    assert on_disk(app, "SELECT value FROM slot_aliases") == [("WhatsApp",)]


def test_edit_alias_target(app: SazedApp) -> None:
    add_alias(app.store, NAMES, "zap", "WhatsApp", T)
    assert edit_alias(app.store, NAMES, 1, "discord", T) is AliasResult.SAVED
    assert on_disk(app, "SELECT id, alias, value FROM slot_aliases") == [(1, "zap", "Discord")]
    assert edit_alias(app.store, NAMES, 1, "Telegram", T) is AliasResult.APP_UNKNOWN
    assert edit_alias(app.store, NAMES, 9, "Discord", T) is AliasResult.UNKNOWN


# forget ------------------------------------------------------------------------


def test_forget_takes_the_example_out_of_the_live_index(app: SazedApp) -> None:
    learn_example(app, FRESH, "abrir_app")
    assert forget_learned(app, "e1") is not None
    assert app.index.scores(FRESH)["abrir_app"] < 0.99
    assert learn_example(app, FRESH, "abrir_app") is LabelResult.LEARNED  # not "already known"
    assert app.store.examples()[0].text == FRESH
    assert [i.kind for i in app.store.learned()] == [LearnedKind.EXAMPLE]
