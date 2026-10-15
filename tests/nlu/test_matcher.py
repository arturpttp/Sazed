import numpy as np
import pytest

from fakes.embedder import HashingEmbedder
from sazed.nlu.matcher import IntentMatcher


@pytest.fixture
def matcher() -> IntentMatcher:
    m = IntentMatcher(HashingEmbedder())
    m.add_examples("abrir_app", ["abre o chrome", "abra o spotify"])
    m.add_examples("volume_aumentar", ["aumenta o volume", "sobe o som"])
    return m


def test_exact_example_scores_one_and_ranks_first(matcher: IntentMatcher) -> None:
    ranking = matcher.rank("abre o chrome")
    assert ranking[0].intent_id == "abrir_app"
    assert ranking[0].score == pytest.approx(1.0, abs=1e-5)


def test_intent_score_is_the_max_over_its_examples(matcher: IntentMatcher) -> None:
    embedder = HashingEmbedder()
    q, a, b = embedder.embed(["sobe o som agora", "aumenta o volume", "sobe o som"])
    expected = max(float(q @ a), float(q @ b))
    assert matcher.scores("sobe o som agora")["volume_aumentar"] == pytest.approx(
        expected, abs=1e-5
    )


def test_ranking_is_sorted_descending(matcher: IntentMatcher) -> None:
    scores = [s.score for s in matcher.rank("aumenta o volume do chrome")]
    assert scores == sorted(scores, reverse=True)


def test_empty_matcher_ranks_nothing() -> None:
    m = IntentMatcher(HashingEmbedder())
    assert m.rank("abre o chrome") == ()
    assert m.scores("abre o chrome") == {}


def test_vectorize_and_add_round_trip(matcher: IntentMatcher) -> None:
    text = "liga o navegador"
    matcher.add("abrir_app", text, matcher.vectorize(text))
    assert matcher.scores(text)["abrir_app"] == pytest.approx(1.0, abs=1e-5)


def test_add_rejects_a_vector_of_the_wrong_size(matcher: IntentMatcher) -> None:
    with pytest.raises(ValueError):
        matcher.add("abrir_app", "x", np.zeros(3, dtype=np.float32).tobytes())


def test_remove_drops_only_that_example(matcher: IntentMatcher) -> None:
    assert matcher.remove("abrir_app", "abre o chrome") is True
    assert matcher.rank("abre o chrome")[0].score < 0.999
    assert matcher.remove("abrir_app", "abre o chrome") is False
    assert "abrir_app" in matcher.scores("abra o spotify")


def test_add_examples_embeds_in_one_batch() -> None:
    calls: list[int] = []

    class Spy(HashingEmbedder):
        def embed(self, texts):  # type: ignore[no-untyped-def]
            calls.append(len(texts))
            return super().embed(texts)

    IntentMatcher(Spy()).add_examples("abrir_app", ["a", "b", "c"])
    assert calls == [3]
