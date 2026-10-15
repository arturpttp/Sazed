from datetime import datetime

from fakes.index import ScriptedIndex
from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.coppermind import LearnedKind, NewAlias, NewExample, Reaction
from sazed.core.decisions import AskSlot, Confirm, Execute
from sazed.core.outcomes import AppOpened, ExampleLearned, Forgotten, NothingToForget
from support.harness import Make

LOW_CHROME = {"abre aí o chrome": {"abrir_app": 0.80, "fechar_app": 0.30}}
CODE = {"abre o code": {"abrir_app": 0.95, "fechar_app": 0.40}}
T0 = datetime(2026, 10, 14, 11, 0)


def learned(h) -> list[tuple[LearnedKind, str, str]]:  # type: ignore[no-untyped-def]
    return [(i.kind, i.text, i.target) for i in h.store.learned()]


def test_confirmed_command_is_learned_and_executes_next_time(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.say("sim")
    assert learned(h) == [(LearnedKind.EXAMPLE, "abre aí o chrome", "abrir_app")]
    assert isinstance(h.say("abre aí o chrome").decision, Execute)
    assert h.launcher.launched == ["Google Chrome", "Google Chrome"]


def test_destructive_confirmation_teaches_nothing(make: Make) -> None:
    h = make(
        {"fecha o chrome": {"fechar_app": 0.97, "abrir_app": 0.6}}, running={"Google Chrome": 2}
    )
    h.say("fecha o chrome")
    h.say("sim")
    assert learned(h) == []


def test_denied_confirmation_teaches_nothing(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.say("não")
    assert learned(h) == []


def test_conflicting_example_is_asked_before_saving(make: Make) -> None:
    h = make(
        {"fecha aí o chrome": {"fechar_app": 0.88, "abrir_app": 0.86}}, running={"Google Chrome": 1}
    )
    h.say("fecha aí o chrome")
    r = h.say("sim")
    assert h.launcher.closed == ["Google Chrome"]
    assert "fecha aí o chrome" in r.text
    assert learned(h) == []
    r = h.say("sim")
    assert isinstance(r.outcome, ExampleLearned)
    assert learned(h) == [(LearnedKind.EXAMPLE, "fecha aí o chrome", "fechar_app")]


def test_near_duplicate_is_not_saved(make: Make) -> None:
    h = make({"abre o chrome agora": {"abrir_app": 0.98, "fechar_app": 0.95}})
    assert isinstance(h.say("abre o chrome agora").decision, Confirm)
    h.say("sim")
    assert h.launcher.launched == ["Google Chrome"]
    assert learned(h) == []


def test_choosing_an_ambiguous_app_learns_the_alias(make: Make) -> None:
    h = make(CODE)
    h.say("abre o code")
    r = h.say("o segundo")
    assert learned(h) == [(LearnedKind.ALIAS, "code", "Visual Studio Code")]
    assert "'code'" in r.text
    assert isinstance(h.say("abre o code").decision, Execute)
    assert h.launcher.launched == ["Visual Studio Code", "Visual Studio Code"]


def test_naming_the_app_after_not_found_learns_the_alias(make: Make) -> None:
    h = make({"abre o zap": {"abrir_app": 0.95, "fechar_app": 0.40}})
    h.say("abre o zap")
    h.say("é o discord")
    assert h.launcher.launched == ["Discord"]
    assert learned(h) == [(LearnedKind.ALIAS, "zap", "Discord")]
    assert h.store.episodes(2)[1].episode.reaction is Reaction.CORRECTED


def test_accepted_suggestion_learns_the_alias(make: Make) -> None:
    h = make({"abre o disc": {"abrir_app": 0.95, "fechar_app": 0.40}})
    h.say("abre o disc")
    h.say("sim")
    assert learned(h) == [(LearnedKind.ALIAS, "disc", "Discord")]


def test_correction_after_a_wrong_execution_learns_the_right_intent(make: Make) -> None:
    h = make(
        {
            "fecha o chrome": {"abrir_app": 0.93, "fechar_app": 0.80},
            "fechar": {"fechar_app": 0.91, "abrir_app": 0.50},
        }
    )
    h.say("fecha o chrome")
    assert h.launcher.launched == ["Google Chrome"]
    h.say("não, era pra fechar")
    assert h.launcher.closed == ["Google Chrome"]
    assert learned(h) == [(LearnedKind.EXAMPLE, "fecha o chrome", "fechar_app")]
    assert h.store.episodes(2)[1].episode.reaction is Reaction.CORRECTED


def test_correcting_only_the_app_reruns_with_the_new_one(make: Make) -> None:
    h = make({"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60}})
    h.say("abre o chrome")
    h.say("não, era o spotify")
    assert h.launcher.launched == ["Google Chrome", "Spotify"]
    assert learned(h) == []


def test_rephrase_after_not_understood_offers_to_learn(make: Make) -> None:
    h = make({"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60}})
    h.say("chrome por favor abre")
    r = h.say("abre o chrome")
    assert "chrome por favor abre" in r.text
    r = h.say("sim")
    assert isinstance(r.outcome, ExampleLearned)
    assert learned(h) == [(LearnedKind.EXAMPLE, "chrome por favor abre", "abrir_app")]
    assert isinstance(h.say("chrome por favor abre").decision, Execute)
    assert h.launcher.launched == ["Google Chrome", "Google Chrome"]


def test_declined_offer_learns_nothing(make: Make) -> None:
    h = make({"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60}})
    h.say("liga o navegador")
    h.say("abre o chrome")
    h.say("não")
    assert learned(h) == []


def test_forget_removes_the_latest_alias_from_store_and_memory(make: Make) -> None:
    h = make(CODE)
    h.say("abre o code")
    h.say("o segundo")
    r = h.say("esquece isso")
    assert isinstance(r.outcome, Forgotten)
    assert h.store.aliases() == []
    assert isinstance(h.say("abre o code").decision, AskSlot)


def test_forget_removes_a_learned_example_from_the_index(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.say("sim")
    h.say("esquece isso")
    assert h.index.learned == []
    assert isinstance(h.say("abre aí o chrome").decision, Confirm)


def test_forget_with_nothing_learned(make: Make) -> None:
    assert make().say("esquece isso").outcome == NothingToForget()


def test_learned_state_is_loaded_at_startup(make: Make) -> None:
    store = SqliteCoppermind(":memory:")
    vector = ScriptedIndex().vectorize("liga o navegador")
    store.learn(
        [NewExample("liga o navegador", "abrir_app", vector, "confirmed")],
        [NewAlias("app", "zap", "Discord")],
        T0,
    )
    h = make({"abre o zap": {"abrir_app": 0.95, "fechar_app": 0.4}}, store=store)
    assert h.index.learned == [("abrir_app", "liga o navegador")]
    h.say("abre o zap")
    assert h.launcher.launched == ["Discord"]


def test_forgetting_a_learned_alias_restores_the_configured_one(make: Make) -> None:
    store = SqliteCoppermind(":memory:")
    store.learn([], [NewAlias("app", "code", "Visual Studio Code")], T0)
    h = make(CODE, aliases={"code": "Claude Code"}, store=store)
    h.say("abre o code")
    h.say("esquece isso")
    h.say("abre o code")
    assert h.launcher.launched == ["Visual Studio Code", "Claude Code"]


def test_correction_marks_the_corrected_command_not_a_later_reply(make: Make) -> None:
    h = make(
        {
            "fecha o chrome": {"abrir_app": 0.93, "fechar_app": 0.80},
            "fechar": {"fechar_app": 0.91, "abrir_app": 0.50},
        }
    )
    h.say("fecha o chrome")  # misfires: opens
    h.say("sim")  # nothing pending: not understood, not remembered
    h.say("não, era pra fechar")
    newest_first = h.store.episodes(3)
    assert newest_first[2].episode.utterance == "fecha o chrome"
    assert newest_first[2].episode.reaction is Reaction.CORRECTED
    assert newest_first[1].episode.reaction is Reaction.NONE


class FailingLearnStore(SqliteCoppermind):
    def learn(self, examples, aliases, now):  # type: ignore[no-untyped-def]
        raise OSError("disk full: secret internals")


def test_a_learning_failure_after_a_confirmed_action_keeps_the_action(make: Make) -> None:
    h = make(LOW_CHROME, store=FailingLearnStore(":memory:"))
    h.say("abre aí o chrome")
    r = h.say("sim")
    assert h.launcher.launched == ["Google Chrome"]
    assert r.outcome == AppOpened("Google Chrome")
    assert "não consegui guardar" in r.text
    assert "secret internals" not in r.text
