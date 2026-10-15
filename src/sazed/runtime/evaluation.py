"""Run labelled phrases through the real decision path with dry-run ports.

Used by the NLU fixture test and scripts/tune_thresholds.py. Each case gets a fresh
Assistant, so cases never influence each other; the index is shared (embeddings are the
expensive part).
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from random import Random

from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.decisions import AskSlot, Confirm, Decision, Execute, NotUnderstood
from sazed.core.learning import LearningThresholds
from sazed.core.policy import Thresholds
from sazed.core.types import SlotValue, Unmatched
from sazed.nlu.matcher import IntentIndex
from sazed.nlu.normalize import normalize
from sazed.runtime.assistant import Assistant, Settings
from sazed.runtime.extractors import build_extractors
from sazed.skills.pc.apps import AppEntry, AppsSkill
from sazed.skills.pc.volume import VolumeSkill

NO_INTENT = "none"
MIN_ACCURACY = 0.90
MAX_FALSE_EXECUTE = 0.02
_FIXED_TIME = datetime(2026, 1, 1, 12, 0)


@dataclass(frozen=True)
class NluCase:
    text: str
    intent: str
    app: str | None = None
    percent: int | None = None
    alvo: int | None = None


@dataclass(frozen=True)
class CaseResult:
    case: NluCase
    top_intent: str | None
    decision: Decision | None


@dataclass(frozen=True)
class Report:
    results: list[CaseResult] = field(default_factory=list)
    accuracy: float = 0.0
    false_execute_rate: float = 0.0
    confirm_rate: float = 0.0
    executed_rate: float = 0.0
    """In-domain cases executed with the right intent and slots."""
    asked_rate: float = 0.0
    """In-domain cases answered with a confirmation or a slot question."""
    not_understood_rate: float = 0.0
    """In-domain cases Sazed did not understand at all."""

    def false_executes(self) -> list[CaseResult]:
        return [r for r in self.results if _is_false_execute(r)]

    def misranked(self) -> list[CaseResult]:
        return [
            r for r in self.results if r.case.intent != NO_INTENT and r.top_intent != r.case.intent
        ]


class DryRunPorts:
    """Ports that do nothing: evaluation must never open apps or change the volume."""

    def __init__(self, names: Sequence[str]) -> None:
        self._entries = [AppEntry(n, f"{n}.exe", f"{n}.lnk") for n in names]

    def entries(self) -> Sequence[AppEntry]:
        return self._entries

    def launch(self, entry: AppEntry) -> None:
        return None

    def instances(self, entry: AppEntry) -> int:
        return 1

    def close(self, entry: AppEntry) -> int:
        return 1

    def get_volume(self) -> int:
        return 50

    def set_volume(self, percent: int) -> None:
        return None

    def set_muted(self, muted: bool) -> None:
        return None


def _is_false_execute(result: CaseResult) -> bool:
    decision, case = result.decision, result.case
    if not isinstance(decision, Execute):
        return False
    if isinstance(decision.slots.get("app"), Unmatched):
        # The skill can only answer "não encontrei": nothing happens on the machine.
        return False
    if case.intent == NO_INTENT or decision.intent_id != case.intent:
        return True
    for name, expected in (("app", case.app), ("percent", case.percent), ("alvo", case.alvo)):
        if expected is None:
            continue
        value = decision.slots.get(name)
        if not isinstance(value, SlotValue) or value.value != expected:
            return True
    return False


def _executed_correctly(result: CaseResult) -> bool:
    return isinstance(result.decision, Execute) and not _is_false_execute(result)


def _share(results: Sequence[CaseResult], test: Callable[[CaseResult], bool]) -> float:
    return sum(1 for r in results if test(r)) / len(results) if results else 0.0


def load_cases(path: Path) -> tuple[list[str], list[NluCase]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cases = [
        NluCase(c["text"], c["intent"], c.get("app"), c.get("percent"), c.get("alvo"))
        for c in data["case"]
    ]
    return list(data["apps"]), cases


def evaluate(
    cases: Sequence[NluCase],
    *,
    index: IntentIndex,
    app_names: Sequence[str],
    thresholds: Thresholds,
) -> Report:
    ports = DryRunPorts(app_names)
    settings = Settings("Artur", thresholds, LearningThresholds(1.0, 1.0), 60.0)
    results: list[CaseResult] = []
    for case in cases:
        assistant = Assistant(
            skills=[AppsSkill(ports, ports), VolumeSkill(ports)],
            index=index,
            extractors=build_extractors(app_names),
            store=SqliteCoppermind(":memory:"),
            aliases={},
            settings=settings,
            clock=lambda: _FIXED_TIME,
            rng=Random(0),
        )
        ranking = index.rank(normalize(case.text))
        response = assistant.handle(case.text)
        results.append(
            CaseResult(case, ranking[0].intent_id if ranking else None, response.decision)
        )

    in_domain = [r for r in results if r.case.intent != NO_INTENT]
    correct = sum(1 for r in in_domain if r.top_intent == r.case.intent)
    asked = sum(1 for r in results if isinstance(r.decision, Confirm | AskSlot))
    return Report(
        results=results,
        accuracy=correct / len(in_domain) if in_domain else 1.0,
        false_execute_rate=sum(_is_false_execute(r) for r in results) / len(results),
        confirm_rate=asked / len(results),
        executed_rate=_share(in_domain, _executed_correctly),
        asked_rate=_share(in_domain, lambda r: isinstance(r.decision, Confirm | AskSlot)),
        not_understood_rate=_share(in_domain, lambda r: isinstance(r.decision, NotUnderstood)),
    )
