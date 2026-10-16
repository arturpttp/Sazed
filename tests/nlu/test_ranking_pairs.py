"""Phrases the final review found misranked with the real model. None of them is a seed."""

import pytest

from sazed.adapters.onnx.embedder import OnnxEmbedder
from sazed.nlu.matcher import IntentMatcher
from sazed.nlu.normalize import normalize
from sazed.runtime.config import DEFAULT_MODEL_DIR
from sazed.runtime.evaluation import dry_run_skills

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def index() -> IntentMatcher:
    if not (DEFAULT_MODEL_DIR / "model.onnx").exists():
        pytest.fail("model missing: run `uv run python scripts/fetch_model.py` first")
    matcher = IntentMatcher(OnnxEmbedder(DEFAULT_MODEL_DIR))
    for skill in dry_run_skills([]).skills:
        for spec in skill.intents:
            matcher.add_examples(spec.id, spec.examples)
    return matcher


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        # Closing a site must rank as closing (it then answers CannotCloseSite), never as opening.
        ("fecha o gmail aí", "fechar_app"),
        ("fecha o github", "fechar_app"),
        ("fecha o youtube pra mim", "fechar_app"),
        # Unmuting the computer must never rank as a power action.
        ("desmuta o computador", "volume_mudo"),
    ],
)
def test_review_pairs_rank_the_right_intent(index: IntentMatcher, text: str, intent: str) -> None:
    ranking = index.rank(normalize(text))
    assert ranking[0].intent_id == intent, [(s.intent_id, round(s.score, 3)) for s in ranking[:3]]
