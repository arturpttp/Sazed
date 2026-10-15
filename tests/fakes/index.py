"""IntentIndex whose scores are written by the test. A learned text scores 1.0 for its intent."""

from collections.abc import Mapping

from sazed.core.types import IntentScore, Ranking


class ScriptedIndex:
    def __init__(self, script: Mapping[str, Mapping[str, float]] | None = None) -> None:
        self._script = {text: dict(scores) for text, scores in (script or {}).items()}
        self.learned: list[tuple[str, str]] = []

    def scores(self, text: str) -> dict[str, float]:
        scores = dict(self._script.get(text, {}))
        for intent_id, learned_text in self.learned:
            if learned_text == text:
                scores[intent_id] = 1.0
        return scores

    def rank(self, text: str) -> Ranking:
        ordered = sorted(self.scores(text).items(), key=lambda kv: (-kv[1], kv[0]))
        return tuple(IntentScore(i, s) for i, s in ordered)

    def vectorize(self, text: str) -> bytes:
        return text.encode("utf-8")

    def add(self, intent_id: str, text: str, vector: bytes) -> None:
        if vector != self.vectorize(text):
            raise ValueError("vector does not belong to this text")
        self.learned.append((intent_id, text))

    def remove(self, intent_id: str, text: str) -> bool:
        try:
            self.learned.remove((intent_id, text))
        except ValueError:
            return False
        return True
