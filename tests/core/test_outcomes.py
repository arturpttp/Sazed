from typing import get_args

from sazed.core.outcomes import (
    FAILURE_NAMES,
    ActionFailed,
    AppNotFound,
    AppOpened,
    Failure,
    Outcome,
    is_failure,
)


def test_every_failure_is_an_outcome() -> None:
    assert set(get_args(Failure)) <= set(get_args(Outcome))


def test_failure_names_are_derived_from_the_failure_union() -> None:
    assert {t.__name__ for t in get_args(Failure)} == FAILURE_NAMES


def test_is_failure_separates_failures_from_successes() -> None:
    assert is_failure(AppNotFound("x", None))
    assert is_failure(ActionFailed("abrir x"))
    assert not is_failure(AppOpened("Google Chrome"))
    assert not is_failure(None)
