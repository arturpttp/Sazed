import pytest

from fakes.index import ScriptedIndex
from sazed.core.types import IntentScore


def test_rank_orders_scripted_scores_best_first_with_id_tiebreak() -> None:
    idx = ScriptedIndex({"x": {"b": 0.5, "a": 0.5, "c": 0.9}})
    assert idx.rank("x") == (IntentScore("c", 0.9), IntentScore("a", 0.5), IntentScore("b", 0.5))


def test_unknown_text_ranks_empty() -> None:
    assert ScriptedIndex().rank("nada") == ()


def test_learned_text_scores_one_for_its_intent() -> None:
    idx = ScriptedIndex({"abre ai o chrome": {"abrir_app": 0.8, "fechar_app": 0.4}})
    idx.add("abrir_app", "abre ai o chrome", idx.vectorize("abre ai o chrome"))
    assert idx.scores("abre ai o chrome") == {"abrir_app": 1.0, "fechar_app": 0.4}


def test_add_rejects_a_vector_of_another_text() -> None:
    idx = ScriptedIndex()
    with pytest.raises(ValueError):
        idx.add("abrir_app", "abre", idx.vectorize("fecha"))


def test_remove_reports_whether_something_was_removed() -> None:
    idx = ScriptedIndex()
    idx.add("abrir_app", "abre", idx.vectorize("abre"))
    assert idx.remove("abrir_app", "abre") is True
    assert idx.remove("abrir_app", "abre") is False
    assert idx.scores("abre") == {}
