"""Sweep t_exec / t_confirm / g_min over the NLU fixture; print the settings that serve best.

Usage: uv run python scripts/tune_thresholds.py
"""

from functools import lru_cache
from pathlib import Path

from sazed.adapters.onnx.embedder import OnnxEmbedder
from sazed.core.policy import Thresholds
from sazed.nlu.matcher import IntentMatcher
from sazed.runtime.config import DEFAULT_MODEL_DIR
from sazed.runtime.evaluation import (
    MAX_FALSE_EXECUTE,
    MIN_ACCURACY,
    DryRunPorts,
    evaluate,
    load_cases,
)
from sazed.skills.pc.apps import AppsSkill
from sazed.skills.pc.volume import VolumeSkill

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "nlu_cases.toml"


class CachedIndex:
    def __init__(self, inner: IntentMatcher) -> None:
        self._inner = inner
        self.rank = lru_cache(maxsize=None)(inner.rank)
        self.scores = inner.scores
        self.vectorize = inner.vectorize
        self.add = inner.add
        self.remove = inner.remove


def main() -> None:
    app_names, cases = load_cases(FIXTURE)
    matcher = IntentMatcher(OnnxEmbedder(DEFAULT_MODEL_DIR))
    ports = DryRunPorts(app_names)
    for skill in (AppsSkill(ports, ports), VolumeSkill(ports)):
        for spec in skill.intents:
            matcher.add_examples(spec.id, spec.examples)
    index = CachedIndex(matcher)
    grid = []
    for e in range(80, 99):
        for c in range(60, e + 1, 2):
            for g in range(0, 7):
                th = Thresholds(e / 100, c / 100, g / 100)
                report = evaluate(cases, index=index, app_names=app_names, thresholds=th)  # type: ignore[arg-type]
                if (
                    report.accuracy >= MIN_ACCURACY
                    and report.false_execute_rate <= MAX_FALSE_EXECUTE
                ):
                    # Serve the person: a right execution is worth 1, a question 0.5,
                    # "not understood" 0. Ties go to the higher t_exec, then the higher
                    # t_confirm, so out-of-domain phrases stay "not understood".
                    served = report.executed_rate + 0.5 * report.asked_rate
                    grid.append((-served, -th.t_exec, -th.t_confirm, th, report))
    if not grid:
        print("No setting meets the thresholds. Improve seeds/fixture before tuning.")
        return
    grid.sort(key=lambda row: row[:3])
    for *_, th, report in grid[:5]:
        print(
            f"{th}  accuracy={report.accuracy:.3f}  false_exec={report.false_execute_rate:.3f}"
            f"  executed={report.executed_rate:.3f}  asked={report.asked_rate:.3f}"
            f"  not_understood={report.not_understood_rate:.3f}"
        )


if __name__ == "__main__":
    main()
