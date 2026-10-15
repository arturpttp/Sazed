from datetime import datetime

from sazed.core.decisions import AskSlot, Confirm, ConfirmReason, Execute, NotUnderstood
from sazed.core.policy import IntentRequirements, Thresholds, decide
from sazed.core.types import (
    Ambiguous,
    Extraction,
    IntentScore,
    ParseResult,
    SlotValue,
    Unmatched,
    Utterance,
)

TH = Thresholds(t_exec=0.90, t_confirm=0.70, g_min=0.05)
NOW = datetime(2026, 10, 14, 12, 0)
APP = SlotValue("app", "Google Chrome", "chrome", 1.0, exact=True)
NEEDS_APP = IntentRequirements(required=frozenset({"app"}), requires_confirmation=False)
NO_SLOTS = IntentRequirements(required=frozenset(), requires_confirmation=False)


def parse(*scores: tuple[str, float], slots: dict[str, Extraction] | None = None) -> ParseResult:
    utterance = Utterance("abre o chrome", "abre o chrome", NOW)
    ranking = tuple(IntentScore(i, s) for i, s in scores)
    return ParseResult(utterance, ranking, slots or {}, frozenset())


def test_high_score_wide_gap_and_resolved_slots_execute() -> None:
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.80), slots={"app": APP}), NEEDS_APP, TH)
    assert d == Execute("abrir_app", {"app": APP})


def test_score_exactly_at_t_exec_executes() -> None:
    d = decide(parse(("volume_mudo", 0.90), ("abrir_app", 0.50)), NO_SLOTS, TH)
    assert d == Execute("volume_mudo", {})


def test_score_in_confirm_band_confirms_with_low_score_reason() -> None:
    d = decide(parse(("volume_mudo", 0.85), ("abrir_app", 0.50)), NO_SLOTS, TH)
    assert d == Confirm("volume_mudo", {}, ConfirmReason.LOW_SCORE)


def test_score_exactly_at_t_confirm_still_confirms() -> None:
    d = decide(parse(("volume_mudo", 0.70), ("abrir_app", 0.10)), NO_SLOTS, TH)
    assert d == Confirm("volume_mudo", {}, ConfirmReason.LOW_SCORE)


def test_score_below_t_confirm_is_not_understood() -> None:
    d = decide(parse(("volume_mudo", 0.69), ("abrir_app", 0.10)), NO_SLOTS, TH)
    assert d == NotUnderstood()


def test_small_gap_confirms_even_above_t_exec() -> None:
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.93), slots={"app": APP}), NEEDS_APP, TH)
    assert d == Confirm("abrir_app", {"app": APP}, ConfirmReason.SMALL_GAP)


def test_gap_just_above_g_min_executes() -> None:
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.89), slots={"app": APP}), NEEDS_APP, TH)
    assert d == Execute("abrir_app", {"app": APP})


def test_destructive_intent_confirms_even_at_top_score() -> None:
    req = IntentRequirements(required=frozenset({"app"}), requires_confirmation=True)
    d = decide(parse(("fechar_app", 0.99), ("abrir_app", 0.50), slots={"app": APP}), req, TH)
    assert d == Confirm("fechar_app", {"app": APP}, ConfirmReason.DESTRUCTIVE)


def test_missing_required_slot_asks_for_it() -> None:
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.50)), NEEDS_APP, TH)
    assert d == AskSlot("abrir_app", {}, "app", (), "")


def test_ambiguous_slot_asks_with_candidates() -> None:
    amb = Ambiguous("app", "code", ("Claude Code", "Visual Studio Code"))
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.5), slots={"app": amb}), NEEDS_APP, TH)
    assert d == AskSlot("abrir_app", {}, "app", ("Claude Code", "Visual Studio Code"), "code")


def test_unmatched_slot_counts_as_given_so_the_skill_can_report_it() -> None:
    gone = Unmatched("app", "discordia", None)
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.5), slots={"app": gone}), NEEDS_APP, TH)
    assert d == Execute("abrir_app", {"app": gone})


def test_empty_ranking_is_not_understood() -> None:
    assert decide(parse(), NO_SLOTS, TH) == NotUnderstood()


def test_single_intent_gap_is_measured_against_zero() -> None:
    assert decide(parse(("volume_mudo", 0.95)), NO_SLOTS, TH) == Execute("volume_mudo", {})
