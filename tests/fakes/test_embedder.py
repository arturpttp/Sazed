import numpy as np

from fakes.embedder import HashingEmbedder


def test_same_text_gives_same_vector() -> None:
    e = HashingEmbedder()
    a, b = e.embed(["abre o chrome", "abre o chrome"])
    assert np.array_equal(a, b)


def test_different_texts_give_different_vectors() -> None:
    a, b = HashingEmbedder().embed(["abre o chrome", "fecha o spotify"])
    assert not np.array_equal(a, b)


def test_rows_are_unit_length_with_declared_dim() -> None:
    out = HashingEmbedder(dim=64).embed(["abre o chrome", "volume em trinta"])
    assert out.shape == (2, 64)
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)


def test_lexically_similar_texts_are_closer_than_unrelated_ones() -> None:
    base, near, far = HashingEmbedder().embed(
        ["abre o chrome", "abre o chrome agora", "volume em trinta"]
    )
    assert float(base @ near) > float(base @ far)


def test_empty_text_gives_zero_vector_not_nan() -> None:
    (row,) = HashingEmbedder().embed([""])
    assert not np.isnan(row).any()
