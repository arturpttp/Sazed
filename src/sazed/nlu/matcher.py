"""Intent ranking by maximum cosine similarity over examples (seed + learned)."""

from collections.abc import Sequence
from typing import Protocol

import numpy as np
import numpy.typing as npt

from sazed.core.types import IntentScore, Ranking
from sazed.nlu.embedder import Embedder


class IntentIndex(Protocol):
    def rank(self, text: str) -> Ranking: ...
    def scores(self, text: str) -> dict[str, float]: ...
    def vectorize(self, text: str) -> bytes: ...
    def add(self, intent_id: str, text: str, vector: bytes) -> None: ...
    def remove(self, intent_id: str, text: str) -> bool: ...


class IntentMatcher:
    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._labels: list[tuple[str, str]] = []
        self._matrix: npt.NDArray[np.float32] = np.zeros((0, embedder.dim), dtype=np.float32)

    def add_examples(self, intent_id: str, texts: Sequence[str]) -> None:
        if not texts:
            return
        vectors = self._embedder.embed(list(texts))
        self._labels.extend((intent_id, t) for t in texts)
        self._matrix = np.vstack([self._matrix, vectors])

    def add(self, intent_id: str, text: str, vector: bytes) -> None:
        row = np.frombuffer(vector, dtype=np.float32)
        if row.shape != (self._embedder.dim,):
            raise ValueError(f"expected {self._embedder.dim} floats, got {row.shape}")
        self._labels.append((intent_id, text))
        self._matrix = np.vstack([self._matrix, row[np.newaxis, :]])

    def remove(self, intent_id: str, text: str) -> bool:
        try:
            i = self._labels.index((intent_id, text))
        except ValueError:
            return False
        del self._labels[i]
        self._matrix = np.delete(self._matrix, i, axis=0)
        return True

    def vectorize(self, text: str) -> bytes:
        return self._embed_one(text).astype(np.float32).tobytes()

    def scores(self, text: str) -> dict[str, float]:
        if not self._labels:
            return {}
        sims = self._matrix @ self._embed_one(text)
        best: dict[str, float] = {}
        for (intent_id, _), sim in zip(self._labels, sims, strict=True):
            if intent_id not in best or sim > best[intent_id]:
                best[intent_id] = float(sim)
        return best

    def rank(self, text: str) -> Ranking:
        ordered = sorted(self.scores(text).items(), key=lambda kv: (-kv[1], kv[0]))
        return tuple(IntentScore(i, s) for i, s in ordered)

    def _embed_one(self, text: str) -> npt.NDArray[np.float32]:
        row: npt.NDArray[np.float32] = self._embedder.embed([text])[0]
        return row
