from sazed.core.learning import LearningThresholds, Verdict, judge_example

TH = LearningThresholds(t_conflict=0.85, t_dup=0.97)


def test_new_example_far_from_everything_is_saved() -> None:
    assert judge_example({"abrir_app": 0.80, "fechar_app": 0.60}, "abrir_app", TH) is Verdict.SAVE


def test_near_copy_of_same_intent_is_duplicate() -> None:
    assert judge_example({"abrir_app": 0.97}, "abrir_app", TH) is Verdict.DUPLICATE


def test_close_to_another_intent_is_conflict() -> None:
    assert (
        judge_example({"abrir_app": 0.80, "fechar_app": 0.85}, "abrir_app", TH) is Verdict.CONFLICT
    )


def test_just_below_conflict_threshold_saves() -> None:
    assert judge_example({"abrir_app": 0.80, "fechar_app": 0.849}, "abrir_app", TH) is Verdict.SAVE


def test_duplicate_wins_over_conflict() -> None:
    scores = {"abrir_app": 0.99, "fechar_app": 0.95}
    assert judge_example(scores, "abrir_app", TH) is Verdict.DUPLICATE


def test_ignored_intents_do_not_count_as_conflict() -> None:
    scores = {"abrir_app": 0.70, "fechar_app": 0.95}
    assert judge_example(scores, "abrir_app", TH, ignore=frozenset({"fechar_app"})) is Verdict.SAVE


def test_unknown_target_with_no_scores_is_saved() -> None:
    assert judge_example({}, "abrir_app", TH) is Verdict.SAVE
