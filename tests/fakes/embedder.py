"""Deterministic stand-in for the real model: character trigrams hashed into buckets."""

import zlib
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from sazed.nlu.normalize import strip_accents


class HashingEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> npt.NDArray[np.float32]:
        out = np.zeros((len(texts), self._dim), dtype=np.float32)
        for row, text in enumerate(texts):
            padded = f"  {strip_accents(text.lower())} "
            for i in range(len(padded) - 2):
                out[row, zlib.crc32(padded[i : i + 3].encode()) % self._dim] += 1.0
            norm = float(np.linalg.norm(out[row]))
            if norm > 0:
                out[row] /= norm
        return out
