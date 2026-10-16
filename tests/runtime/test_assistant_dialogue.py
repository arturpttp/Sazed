from collections.abc import Sequence
from datetime import datetime

from sazed.core.coppermind import Reaction
from sazed.core.decisions import AskSlot, Confirm, ConfirmReason, NotUnderstood
from sazed.core.outcomes import AmbiguousSlot, AppOpened, Cancelled, NothingToRepeat, Outcome
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue
from support.harness import Make

LOW_CHROME = {"abre aí o chrome": {"abrir_app": 0.80, "fechar_app": 0.30}}
VOLUME_30 = {"volume em 30": {"volume_definir": 0.97, "volume_aumentar": 0.70}}
OPEN_SOMETHING = {"abre o programa": {"abrir_app": 0.95, "fechar_app": 0.40}}


def test_yes_executes_the_confirmed_command(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    r = h.say("sim")
    assert h.launcher.launched == ["Google Chrome"]
    assert r.outcome == AppOpened("Google Chrome")


def test_yes_marks_the_question_episode_confirmed(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.say("sim")
    question = h.store.episodes(2)[1]
    assert question.episode.reaction is Reaction.CONFIRMED


def test_no_cancels_and_marks_the_question_denied(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    r = h.say("não")
    assert r.outcome == Cancelled()
    assert h.launcher.launched == []
    assert h.store.episodes(2)[1].episode.reaction is Reaction.DENIED


def test_unrelated_reply_drops_pending_and_is_understood(make: Make) -> None:
    h = make({**LOW_CHROME, **VOLUME_30})
    h.say("abre aí o chrome")
    h.say("volume em 30")
    assert h.audio.volume == 30
    assert h.say("sim").decision == NotUnderstood()
    assert h.launcher.launched == []


def test_yes_with_nothing_pending_is_not_understood(make: Make) -> None:
    h = make()
    assert h.say("sim").decision == NotUnderstood()


def test_yes_after_ttl_is_not_understood(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.clock.advance(61)
    assert h.say("sim").decision == NotUnderstood()
    assert h.launcher.launched == []


def test_yes_exactly_at_ttl_is_still_an_answer(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.clock.advance(60)
    h.say("sim")
    assert h.launcher.launched == ["Google Chrome"]


def test_missing_slot_answer_completes_the_command(make: Make) -> None:
    h = make(OPEN_SOMETHING)
    h.say("abre o programa")
    h.say("o spotify")
    assert h.launcher.launched == ["Spotify"]


def test_new_command_instead_of_a_slot_answer_is_handled_as_a_command(make: Make) -> None:
    h = make({**OPEN_SOMETHING, **VOLUME_30})
    h.say("abre o programa")
    h.say("volume em 30")
    assert h.audio.volume == 30
    assert h.launcher.launched == []


def test_yes_to_a_slot_question_is_not_an_app_name(make: Make) -> None:
    h = make(OPEN_SOMETHING)
    h.say("abre o programa")
    assert h.say("sim").decision == NotUnderstood()
    assert h.launcher.launched == []


def test_ambiguous_app_is_chosen_by_ordinal(make: Make) -> None:
    h = make({"abre o code": {"abrir_app": 0.95, "fechar_app": 0.40}})
    r = h.say("abre o code")
    assert "1) Claude Code, 2) Visual Studio Code" in r.text
    h.say("o segundo")
    assert h.launcher.launched == ["Visual Studio Code"]


def test_destructive_close_confirms_then_closes(make: Make) -> None:
    h = make(
        {"fecha o chrome": {"fechar_app": 0.97, "abrir_app": 0.60}}, running={"Google Chrome": 2}
    )
    r = h.say("fecha o chrome")
    assert isinstance(r.decision, Confirm) and r.decision.reason is ConfirmReason.DESTRUCTIVE
    assert h.launcher.closed == []
    h.say("sim")
    assert h.launcher.closed == ["Google Chrome"]


def test_slot_answer_for_a_destructive_close_still_confirms(make: Make) -> None:
    h = make(
        {"fecha o programa": {"fechar_app": 0.95, "abrir_app": 0.4}}, running={"Google Chrome": 2}
    )
    h.say("fecha o programa")
    r = h.say("o chrome")
    assert isinstance(r.decision, Confirm)
    assert h.launcher.closed == []
    h.say("sim")
    assert h.launcher.closed == ["Google Chrome"]


def test_repeat_reruns_the_last_command(make: Make) -> None:
    h = make({"aumenta o volume": {"volume_aumentar": 0.97, "volume_diminuir": 0.6}})
    h.say("aumenta o volume")
    h.say("de novo")
    assert h.audio.volume == 70


def test_repeat_after_ttl_does_not_rerun(make: Make) -> None:
    h = make({"aumenta o volume": {"volume_aumentar": 0.97, "volume_diminuir": 0.6}})
    h.say("aumenta o volume")
    h.clock.advance(61)
    assert h.say("de novo").outcome == NothingToRepeat()
    assert h.audio.volume == 60


def test_not_found_with_suggestion_asks_and_yes_opens_it(make: Make) -> None:
    h = make({"abre o disc": {"abrir_app": 0.95, "fechar_app": 0.40}})
    r = h.say("abre o disc")
    assert "Discord" in r.text
    h.say("sim")
    assert h.launcher.launched == ["Discord"]


class PickySkill:
    """Returns AmbiguousSlot from execute, as a skill with its own disambiguation would."""

    id = "picky"
    intents: Sequence[IntentSpec] = (
        IntentSpec(
            "escolher",
            ("escolhe um",),
            (SlotSpec("app", False, "Qual deles?"),),
            describe=lambda s: "escolher um programa",
        ),
    )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        app = slots.get("app")
        if isinstance(app, SlotValue):
            return AppOpened(str(app.value))
        return AmbiguousSlot("app", ("Alfa", "Beta"))


def test_ambiguous_outcome_from_a_skill_becomes_a_question(make: Make) -> None:
    h = make({"escolhe um": {"escolher": 0.95}}, extra_skills=[PickySkill()])
    r = h.say("escolhe um")
    assert isinstance(r.decision, AskSlot)
    assert "1) Alfa, 2) Beta" in r.text
    assert h.say("o segundo").outcome == AppOpened("Beta")


def test_context_uses_the_injected_clock_only(make: Make) -> None:
    h = make(LOW_CHROME)
    h.clock.now = datetime(2030, 1, 1, 0, 0)
    h.say("abre aí o chrome")
    h.clock.advance(30)
    h.say("sim")
    assert h.launcher.launched == ["Google Chrome"]


def test_other_command_with_an_app_is_not_taken_as_the_slot_answer(make: Make) -> None:
    h = make({**OPEN_SOMETHING, "fecha o spotify": {"fechar_app": 0.97, "abrir_app": 0.60}})
    h.say("abre o programa")
    h.say("fecha o spotify")
    assert h.launcher.launched == []


def test_other_command_naming_a_candidate_is_not_the_choice(make: Make) -> None:
    h = make(
        {
            "abre o code": {"abrir_app": 0.95, "fechar_app": 0.40},
            "fecha o visual studio code": {"fechar_app": 0.97, "abrir_app": 0.60},
        }
    )
    h.say("abre o code")
    h.say("fecha o visual studio code")
    assert h.launcher.launched == []
    assert h.store.aliases() == []


def test_other_volume_command_is_not_taken_as_the_percent_answer(make: Make) -> None:
    h = make(
        {
            "volume": {"volume_definir": 0.95, "volume_aumentar": 0.60},
            "aumenta o volume em 20": {"volume_aumentar": 0.97, "volume_definir": 0.70},
        }
    )
    h.say("volume")
    h.say("aumenta o volume em 20")
    assert h.audio.volume == 70


def test_bare_yes_is_never_offered_as_a_rephrase(make: Make) -> None:
    h = make({"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60}})
    h.say("sim")
    r = h.say("abre o chrome")
    assert "'sim'" not in r.text
    h.say("sim")
    assert h.store.learned() == []


def test_repeat_does_not_reopen_an_app(make: Make) -> None:
    h = make({"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60}})
    h.say("abre o chrome")
    r = h.say("mais")
    assert h.launcher.launched == ["Google Chrome"]
    assert r.outcome == NothingToRepeat()


def test_bare_more_with_nothing_to_repeat_is_never_ranked(make: Make) -> None:
    h = make({"mais": {"volume_aumentar": 0.99, "volume_diminuir": 0.5}})
    r = h.say("mais")
    assert r.outcome == NothingToRepeat()
    assert h.audio.volume == 50


def test_search_without_a_query_asks_and_takes_a_bare_answer(make: Make) -> None:
    h = make({"pesquisa no youtube": {"pesquisar": 0.97, "abrir_app": 0.5}})
    r = h.say("pesquisa no youtube")
    assert isinstance(r.decision, AskSlot)
    assert "O que devo pesquisar?" in r.text
    h.say("lofi")
    assert h.opener.opened == ["https://www.youtube.com/results?search_query=lofi"]
