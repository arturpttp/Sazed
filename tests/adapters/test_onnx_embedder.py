import numpy as np
import pytest

from sazed.adapters.onnx.embedder import OnnxEmbedder
from sazed.runtime.config import DEFAULT_MODEL_DIR

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def embedder() -> OnnxEmbedder:
    if not (DEFAULT_MODEL_DIR / "model.onnx").exists():
        pytest.fail("model missing: run `uv run python scripts/fetch_model.py` first")
    return OnnxEmbedder(DEFAULT_MODEL_DIR)


def test_rows_are_unit_length_384_floats(embedder: OnnxEmbedder) -> None:
    out = embedder.embed(["abre o chrome", "aumenta o volume"])
    assert out.shape == (2, 384) and out.dtype == np.float32
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0, atol=1e-5)
    assert embedder.dim == 384


def test_same_text_same_vector(embedder: OnnxEmbedder) -> None:
    a, b = embedder.embed(["abre o chrome", "abre o chrome"])
    assert np.allclose(a, b, atol=1e-6)


def test_batch_mates_do_not_change_a_sentence_vector(embedder: OnnxEmbedder) -> None:
    alone = embedder.embed(["abre o chrome"])[0]
    batched = embedder.embed(
        ["abre o chrome", "uma frase bem mais longa para forçar padding no lote"]
    )[0]
    assert np.allclose(alone, batched, atol=1e-4)


def test_paraphrase_is_closer_than_another_intent(embedder: OnnxEmbedder) -> None:
    base, para, other = embedder.embed(
        ["abre o chrome", "abra o google chrome", "aumenta o volume"]
    )
    assert float(base @ para) > float(base @ other)


def test_empty_batch(embedder: OnnxEmbedder) -> None:
    assert embedder.embed([]).shape == (0, 384)
