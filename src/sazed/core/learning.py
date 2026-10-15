"""Safeguards on what may be learned. Pure: similarities are computed by the caller."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class LearningThresholds:
    t_conflict: float
    t_dup: float


class Verdict(Enum):
    SAVE = "save"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


def judge_example(
    scores: Mapping[str, float],
    target: str,
    th: LearningThresholds,
    ignore: frozenset[str] = frozenset(),
) -> Verdict:
    """Decide whether `target` may learn a candidate whose per-intent max similarity is `scores`.

    `ignore` names intents the user has just explicitly ruled out (a correction away from
    them), so resembling them is expected rather than a conflict.
    """
    if scores.get(target, 0.0) >= th.t_dup:
        return Verdict.DUPLICATE
    other = max(
        (s for intent, s in scores.items() if intent != target and intent not in ignore),
        default=0.0,
    )
    if other >= th.t_conflict:
        return Verdict.CONFLICT
    return Verdict.SAVE
