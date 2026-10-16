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
from sazed.core.decisions import (
    AskSlot,
    Confirm,
    ConfirmReason,
    Decision,
    Execute,
    NotUnderstood,
)
from sazed.core.learning import LearningThresholds
from sazed.core.policy import Thresholds
from sazed.core.types import SlotValue, Unmatched
from sazed.nlu.matcher import IntentIndex
from sazed.nlu.normalize import normalize
from sazed.runtime.assistant import Assistant, Settings
from sazed.runtime.config import Config
from sazed.runtime.skills import PcPorts, SkillSet, build_skills
from sazed.skills.pc.apps import AppEntry
from sazed.skills.pc.fileops import Area, ItemState
from sazed.skills.pc.files import KNOWN_FOLDERS, FileHit
from sazed.skills.pc.media import NowPlayingInfo
from sazed.skills.pc.windows import Monitor, Rect, WindowRef

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
    consulta: str | None = None
    pagina: str | None = None
    site: str | None = None
    lado: str | None = None
    pasta: str | None = None
    arquivo: str | None = None


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
    """Ports that do nothing: evaluation must never touch the machine."""

    def __init__(self, names: Sequence[str]) -> None:
        self._entries = [AppEntry(n, f"{n}.exe", f"{n}.lnk") for n in names]

    # apps
    def entries(self) -> Sequence[AppEntry]:
        return self._entries

    def launch(self, entry: AppEntry) -> None:
        return None

    def instances(self, entry: AppEntry) -> int:
        return 1

    def close(self, entry: AppEntry) -> int:
        return 1

    # audio
    def get_volume(self) -> int:
        return 50

    def set_volume(self, percent: int) -> None:
        return None

    def set_muted(self, muted: bool) -> None:
        return None

    # media
    def toggle(self) -> bool:
        return True

    def next(self) -> bool:
        return True

    def previous(self) -> bool:
        return True

    def now_playing(self) -> NowPlayingInfo | None:
        return NowPlayingInfo("Exemplo", "Exemplo")

    # power: never acts
    def lock(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def restart(self) -> None:
        return None

    def sleep(self) -> None:
        return None

    def sign_out(self) -> None:
        return None

    # screen
    def capture(self, file_name: str) -> str:
        return file_name

    def open_snip(self) -> None:
        return None

    # brightness
    def get(self) -> int | None:
        return 50

    def set(self, percent: int) -> bool:
        return True

    # opener
    def open(self, uri: str) -> None:
        return None

    # status
    def memory(self) -> tuple[int, int]:
        return (1, 2)

    def cpu_percent(self) -> float:
        return 0.0

    def disks(self) -> list[tuple[str, int, int]]:
        return []


class DryRunDesk:
    """Windows and files that do nothing; one window, one monitor, no files."""

    def windows(self, entry: AppEntry | None) -> list[WindowRef]:
        return [WindowRef(1, "Janela", "normal", Rect(0, 0, 800, 600), 1)]

    def monitors(self) -> list[Monitor]:
        return [Monitor(1, Rect(0, 0, 1920, 1040), True)]

    def minimize(self, hwnd: int) -> None:
        return None

    def maximize(self, hwnd: int) -> None:
        return None

    def restore(self, hwnd: int) -> None:
        return None

    def focus(self, hwnd: int) -> bool:
        return True

    def place(self, hwnd: int, rect: Rect) -> None:
        return None

    def show_desktop(self) -> None:
        return None

    def undo_show_desktop(self) -> None:
        return None

    def names(self) -> Sequence[str]:
        return list(KNOWN_FOLDERS)

    def resolve(self, name: str) -> str | None:
        return f"C:/{name}"

    def search(self, words: Sequence[str], extensions: Sequence[str], limit: int) -> list[FileHit]:
        return []

    def newest(self, folder: str, since: datetime | None, limit: int) -> list[FileHit]:
        return []

    def folders(self, words: Sequence[str], limit: int) -> list[FileHit]:
        return []

    def open(self, path: str) -> None:
        return None

    def reveal(self, path: str) -> None:
        return None

    def exists(self, path: str) -> bool:
        return False


class DryRunChanger:
    """File changes that never happen: nothing exists."""

    def state(self, path: str) -> ItemState | None:
        return None

    def names_in(self, folder: str) -> set[str]:
        return set()

    def move(self, src: str, dst: str) -> None:
        return None

    def copy(self, src: str, dst: str) -> None:
        return None

    def rename(self, src: str, dst: str) -> None:
        return None

    def make_folder(self, path: str) -> None:
        return None

    def can_recycle(self, path: str) -> bool:
        return True

    def recycle(self, path: str) -> str:
        return ""

    def restore(self, ref: str) -> bool:
        return False


def dry_run_skills(app_names: Sequence[str]) -> SkillSet:
    p = DryRunPorts(app_names)
    desk = DryRunDesk()
    ports = PcPorts(
        catalog=p,
        launcher=p,
        audio=p,
        media=p,
        power=p,
        screen=p,
        brightness=p,
        opener=p,
        status=p,
        windows=desk,
        folders=desk,
        files=desk,
        file_opener=desk,
        changer=DryRunChanger(),
        file_area=Area((), (), (), str),
    )
    return build_skills(ports, Config())


def _is_false_execute(result: CaseResult) -> bool:
    decision, case = result.decision, result.case
    if not isinstance(decision, Execute):
        return False
    if isinstance(decision.slots.get("app"), Unmatched):
        # The skill can only answer "não encontrei": nothing happens on the machine.
        return False
    if case.intent == NO_INTENT or decision.intent_id != case.intent:
        return True
    expected_slots = (
        ("app", case.app),
        ("percent", case.percent),
        ("alvo", case.alvo),
        ("consulta", case.consulta),
        ("pagina", case.pagina),
        ("site", case.site),
        ("lado", case.lado),
        ("pasta", case.pasta),
        ("arquivo", case.arquivo),
    )
    for name, expected in expected_slots:
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
        NluCase(
            c["text"],
            c["intent"],
            c.get("app"),
            c.get("percent"),
            c.get("alvo"),
            c.get("consulta"),
            c.get("pagina"),
            c.get("site"),
            c.get("lado"),
            c.get("pasta"),
            c.get("arquivo"),
        )
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
    skill_set = dry_run_skills(app_names)
    extractors = skill_set.extractors()
    settings = Settings("Artur", thresholds, LearningThresholds(1.0, 1.0), 60.0)
    # A self-confirming intent's Execute is only a proposal: it still asks before acting.
    proposing = {s.id for skill in skill_set.skills for s in skill.intents if s.confirms_itself}
    results: list[CaseResult] = []
    for case in cases:
        assistant = Assistant(
            skills=skill_set.skills,
            index=index,
            extractors=extractors,
            store=SqliteCoppermind(":memory:"),
            aliases={"app": skill_set.app_aliases},
            settings=settings,
            clock=lambda: _FIXED_TIME,
            rng=Random(0),
        )
        ranking = index.rank(normalize(case.text))
        response = assistant.handle(case.text)
        decision = response.decision
        if isinstance(decision, Execute) and decision.intent_id in proposing:
            decision = Confirm(decision.intent_id, decision.slots, ConfirmReason.DESTRUCTIVE)
        results.append(CaseResult(case, ranking[0].intent_id if ranking else None, decision))

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
