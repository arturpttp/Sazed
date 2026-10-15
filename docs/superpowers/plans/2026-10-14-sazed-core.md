# Sazed Sub-project 1 — Core + text CLI + PC slice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A terminal assistant that understands pt-BR commands to open/close installed apps and control the system volume, answers in Sazed's voice, and learns persistently from explicit user signals.

**Architecture:** A pure, stdlib-only `core` (types, decision policy, dialogue context, learning rules, persona) is driven by a `runtime.Assistant` that normalises text, ranks intents through an `IntentIndex` (embedding similarity over examples), extracts slots, decides, executes a skill through ports, renders the persona response and records an episode in the SQLite "coppermind". Windows, ONNX and SQLite live in `adapters` behind ports; the CLI talks only to `runtime`.

**Tech Stack:** Python 3.12 (uv), numpy, onnxruntime + tokenizers (multilingual-e5-small), rapidfuzz, pydantic v2, psutil, pywin32, pycaw, stdlib sqlite3/tomllib; pytest, ruff, mypy --strict.

**Spec:** [`docs/superpowers/specs/2026-10-14-sazed-core-design.md`](../specs/2026-10-14-sazed-core-design.md)

## Global Constraints

- Python **3.12** exactly (`requires-python = ">=3.12,<3.13"`, `.python-version` = `3.12`); the machine default is 3.14.
- **No external AI APIs, ever.** The only network access in the whole sub-project is `scripts/fetch_model.py`, run once by hand.
- Dependency direction: `interfaces → runtime → skills → core`, `runtime → nlu → core`; `adapters` import `core`/`nlu`/`skills` to implement ports. Enforced by `tests/test_architecture.py`.
- `sazed.core` imports the stdlib only, does no I/O, and never reads the clock, environment or RNG seed. The runtime is the only place that reads the clock (`clock()` injected into `Assistant`).
- All user-facing text is **pt-BR**, masculine persona, addresses the user as `Mestre {user.name}` (default name `Artur`). Code, comments, commits, docs: English.
- No stack trace, exception text or library message ever reaches a `Response` or the terminal. Logs go to a rotating file only.
- Any learning step writing more than one row runs in one SQLite transaction.
- TDD: no implementation line without a failing test first. Conventional Commits, one logical unit per commit, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Default test run excludes `model` and `windows` markers; those run explicitly.
- Discrimination proofs (spec §10) are appended to `docs/superpowers/proofs/2026-10-14-sub-project-1.md` with the failing output pasted.

## Deviations from the spec (flagged for the user)

1. **Embedder size.** `intfloat/multilingual-e5-small` fp32 ONNX is **470 MB** (checked on Hugging Face, 2026-10-14), not ~120 MB. The int8 build `onnx/model_qint8_avx512_vnni.onnx` is **118 MB** and the Ryzen 8600G (Zen 4) supports AVX-512 VNNI. The plan uses int8 by default; Task 17 compares it with fp32 on the NLU fixture and keeps fp32 only if int8 misses the thresholds.
2. **App catalog covers `.lnk` shortcuts only** (as specified). Microsoft Store apps (WhatsApp, the new Notepad, Calculator) have no `.lnk` and will not be found. Recorded as a known gap for sub-project 2.
3. **Closing is graceful:** `WM_CLOSE` to the app's top-level windows, never `TerminateProcess`, so unsaved work triggers the app's own prompt.
4. **"Several running instances"** (spec §4.2) means several *root* processes (a matching process whose parent is not also a match), so Chrome's helper processes don't count as instances.
5. An `app` match counts as **exact** when it scores 100 (all words of the query are in exactly one app name) or comes from an alias. "chrome" → "Google Chrome" is therefore exact, and "crome" is not.
6. The spec's `Decision` set has no "rejected" case. A required slot the user gave that matches nothing (`Unmatched`) counts as *given*, the skill runs and returns `AppNotFound`. This keeps the four decisions intact.

## Review Focus

1. **Open vs close embed close together** ("abre o chrome" / "fecha o chrome" differ by one word). Expect a gap-based `Confirm`, never a wrong `Execute`. Pinned by the opposite-verb cases in the NLU fixture (Task 17) and the `SMALL_GAP` policy test (Task 2).
2. **A bare "sim"/"não" with nothing pending, or after the TTL**, should get "não compreendi", and must never execute a stale action. Pinned in Task 11 (`test_yes_after_ttl_is_not_understood`, `test_yes_with_nothing_pending_is_not_understood`).
3. **Out-of-range or absent numbers** ("volume em 150", "aumenta o volume"). Expect 150 → ask "Em quanto?", and no number → a default step of 10, clamped to 0–100. Pinned in Task 7 (`test_out_of_range_number_is_ignored`) and Task 8 (`test_increase_clamps_at_100`).
4. **Starting a new command while a question is pending** ("Devo abrir o Chrome?" → "aumenta o volume"). Expect the pending question to be dropped and the new command handled. Pinned in Task 11 (`test_unrelated_reply_drops_pending_and_is_understood`).
5. **An adapter raising mid-command** (a COM error, a missing exe) should produce a polite pt-BR failure with no exception text, the next command should still work, and the cause should be in the log file only. Pinned in Task 10 (`test_skill_exception_is_rendered_politely_and_logged`) and Task 16 (`test_logging_never_writes_to_the_console`).

---

## File structure

```
pyproject.toml, .python-version, .gitignore, config.example.toml
scripts/fetch_model.py              # one-time model download (only network code)
scripts/measure_embedder.py         # RAM / latency measurement
scripts/tune_thresholds.py          # threshold sweep over the NLU fixture
src/sazed/__init__.py               # __version__
src/sazed/core/                     # pure, stdlib only
  types.py        Utterance, IntentScore, Ranking, SlotValue, Ambiguous, Unmatched, Extraction, Slots, ParseResult
  decisions.py    Execute, Confirm(+ConfirmReason), AskSlot, NotUnderstood, Decision
  outcomes.py     success outcomes, Failure types, Outcome, is_failure, FAILURE_NAMES
  policy.py       Thresholds, IntentRequirements, decide()
  context.py      DialogueContext, pending questions, LastTurn
  learning.py     LearningThresholds, Verdict, judge_example()
  coppermind.py   store port (Coppermind protocol) + its value types
  skill.py        SlotSpec, IntentSpec, SkillContext, Skill protocol
  response.py     Response
  persona/definition.py  TRAITS, TEMPLATES, EXTRA_FIELDS, Prompt, keys_for_type()
  persona/render.py      render()
  CLAUDE.md
src/sazed/nlu/
  normalize.py    normalize(), strip_accents()
  embedder.py     Embedder protocol
  matcher.py      IntentIndex protocol, IntentMatcher
  control.py      parse_control(), pick_candidate()
  slots/app.py, slots/percent.py, slots/mute.py
  CLAUDE.md
src/sazed/skills/
  pc/apps.py      AppEntry, AppCatalog, AppLauncher ports, AppsSkill
  pc/volume.py    AudioControl port, VolumeSkill
  CLAUDE.md
src/sazed/adapters/
  sqlite/coppermind.py   SqliteCoppermind
  onnx/embedder.py       OnnxEmbedder
  windows/catalog.py     StartMenuCatalog, build_entries()
  windows/launcher.py    WindowsLauncher
  windows/audio.py       PycawAudio
src/sazed/runtime/
  assistant.py    Assistant, Settings
  extractors.py   build_extractors()
  config.py       Config, load_config(), ConfigError
  wiring.py       SazedApp, build_app(), build_default_app()
  admin.py        rows for `aprendizado` / `revisar`
  logs.py         setup_logging()
src/sazed/interfaces/cli/main.py    REPL + subcommands
tests/fakes/      embedder.py, index.py, ports.py, clock.py     (each has its own test)
tests/support/    samples.py                                     (has its own test)
tests/fixtures/nlu_cases.toml
tests/<mirror of src>/test_*.py
```

---

### Task 1: Project scaffold and architecture guard

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `src/sazed/__init__.py`, `src/sazed/{core,nlu,skills,adapters,runtime,interfaces}/__init__.py`, `src/sazed/interfaces/cli/__init__.py`
- Create: `tests/test_package.py`, `tests/test_architecture.py`, `docs/superpowers/proofs/2026-10-14-sub-project-1.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Produces: package `sazed` with `__version__ = "0.1.0"`; pytest config with `pythonpath = ["tests"]` so tests import helpers as `from fakes.x import ...` / `from support.x import ...`; markers `model`, `windows`.

- [ ] **Step 1: Pin Python and create the project files**

`.python-version`:
```
3.12
```

`pyproject.toml`:
```toml
[project]
name = "sazed"
version = "0.1.0"
description = "Local, offline personal assistant with the persona of Sazed."
requires-python = ">=3.12,<3.13"
dependencies = [
    "numpy>=2.1",
    "onnxruntime>=1.20",
    "tokenizers>=0.20",
    "rapidfuzz>=3.10",
    "pydantic>=2.9",
    "psutil>=6.1",
    "pywin32>=308; sys_platform == 'win32'",
    "pycaw>=20240316; sys_platform == 'win32'",
    "comtypes>=1.4; sys_platform == 'win32'",
]

[project.scripts]
sazed = "sazed.interfaces.cli.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sazed"]

[dependency-groups]
dev = ["pytest>=8.3", "ruff>=0.8", "mypy>=1.13", "types-psutil", "types-pywin32"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["tests"]
addopts = "--import-mode=importlib -m 'not model and not windows'"
markers = [
    "model: needs the downloaded embedder model (run: uv run pytest -m model)",
    "windows: touches the real desktop - apps, volume (run: uv run pytest -m windows)",
]

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "TID"]

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src/sazed/core", "src/sazed/nlu"]
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
models/
*.db
*.log
```

`src/sazed/__init__.py`:
```python
"""Sazed: a local, offline personal assistant."""

__version__ = "0.1.0"
```

Create empty `__init__.py` files (one line docstring each) in `core`, `nlu`, `skills`, `adapters`, `runtime`, `interfaces`, `interfaces/cli`. Example `src/sazed/core/__init__.py`:
```python
"""Pure domain core: types, policy, context, learning rules, persona. Stdlib only."""
```

- [ ] **Step 2: Sync the environment and confirm the interpreter**

Run: `uv sync`
Then: `uv run python -c "import sys, numpy, onnxruntime, tokenizers, rapidfuzz, pydantic, psutil; print(sys.version)"`
Expected: prints `3.12.x`. If any wheel fails to install on 3.12, stop and report it (spec §12 open question). Do not switch versions silently.

- [ ] **Step 3: Write the failing tests**

`tests/test_package.py`:
```python
from importlib.metadata import version

import sazed


def test_version_matches_installed_metadata() -> None:
    assert sazed.__version__ == version("sazed")
```

`tests/test_architecture.py`:
```python
"""Dependency direction and core purity, checked by parsing the source."""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "sazed"

ALLOWED: dict[str, set[str]] = {
    "core": {"sazed.core"},
    "nlu": {"sazed.core", "sazed.nlu"},
    "skills": {"sazed.core", "sazed.skills"},
    "adapters": {"sazed.core", "sazed.nlu", "sazed.skills", "sazed.adapters"},
    "runtime": {"sazed.core", "sazed.nlu", "sazed.skills", "sazed.adapters", "sazed.runtime"},
    "interfaces": {"sazed.runtime", "sazed.interfaces"},
}
STDLIB_ONLY = {"core"}
PURE = {"core", "nlu"}
IMPURE_ATTRIBUTES = {"now", "today", "utcnow", "getenv", "environ"}
IMPURE_NAMES = {"open", "input", "print"}


def _imports(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append("." * node.level + (node.module or ""))
    return found


def _is_allowed(module: str, allowed: set[str]) -> bool:
    return any(module == a or module.startswith(a + ".") for a in allowed)


@pytest.mark.parametrize("package", sorted(ALLOWED))
def test_package_imports_only_what_it_may(package: str) -> None:
    violations: list[str] = []
    for file in sorted((SRC / package).rglob("*.py")):
        for module in _imports(ast.parse(file.read_text(encoding="utf-8"))):
            top = module.split(".")[0]
            if module.startswith("."):
                violations.append(f"{file.name}: relative import {module}")
            elif top == "sazed":
                if not _is_allowed(module, ALLOWED[package]):
                    violations.append(f"{file.name}: {module}")
            elif package in STDLIB_ONLY and top not in sys.stdlib_module_names:
                violations.append(f"{file.name}: third-party {module}")
    assert violations == []


@pytest.mark.parametrize("package", sorted(PURE))
def test_pure_packages_do_not_touch_clock_env_or_io(package: str) -> None:
    violations: list[str] = []
    for file in sorted((SRC / package).rglob("*.py")):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in IMPURE_ATTRIBUTES:
                violations.append(f"{file.name}:{node.lineno} .{node.attr}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in IMPURE_NAMES
            ):
                violations.append(f"{file.name}:{node.lineno} {node.func.id}()")
    assert violations == []


def test_every_package_has_a_rule() -> None:
    packages = {p.name for p in SRC.iterdir() if (p / "__init__.py").exists()}
    assert packages == set(ALLOWED)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -v`
Expected: the package test passes once installed. The architecture tests pass vacuously, because the packages are empty. That is why Step 5 exists.

- [ ] **Step 5: Prove the architecture guard discriminates**

Temporarily add `import sazed.runtime` to `src/sazed/core/__init__.py`, then run `uv run pytest tests/test_architecture.py -v`. Expected: `test_package_imports_only_what_it_may[core]` FAILS, listing `__init__.py: sazed.runtime`. Replace it with `from datetime import datetime; datetime.now()` and expect `test_pure_packages_do_not_touch_clock_env_or_io[core]` to FAIL. Revert both. Create `docs/superpowers/proofs/2026-10-14-sub-project-1.md`:

````markdown
# Discrimination proofs — sub-project 1

Each entry: the property, the mutation (a bug a person would write), the failing output, reverted.

## Architecture guard
Mutation: `import sazed.runtime` in `sazed/core/__init__.py`.
```
<paste the failing pytest output>
```
Mutation: `datetime.now()` in `sazed/core/__init__.py`.
```
<paste the failing pytest output>
```
````

- [ ] **Step 6: Lint, type-check, and document the commands**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: all clean (run `uv run ruff format .` first if needed).

Replace the last line of the root `CLAUDE.md` ("Commands, layout and toolchain notes are added here as the project is scaffolded.") with:
```markdown
## Commands

- `uv sync` — install (Python 3.12 is pinned in `.python-version`; the machine default is 3.14).
- `uv run pytest` — fast suite (excludes `model` and `windows` markers).
- `uv run pytest -m model` — tests that need the downloaded embedder (`uv run python scripts/fetch_model.py` first).
- `uv run pytest -m windows` — tests that open real apps and change the real volume.
- `uv run ruff check . && uv run ruff format --check . && uv run mypy` — lint, format, strict types (`core`, `nlu`).
- `uv run sazed` — the REPL.

## Layout

`src/sazed/{core,nlu,skills,adapters,runtime,interfaces}`. The dependency direction is enforced by
`tests/test_architecture.py`. Test doubles live in `tests/fakes/`, and each has its own test.
```
Also change the **Status** section's "Next step" line to: `**Next step:** execute docs/superpowers/plans/2026-10-14-sazed-core.md.`

- [ ] **Step 7: Commit**

```bash
git add .python-version pyproject.toml uv.lock .gitignore src tests docs/superpowers/proofs CLAUDE.md
git commit -m "chore: scaffold uv project with architecture guard" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Core types, decisions, outcomes and the decision policy

**Files:**
- Create: `src/sazed/core/types.py`, `src/sazed/core/decisions.py`, `src/sazed/core/outcomes.py`, `src/sazed/core/policy.py`, `src/sazed/core/response.py`
- Test: `tests/core/test_policy.py`, `tests/core/test_outcomes.py`

**Interfaces:**
- Produces (used by every later task):
  - `Utterance(text: str, normalized: str, received_at: datetime)`
  - `IntentScore(intent_id: str, score: float)`; `Ranking = tuple[IntentScore, ...]` (best first)
  - `SlotValue(name: str, value: str | int | bool, raw: str, confidence: float, exact: bool = True)`
  - `Ambiguous(name: str, raw: str, candidates: tuple[str, ...])`, `Unmatched(name: str, raw: str, suggestion: str | None)`
  - `Extraction = SlotValue | Ambiguous | Unmatched`; `Slots = Mapping[str, SlotValue | Unmatched]`
  - `ParseResult(utterance, ranking, slots: Mapping[str, Extraction], missing_slots: frozenset[str])`
  - `ConfirmReason.{LOW_SCORE, SMALL_GAP, DESTRUCTIVE}`; `Execute(intent_id, slots)`, `Confirm(intent_id, slots, reason)`, `AskSlot(intent_id, slots, slot, candidates, raw)`, `NotUnderstood()`; `Decision`
  - Outcomes: `AppOpened(app)`, `AppClosed(app)`, `VolumeSet(percent)`, `VolumeChanged(percent)`, `Muted()`, `Unmuted()`, `ExampleLearned(text)`, `AliasLearned(alias, value)`, `AlreadyKnown()`, `Forgotten(description)`, `NothingToForget()`, `Cancelled()`; failures `AppNotFound(query, suggestion)`, `AppNotRunning(app)`, `AmbiguousSlot(slot, candidates)`, `ActionFailed(action)`; `Outcome`, `Failure`, `is_failure(o) -> bool`, `FAILURE_NAMES: frozenset[str]`
  - `Thresholds(t_exec, t_confirm, g_min)`, `IntentRequirements(required: frozenset[str], requires_confirmation: bool)`, `decide(parse, requirements, thresholds) -> Decision`
  - `Response(text: str, outcome: Outcome | None, decision: Decision | None)`

- [ ] **Step 1: Write the failing policy tests**

`tests/core/test_policy.py`:
```python
from datetime import datetime

from sazed.core.decisions import AskSlot, Confirm, ConfirmReason, Execute, NotUnderstood
from sazed.core.policy import IntentRequirements, Thresholds, decide
from sazed.core.types import (
    Ambiguous,
    Extraction,
    IntentScore,
    ParseResult,
    SlotValue,
    Unmatched,
    Utterance,
)

TH = Thresholds(t_exec=0.90, t_confirm=0.70, g_min=0.05)
NOW = datetime(2026, 10, 14, 12, 0)
APP = SlotValue("app", "Google Chrome", "chrome", 1.0, exact=True)
NEEDS_APP = IntentRequirements(required=frozenset({"app"}), requires_confirmation=False)
NO_SLOTS = IntentRequirements(required=frozenset(), requires_confirmation=False)


def parse(*scores: tuple[str, float], slots: dict[str, Extraction] | None = None) -> ParseResult:
    utterance = Utterance("abre o chrome", "abre o chrome", NOW)
    ranking = tuple(IntentScore(i, s) for i, s in scores)
    return ParseResult(utterance, ranking, slots or {}, frozenset())


def test_high_score_wide_gap_and_resolved_slots_execute() -> None:
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.80), slots={"app": APP}), NEEDS_APP, TH)
    assert d == Execute("abrir_app", {"app": APP})


def test_score_exactly_at_t_exec_executes() -> None:
    d = decide(parse(("volume_mudo", 0.90), ("abrir_app", 0.50)), NO_SLOTS, TH)
    assert d == Execute("volume_mudo", {})


def test_score_in_confirm_band_confirms_with_low_score_reason() -> None:
    d = decide(parse(("volume_mudo", 0.85), ("abrir_app", 0.50)), NO_SLOTS, TH)
    assert d == Confirm("volume_mudo", {}, ConfirmReason.LOW_SCORE)


def test_score_exactly_at_t_confirm_still_confirms() -> None:
    d = decide(parse(("volume_mudo", 0.70), ("abrir_app", 0.10)), NO_SLOTS, TH)
    assert d == Confirm("volume_mudo", {}, ConfirmReason.LOW_SCORE)


def test_score_below_t_confirm_is_not_understood() -> None:
    d = decide(parse(("volume_mudo", 0.69), ("abrir_app", 0.10)), NO_SLOTS, TH)
    assert d == NotUnderstood()


def test_small_gap_confirms_even_above_t_exec() -> None:
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.93), slots={"app": APP}), NEEDS_APP, TH)
    assert d == Confirm("abrir_app", {"app": APP}, ConfirmReason.SMALL_GAP)


def test_gap_just_above_g_min_executes() -> None:
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.89), slots={"app": APP}), NEEDS_APP, TH)
    assert d == Execute("abrir_app", {"app": APP})


def test_destructive_intent_confirms_even_at_top_score() -> None:
    req = IntentRequirements(required=frozenset({"app"}), requires_confirmation=True)
    d = decide(parse(("fechar_app", 0.99), ("abrir_app", 0.50), slots={"app": APP}), req, TH)
    assert d == Confirm("fechar_app", {"app": APP}, ConfirmReason.DESTRUCTIVE)


def test_missing_required_slot_asks_for_it() -> None:
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.50)), NEEDS_APP, TH)
    assert d == AskSlot("abrir_app", {}, "app", (), "")


def test_ambiguous_slot_asks_with_candidates() -> None:
    amb = Ambiguous("app", "code", ("Claude Code", "Visual Studio Code"))
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.5), slots={"app": amb}), NEEDS_APP, TH)
    assert d == AskSlot("abrir_app", {}, "app", ("Claude Code", "Visual Studio Code"), "code")


def test_unmatched_slot_counts_as_given_so_the_skill_can_report_it() -> None:
    gone = Unmatched("app", "discordia", None)
    d = decide(parse(("abrir_app", 0.95), ("fechar_app", 0.5), slots={"app": gone}), NEEDS_APP, TH)
    assert d == Execute("abrir_app", {"app": gone})


def test_empty_ranking_is_not_understood() -> None:
    assert decide(parse(), NO_SLOTS, TH) == NotUnderstood()


def test_single_intent_gap_is_measured_against_zero() -> None:
    assert decide(parse(("volume_mudo", 0.95)), NO_SLOTS, TH) == Execute("volume_mudo", {})
```

`tests/core/test_outcomes.py`:
```python
from typing import get_args

from sazed.core.outcomes import (
    FAILURE_NAMES,
    ActionFailed,
    AppNotFound,
    AppOpened,
    Failure,
    Outcome,
    is_failure,
)


def test_every_failure_is_an_outcome() -> None:
    assert set(get_args(Failure)) <= set(get_args(Outcome))


def test_failure_names_are_derived_from_the_failure_union() -> None:
    assert {t.__name__ for t in get_args(Failure)} == FAILURE_NAMES


def test_is_failure_separates_failures_from_successes() -> None:
    assert is_failure(AppNotFound("x", None))
    assert is_failure(ActionFailed("abrir x"))
    assert not is_failure(AppOpened("Google Chrome"))
    assert not is_failure(None)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/core -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sazed.core.decisions'` (and similar).

- [ ] **Step 3: Implement the types**

`src/sazed/core/types.py`:
```python
"""Value types shared by every layer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Utterance:
    text: str
    normalized: str
    received_at: datetime


@dataclass(frozen=True)
class IntentScore:
    intent_id: str
    score: float


Ranking = tuple[IntentScore, ...]
"""Intent scores, best first."""


@dataclass(frozen=True)
class SlotValue:
    name: str
    value: str | int | bool
    raw: str
    confidence: float
    exact: bool = True


@dataclass(frozen=True)
class Ambiguous:
    """Several candidates fit equally well; the user must choose."""

    name: str
    raw: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class Unmatched:
    """The user named something, but nothing known matches it."""

    name: str
    raw: str
    suggestion: str | None


Extraction = SlotValue | Ambiguous | Unmatched
Slots = Mapping[str, SlotValue | Unmatched]
"""Slots handed to a skill. Ambiguous values never reach a skill."""


@dataclass(frozen=True)
class ParseResult:
    utterance: Utterance
    ranking: Ranking
    slots: Mapping[str, Extraction]
    missing_slots: frozenset[str]
```

`src/sazed/core/decisions.py`:
```python
"""The four ways a command can end."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sazed.core.types import Slots


class ConfirmReason(Enum):
    LOW_SCORE = "low_score"
    SMALL_GAP = "small_gap"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class Execute:
    intent_id: str
    slots: Slots


@dataclass(frozen=True)
class Confirm:
    intent_id: str
    slots: Slots
    reason: ConfirmReason


@dataclass(frozen=True)
class AskSlot:
    intent_id: str
    slots: Slots
    slot: str
    candidates: tuple[str, ...]
    raw: str


@dataclass(frozen=True)
class NotUnderstood:
    pass


Decision = Execute | Confirm | AskSlot | NotUnderstood
```

`src/sazed/core/outcomes.py`:
```python
"""What happened when a command ran. Failures are values, not exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import get_args


@dataclass(frozen=True)
class AppOpened:
    app: str


@dataclass(frozen=True)
class AppClosed:
    app: str


@dataclass(frozen=True)
class VolumeSet:
    percent: int


@dataclass(frozen=True)
class VolumeChanged:
    percent: int


@dataclass(frozen=True)
class Muted:
    pass


@dataclass(frozen=True)
class Unmuted:
    pass


@dataclass(frozen=True)
class ExampleLearned:
    text: str


@dataclass(frozen=True)
class AliasLearned:
    alias: str
    value: str


@dataclass(frozen=True)
class AlreadyKnown:
    pass


@dataclass(frozen=True)
class Forgotten:
    description: str


@dataclass(frozen=True)
class NothingToForget:
    pass


@dataclass(frozen=True)
class Cancelled:
    pass


@dataclass(frozen=True)
class AppNotFound:
    query: str
    suggestion: str | None


@dataclass(frozen=True)
class AppNotRunning:
    app: str


@dataclass(frozen=True)
class AmbiguousSlot:
    slot: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class ActionFailed:
    """An adapter failed. `action` is a pt-BR infinitive phrase, e.g. "abrir Google Chrome"."""

    action: str


Success = (
    AppOpened
    | AppClosed
    | VolumeSet
    | VolumeChanged
    | Muted
    | Unmuted
    | ExampleLearned
    | AliasLearned
    | AlreadyKnown
    | Forgotten
    | NothingToForget
    | Cancelled
)
Failure = AppNotFound | AppNotRunning | AmbiguousSlot | ActionFailed
Outcome = Success | Failure

_FAILURE_TYPES: tuple[type, ...] = get_args(Failure)
FAILURE_NAMES: frozenset[str] = frozenset(t.__name__ for t in _FAILURE_TYPES)


def is_failure(outcome: object) -> bool:
    return isinstance(outcome, _FAILURE_TYPES)
```

`src/sazed/core/response.py`:
```python
from __future__ import annotations

from dataclasses import dataclass

from sazed.core.decisions import Decision
from sazed.core.outcomes import Outcome


@dataclass(frozen=True)
class Response:
    """What the user sees. `text` is always rendered by the persona."""

    text: str
    outcome: Outcome | None
    decision: Decision | None
```

- [ ] **Step 4: Implement the policy**

`src/sazed/core/policy.py`:
```python
"""Turn scores and slots into exactly one decision. Pure."""

from __future__ import annotations

from dataclasses import dataclass

from sazed.core.decisions import AskSlot, Confirm, ConfirmReason, Decision, Execute, NotUnderstood
from sazed.core.types import Ambiguous, ParseResult, Slots


@dataclass(frozen=True)
class Thresholds:
    t_exec: float
    t_confirm: float
    g_min: float


@dataclass(frozen=True)
class IntentRequirements:
    required: frozenset[str]
    requires_confirmation: bool


def decide(parse: ParseResult, req: IntentRequirements, th: Thresholds) -> Decision:
    if not parse.ranking:
        return NotUnderstood()
    top = parse.ranking[0]
    second = parse.ranking[1].score if len(parse.ranking) > 1 else 0.0
    if top.score < th.t_confirm:
        return NotUnderstood()

    given: Slots = {n: v for n, v in parse.slots.items() if not isinstance(v, Ambiguous)}
    for name in sorted(req.required):
        extraction = parse.slots.get(name)
        if extraction is None:
            return AskSlot(top.intent_id, given, name, (), "")
        if isinstance(extraction, Ambiguous):
            return AskSlot(top.intent_id, given, name, extraction.candidates, extraction.raw)

    if top.score < th.t_exec:
        return Confirm(top.intent_id, given, ConfirmReason.LOW_SCORE)
    if top.score - second < th.g_min:
        return Confirm(top.intent_id, given, ConfirmReason.SMALL_GAP)
    if req.requires_confirmation:
        return Confirm(top.intent_id, given, ConfirmReason.DESTRUCTIVE)
    return Execute(top.intent_id, given)
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/core -v && uv run mypy`
Expected: all PASS; mypy clean.

- [ ] **Step 6: Prove the confirm band discriminates**

Mutation (a realistic omission): delete the two lines
```python
    if top.score < th.t_exec:
        return Confirm(top.intent_id, given, ConfirmReason.LOW_SCORE)
```
Run: `uv run pytest tests/core/test_policy.py -v`
Expected: `test_score_in_confirm_band_confirms_with_low_score_reason` and `test_score_exactly_at_t_confirm_still_confirms` FAIL (they get `Execute`). Paste the output under `## Confirm band` in the proofs file. Revert, then re-run and expect all tests to pass.

- [ ] **Step 7: Commit**

```bash
git add src/sazed/core tests/core docs/superpowers/proofs
git commit -m "feat(core): add domain types and decision policy" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Dialogue context

**Files:**
- Create: `src/sazed/core/context.py`
- Test: `tests/core/test_context.py`

**Interfaces:**
- Consumes: `Slots` (Task 2).
- Produces:
  - `AliasCandidate(slot: str, alias: str, value: str)`
  - `AwaitConfirm(intent_id: str, slots: Slots, utterance: str, learn_example: bool, alias: AliasCandidate | None = None)`
  - `AwaitSlot(intent_id: str, slots: Slots, slot: str, candidates: tuple[str, ...], raw: str, utterance: str)`
  - `AwaitLearn(text: str, intent_id: str)`; `Pending = AwaitConfirm | AwaitSlot | AwaitLearn`
  - `LastKind.{EXECUTED, NOT_UNDERSTOOD, APP_NOT_FOUND}`; `LastTurn(kind, utterance: str, intent_id: str | None, slots: Slots, raw_query: str | None)`
  - `DialogueContext(pending=None, pending_at=None, last=None, last_at=None)` with `.expire(now, ttl_seconds)`, `.with_pending(p, now)`, `.without_pending()`, `.with_last(t, now)`; all return new instances.

- [ ] **Step 1: Write the failing tests**

`tests/core/test_context.py`:
```python
from datetime import datetime, timedelta

from sazed.core.context import (
    AwaitConfirm,
    AwaitLearn,
    DialogueContext,
    LastKind,
    LastTurn,
)

T0 = datetime(2026, 10, 14, 12, 0, 0)
TTL = 60.0
PENDING = AwaitConfirm("abrir_app", {}, "abre o crome", learn_example=True)
LAST = LastTurn(LastKind.EXECUTED, "aumenta o volume", "volume_aumentar", {}, None)


def test_pending_survives_before_ttl() -> None:
    ctx = DialogueContext().with_pending(PENDING, T0)
    assert ctx.expire(T0 + timedelta(seconds=59), TTL).pending == PENDING


def test_pending_survives_exactly_at_ttl() -> None:
    ctx = DialogueContext().with_pending(PENDING, T0)
    assert ctx.expire(T0 + timedelta(seconds=60), TTL).pending == PENDING


def test_pending_expires_after_ttl() -> None:
    ctx = DialogueContext().with_pending(PENDING, T0)
    assert ctx.expire(T0 + timedelta(seconds=61), TTL).pending is None


def test_last_turn_expires_independently_of_pending() -> None:
    ctx = DialogueContext().with_last(LAST, T0).with_pending(PENDING, T0 + timedelta(seconds=30))
    later = ctx.expire(T0 + timedelta(seconds=75), TTL)
    assert later.last is None
    assert later.pending == PENDING


def test_new_pending_replaces_the_old_one() -> None:
    other = AwaitLearn("abre o zap", "abrir_app")
    ctx = DialogueContext().with_pending(PENDING, T0).with_pending(other, T0)
    assert ctx.pending == other


def test_without_pending_keeps_last() -> None:
    ctx = DialogueContext().with_last(LAST, T0).with_pending(PENDING, T0).without_pending()
    assert ctx.pending is None
    assert ctx.last == LAST


def test_context_is_immutable() -> None:
    ctx = DialogueContext()
    ctx.with_pending(PENDING, T0)
    assert ctx.pending is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sazed.core.context'`.

- [ ] **Step 3: Implement**

`src/sazed/core/context.py`:
```python
"""Short-term dialogue memory. Pure: `now` is always passed in."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

from sazed.core.types import Slots


@dataclass(frozen=True)
class AliasCandidate:
    slot: str
    alias: str
    value: str


@dataclass(frozen=True)
class AwaitConfirm:
    intent_id: str
    slots: Slots
    utterance: str
    learn_example: bool
    alias: AliasCandidate | None = None


@dataclass(frozen=True)
class AwaitSlot:
    intent_id: str
    slots: Slots
    slot: str
    candidates: tuple[str, ...]
    raw: str
    utterance: str


@dataclass(frozen=True)
class AwaitLearn:
    """Sazed asked "may I remember that <text> means this?"."""

    text: str
    intent_id: str


Pending = AwaitConfirm | AwaitSlot | AwaitLearn


class LastKind(Enum):
    EXECUTED = "executed"
    NOT_UNDERSTOOD = "not_understood"
    APP_NOT_FOUND = "app_not_found"


@dataclass(frozen=True)
class LastTurn:
    kind: LastKind
    utterance: str
    intent_id: str | None
    slots: Slots
    raw_query: str | None


@dataclass(frozen=True)
class DialogueContext:
    pending: Pending | None = None
    pending_at: datetime | None = None
    last: LastTurn | None = None
    last_at: datetime | None = None

    def expire(self, now: datetime, ttl_seconds: float) -> DialogueContext:
        ttl = timedelta(seconds=ttl_seconds)
        ctx = self
        if ctx.pending_at is not None and now - ctx.pending_at > ttl:
            ctx = ctx.without_pending()
        if ctx.last_at is not None and now - ctx.last_at > ttl:
            ctx = replace(ctx, last=None, last_at=None)
        return ctx

    def with_pending(self, pending: Pending, now: datetime) -> DialogueContext:
        return replace(self, pending=pending, pending_at=now)

    def without_pending(self) -> DialogueContext:
        return replace(self, pending=None, pending_at=None)

    def with_last(self, last: LastTurn, now: datetime) -> DialogueContext:
        return replace(self, last=last, last_at=now)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/core/test_context.py -v && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sazed/core/context.py tests/core/test_context.py
git commit -m "feat(core): add dialogue context with TTL expiry" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Learning rules and the coppermind port

**Files:**
- Create: `src/sazed/core/learning.py`, `src/sazed/core/coppermind.py`
- Test: `tests/core/test_learning.py`

**Interfaces:**
- Produces:
  - `LearningThresholds(t_conflict: float, t_dup: float)`; `Verdict.{SAVE, DUPLICATE, CONFLICT}`
  - `judge_example(scores: Mapping[str, float], target: str, th: LearningThresholds, ignore: frozenset[str] = frozenset()) -> Verdict`, where `scores` is the candidate's per-intent max similarity
  - Store port (`core/coppermind.py`): `LearnedKind.{EXAMPLE, ALIAS}`; `LearnedItem(kind, id: int, text: str, target: str, slot: str | None, created_at: datetime)` (example: `text`=utterance, `target`=intent_id, `slot`=None; alias: `text`=alias, `target`=value, `slot`=slot name); `NewExample(text, intent_id, embedding: bytes, origin: str)`; `NewAlias(slot, alias, value)`; `StoredExample(id, text, intent_id, embedding: bytes)`; `StoredAlias(id, slot, alias, value)`; `Reaction.{NONE, CONFIRMED, DENIED, CORRECTED}`; `Episode(utterance: str, at: datetime, ranking: Ranking, slots: Mapping[str, str], decision: str, intent_id: str | None, outcome: str, reaction: Reaction = Reaction.NONE)`; `StoredEpisode(id: int, episode: Episode)`
  - `class Coppermind(Protocol)`: `learn(examples, aliases, now) -> list[LearnedItem]` (atomic, one batch), `examples() -> list[StoredExample]`, `aliases() -> list[StoredAlias]`, `learned() -> list[LearnedItem]` (newest first), `forget(kind, item_id) -> LearnedItem | None`, `forget_latest() -> list[LearnedItem]` (the whole most recent batch), `record_episode(ep) -> int`, `set_reaction(episode_id, reaction) -> None`, `episodes(limit) -> list[StoredEpisode]`, `episode(episode_id) -> StoredEpisode | None`, `recent_failures(limit) -> list[StoredEpisode]`

- [ ] **Step 1: Write the failing tests**

`tests/core/test_learning.py`:
```python
from sazed.core.learning import LearningThresholds, Verdict, judge_example

TH = LearningThresholds(t_conflict=0.85, t_dup=0.97)


def test_new_example_far_from_everything_is_saved() -> None:
    assert judge_example({"abrir_app": 0.80, "fechar_app": 0.60}, "abrir_app", TH) is Verdict.SAVE


def test_near_copy_of_same_intent_is_duplicate() -> None:
    assert judge_example({"abrir_app": 0.97}, "abrir_app", TH) is Verdict.DUPLICATE


def test_close_to_another_intent_is_conflict() -> None:
    assert judge_example({"abrir_app": 0.80, "fechar_app": 0.85}, "abrir_app", TH) is Verdict.CONFLICT


def test_just_below_conflict_threshold_saves() -> None:
    assert judge_example({"abrir_app": 0.80, "fechar_app": 0.849}, "abrir_app", TH) is Verdict.SAVE


def test_duplicate_wins_over_conflict() -> None:
    scores = {"abrir_app": 0.99, "fechar_app": 0.95}
    assert judge_example(scores, "abrir_app", TH) is Verdict.DUPLICATE


def test_ignored_intents_do_not_count_as_conflict() -> None:
    scores = {"abrir_app": 0.70, "fechar_app": 0.95}
    assert judge_example(scores, "abrir_app", TH, ignore=frozenset({"fechar_app"})) is Verdict.SAVE


def test_unknown_target_with_no_scores_is_saved() -> None:
    assert judge_example({}, "abrir_app", TH) is Verdict.SAVE
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_learning.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the rules**

`src/sazed/core/learning.py`:
```python
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
```

- [ ] **Step 4: Implement the store port** (types only, so there is no test of its own. Task 9 tests the adapter against it.)

`src/sazed/core/coppermind.py`:
```python
"""The coppermind: persistent learned examples, aliases and episodes. Port only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from sazed.core.types import Ranking


class LearnedKind(Enum):
    EXAMPLE = "example"
    ALIAS = "alias"


@dataclass(frozen=True)
class LearnedItem:
    kind: LearnedKind
    id: int
    text: str
    target: str
    slot: str | None
    created_at: datetime


@dataclass(frozen=True)
class NewExample:
    text: str
    intent_id: str
    embedding: bytes
    origin: str


@dataclass(frozen=True)
class NewAlias:
    slot: str
    alias: str
    value: str


@dataclass(frozen=True)
class StoredExample:
    id: int
    text: str
    intent_id: str
    embedding: bytes


@dataclass(frozen=True)
class StoredAlias:
    id: int
    slot: str
    alias: str
    value: str


class Reaction(Enum):
    NONE = "none"
    CONFIRMED = "confirmed"
    DENIED = "denied"
    CORRECTED = "corrected"


@dataclass(frozen=True)
class Episode:
    utterance: str
    at: datetime
    ranking: Ranking
    slots: Mapping[str, str]
    decision: str
    intent_id: str | None
    outcome: str
    reaction: Reaction = Reaction.NONE


@dataclass(frozen=True)
class StoredEpisode:
    id: int
    episode: Episode


class Coppermind(Protocol):
    def learn(
        self, examples: Sequence[NewExample], aliases: Sequence[NewAlias], now: datetime
    ) -> list[LearnedItem]: ...
    def examples(self) -> list[StoredExample]: ...
    def aliases(self) -> list[StoredAlias]: ...
    def learned(self) -> list[LearnedItem]: ...
    def forget(self, kind: LearnedKind, item_id: int) -> LearnedItem | None: ...
    def forget_latest(self) -> list[LearnedItem]: ...
    def record_episode(self, episode: Episode) -> int: ...
    def set_reaction(self, episode_id: int, reaction: Reaction) -> None: ...
    def episodes(self, limit: int) -> list[StoredEpisode]: ...
    def episode(self, episode_id: int) -> StoredEpisode | None: ...
    def recent_failures(self, limit: int) -> list[StoredEpisode]: ...
```

- [ ] **Step 5: Run tests, types**

Run: `uv run pytest tests/core -v && uv run mypy`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sazed/core/learning.py src/sazed/core/coppermind.py tests/core/test_learning.py
git commit -m "feat(core): add learning safeguards and coppermind port" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 5: Persona — Sazed's voice

**Files:**
- Create: `src/sazed/core/persona/__init__.py`, `src/sazed/core/persona/definition.py`, `src/sazed/core/persona/render.py`, `src/sazed/core/CLAUDE.md`
- Create: `tests/support/__init__.py` (empty), `tests/support/samples.py`
- Test: `tests/support/test_samples.py`, `tests/core/persona/test_persona.py`

**Interfaces:**
- Consumes: outcome and decision types (Task 2).
- Produces:
  - `Prompt.{OFFER_LEARN="offer_learn", CONFLICT_ASK="conflict_ask", GREETING="greeting", FAREWELL="farewell"}`
  - `render(item: Outcome | Decision | Prompt, *, nome: str, rng: random.Random, extra: Mapping[str, str] | None = None) -> str`
  - Required `extra` keys by template key (`EXTRA_FIELDS`): `Confirm`/`ConfirmDestructive` → `acao`; `AskSlot`/`AskSlotChoice` → `pergunta`; `offer_learn` → `original`; `conflict_ask` → `texto`, `acao`. A missing one raises `KeyError` (a programming error that the tests catch).
  - `template_key(item) -> str`, `keys_for_type(cls) -> tuple[str, ...]`, `format_fields(item) -> dict[str, str]`
  - Test helper `sample_instance(cls)` / `sample_value(tp)` in `tests/support/samples.py`.

- [ ] **Step 1: Write the failing test for the sample helper** (the persona test relies on it, so it is proven first)

`tests/support/test_samples.py`:
```python
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

import pytest
from support.samples import sample_instance, sample_value


class Color(Enum):
    RED = "red"
    BLUE = "blue"


@dataclass(frozen=True)
class Everything:
    text: str
    count: int
    ratio: float
    flag: bool
    maybe: str | None
    many: tuple[str, ...]
    mapping: Mapping[str, int]
    color: Color


@dataclass(frozen=True)
class Unsupported:
    items: set[int]


def test_sample_instance_fills_every_field_with_a_value_of_the_right_type() -> None:
    item = sample_instance(Everything)
    assert item == Everything(
        text="Exemplo",
        count=7,
        ratio=0.5,
        flag=True,
        maybe="Exemplo",
        many=("Exemplo", "Exemplo"),
        mapping={},
        color=Color.RED,
    )


def test_sample_value_refuses_unknown_types_instead_of_guessing() -> None:
    with pytest.raises(TypeError):
        sample_instance(Unsupported)


def test_sample_value_of_plain_str() -> None:
    assert sample_value(str) == "Exemplo"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/support -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'support.samples'`.

- [ ] **Step 3: Implement the helper**

`tests/support/samples.py`:
```python
"""Build a sample instance of any dataclass from its type hints, for schema-driven tests."""

import types
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints


def sample_value(tp: Any) -> Any:
    if tp is str:
        return "Exemplo"
    if tp is bool:
        return True
    if tp is int:
        return 7
    if tp is float:
        return 0.5
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        first = next(a for a in get_args(tp) if a is not type(None))
        return sample_value(first)
    if origin is tuple:
        item = sample_value(get_args(tp)[0])
        return (item, item)
    if origin is Mapping or tp is Mapping:
        return {}
    if isinstance(tp, type) and issubclass(tp, Enum):
        return next(iter(tp))
    if isinstance(tp, type) and is_dataclass(tp):
        return sample_instance(tp)
    raise TypeError(f"no sample value for {tp!r}")


def sample_instance(cls: type) -> Any:
    hints = get_type_hints(cls)
    return cls(**{f.name: sample_value(hints[f.name]) for f in fields(cls)})
```

Run: `uv run pytest tests/support -v`. Expected: PASS.

- [ ] **Step 4: Write the failing persona tests**

`tests/core/persona/test_persona.py`:
```python
from random import Random
from typing import get_args

import pytest
from support.samples import sample_instance

from sazed.core.decisions import AskSlot, Confirm, ConfirmReason, Decision
from sazed.core.outcomes import AppNotFound, AppOpened, Outcome
from sazed.core.persona import Prompt, render
from sazed.core.persona.definition import EXTRA_FIELDS, TEMPLATES, keys_for_type
from sazed.core.persona.render import format_fields, template_key

ALL_TYPES: tuple[type, ...] = get_args(Outcome) + get_args(Decision)
KEY_TO_TYPE = {key: cls for cls in ALL_TYPES for key in keys_for_type(cls)}
ALL_KEYS = sorted(KEY_TO_TYPE) + sorted(p.value for p in Prompt)


def _values_for(key: str) -> dict[str, str]:
    cls = KEY_TO_TYPE.get(key)
    base = format_fields(sample_instance(cls)) if cls is not None else {}
    extra = {name: "Exemplo" for name in EXTRA_FIELDS.get(key, ())}
    return {**base, **extra, "mestre": "Mestre Artur"}


def test_template_keys_are_exactly_the_reachable_ones() -> None:
    assert set(TEMPLATES) == set(ALL_KEYS)


@pytest.mark.parametrize("key", ALL_KEYS)
def test_every_variant_formats_with_the_fields_it_will_receive(key: str) -> None:
    assert TEMPLATES[key], f"{key} has no template"
    for template in TEMPLATES[key]:
        text = template.format(**_values_for(key))
        assert "{" not in text and "}" not in text


@pytest.mark.parametrize("key", ALL_KEYS)
def test_every_key_addresses_the_master_in_at_least_one_variant(key: str) -> None:
    assert any("{mestre}" in t for t in TEMPLATES[key])


@pytest.mark.parametrize("cls", ALL_TYPES)
def test_render_fills_the_configured_name(cls: type) -> None:
    item = sample_instance(cls)
    extra = {n: "Exemplo" for n in EXTRA_FIELDS.get(template_key(item), ())}
    texts = {render(item, nome="Artur", rng=Random(seed), extra=extra) for seed in range(40)}
    assert any("Mestre Artur" in t for t in texts)
    assert not any("{" in t for t in texts)


def test_rendering_is_deterministic_for_a_seed() -> None:
    a = render(AppOpened("Spotify"), nome="Artur", rng=Random(3))
    b = render(AppOpened("Spotify"), nome="Artur", rng=Random(3))
    assert a == b


def test_rng_reaches_every_variant() -> None:
    texts = {render(AppOpened("Spotify"), nome="Artur", rng=Random(s)) for s in range(60)}
    assert len(texts) == len(TEMPLATES["AppOpened"])


def test_app_not_found_with_suggestion_offers_it() -> None:
    text = render(AppNotFound("disc", "Discord"), nome="Artur", rng=Random(0))
    assert "Discord" in text and "disc" in text


def test_destructive_confirm_uses_its_own_template() -> None:
    item = Confirm("fechar_app", {}, ConfirmReason.DESTRUCTIVE)
    text = render(item, nome="Artur", rng=Random(0), extra={"acao": "fechar Spotify"})
    assert text in {t.format(acao="fechar Spotify", mestre="Mestre Artur")
                    for t in TEMPLATES["ConfirmDestructive"]}


def test_ask_slot_with_candidates_numbers_them() -> None:
    item = AskSlot("abrir_app", {}, "app", ("Claude Code", "Visual Studio Code"), "code")
    text = render(item, nome="Artur", rng=Random(0), extra={"pergunta": "Qual programa?"})
    assert "1) Claude Code, 2) Visual Studio Code" in text


def test_missing_extra_is_a_programming_error() -> None:
    with pytest.raises(KeyError):
        render(Confirm("abrir_app", {}, ConfirmReason.LOW_SCORE), nome="Artur", rng=Random(0))
```

- [ ] **Step 5: Run to verify failure**

Run: `uv run pytest tests/core/persona -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sazed.core.persona'`.

- [ ] **Step 6: Implement the definition**

`src/sazed/core/persona/definition.py`:
```python
"""Sazed's single persona definition: traits and pt-BR templates.

Sub-project 6 builds the SLM system prompt from TRAITS; keep them descriptive, not quoted
from the books.
"""

from __future__ import annotations

from enum import Enum

from sazed.core.decisions import AskSlot, Confirm
from sazed.core.outcomes import AppNotFound

TRAITS: tuple[str, ...] = (
    "Guardião terrisano: erudito gentil, cortês e muito educado.",
    "Guarda conhecimento em mentes de cobre; fala de aprender e lembrar com cuidado.",
    "Serve por escolha, não por servilidade; discorda com delicadeza quando importa.",
    "Humilde ao errar; eficaz sem alarde.",
    "Valoriza as pessoas e as crenças delas. Referências ao seu mundo são leves e raras.",
    "Respostas curtas para comandos; trata o usuário por 'Mestre' seguido do nome.",
)


class Prompt(Enum):
    OFFER_LEARN = "offer_learn"
    CONFLICT_ASK = "conflict_ask"
    GREETING = "greeting"
    FAREWELL = "farewell"


VARIANT_KEYS: dict[type, tuple[str, ...]] = {
    AppNotFound: ("AppNotFound", "AppNotFound.suggestion"),
    Confirm: ("Confirm", "ConfirmDestructive"),
    AskSlot: ("AskSlot", "AskSlotChoice"),
}


def keys_for_type(cls: type) -> tuple[str, ...]:
    return VARIANT_KEYS.get(cls, (cls.__name__,))


EXTRA_FIELDS: dict[str, tuple[str, ...]] = {
    "Confirm": ("acao",),
    "ConfirmDestructive": ("acao",),
    "AskSlot": ("pergunta",),
    "AskSlotChoice": ("pergunta",),
    "offer_learn": ("original",),
    "conflict_ask": ("texto", "acao"),
}

TEMPLATES: dict[str, tuple[str, ...]] = {
    # Outcomes: success
    "AppOpened": (
        "Pois não, {mestre}. Abrindo {app}.",
        "Como desejar. {app} está abrindo.",
        "Abrindo {app}, {mestre}.",
    ),
    "AppClosed": ("Pronto, {mestre}. {app} foi fechado.", "Fechei {app}, {mestre}."),
    "VolumeSet": ("Volume em {percent}%, {mestre}.", "Pronto. O volume está em {percent}%."),
    "VolumeChanged": ("Pronto, {mestre}. Volume em {percent}%.", "Volume agora em {percent}%."),
    "Muted": ("Som silenciado, {mestre}.", "Pronto. Silêncio, como pediu."),
    "Unmuted": ("O som está de volta, {mestre}.", "Pronto. Som reativado."),
    "ExampleLearned": (
        "Guardarei isso em minha mente de cobre, {mestre}: '{text}'.",
        "Anotado em minha mente de cobre, {mestre}.",
    ),
    "AliasLearned": (
        "Guardarei isso em minha mente de cobre: '{alias}' é {value}.",
        "Anotado, {mestre}. Quando disser '{alias}', entenderei {value}.",
    ),
    "AlreadyKnown": ("Isso eu já sabia, {mestre}.",),
    "Forgotten": (
        "Pronto, {mestre}. Esqueci {description}.",
        "Removido de minha mente de cobre, {mestre}: {description}.",
    ),
    "NothingToForget": ("Não há nada recente para esquecer, {mestre}.",),
    "Cancelled": ("Como desejar, {mestre}.", "Está bem, {mestre}. Não farei nada."),
    # Outcomes: failures
    "AppNotFound": ("Peço desculpas, {mestre}, mas não encontrei '{query}' entre os seus programas.",),
    "AppNotFound.suggestion": ("Não encontrei '{query}', {mestre}. Quis dizer {suggestion}?",),
    "AppNotRunning": ("{app} não parece estar aberto, {mestre}.",),
    "AmbiguousSlot": ("Encontrei mais de uma opção, {mestre}: {candidates}. Qual delas?",),
    "ActionFailed": (
        "Peço desculpas, {mestre}. Não consegui {action}.",
        "Algo deu errado ao tentar {action}, {mestre}. Peço desculpas.",
    ),
    # Decisions
    "Execute": ("Pois não, {mestre}.",),
    "Confirm": ("Devo {acao}, {mestre}?", "Entendi que deseja {acao}. Confirma, {mestre}?"),
    "ConfirmDestructive": ("Posso {acao}, mas prefiro confirmar antes, {mestre}. Deseja mesmo?",),
    "AskSlot": ("{pergunta}", "Perdão, {mestre}. {pergunta}"),
    "AskSlotChoice": ("{pergunta} Encontrei: {candidates}.", "{mestre}, encontrei {candidates}. {pergunta}"),
    "NotUnderstood": (
        "Peço desculpas, {mestre}, não compreendi.",
        "Perdão, {mestre}. Pode dizer de outra forma?",
    ),
    # Prompts
    "offer_learn": ("Posso guardar que '{original}' significa isso, {mestre}?",),
    "conflict_ask": (
        "'{texto}' se parece com outro pedido que conheço, {mestre}. "
        "Guardo mesmo assim que significa {acao}?",
    ),
    "greeting": ("Às suas ordens, {mestre}.", "Estou aqui, {mestre}."),
    "farewell": ("Até logo, {mestre}.",),
}
```

`src/sazed/core/persona/render.py`:
```python
"""Render outcomes, decisions and prompts in Sazed's voice. Pure: the RNG is passed in."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from random import Random

from sazed.core.decisions import AskSlot, Confirm, ConfirmReason, Decision
from sazed.core.outcomes import AppNotFound, Outcome
from sazed.core.persona.definition import EXTRA_FIELDS, TEMPLATES, Prompt

Renderable = Outcome | Decision | Prompt


def template_key(item: Renderable) -> str:
    if isinstance(item, Prompt):
        return item.value
    if isinstance(item, AppNotFound) and item.suggestion is not None:
        return "AppNotFound.suggestion"
    if isinstance(item, Confirm) and item.reason is ConfirmReason.DESTRUCTIVE:
        return "ConfirmDestructive"
    if isinstance(item, AskSlot) and item.candidates:
        return "AskSlotChoice"
    return type(item).__name__


def format_fields(item: object) -> dict[str, str]:
    """Template values from a dataclass: strings and ints as-is, tuples as a numbered list.

    Mappings (slots) and enums are internal and never formatted.
    """
    if isinstance(item, Prompt) or not hasattr(item, "__dataclass_fields__"):
        return {}
    values: dict[str, str] = {}
    for f in fields(item):  # type: ignore[arg-type]
        value = getattr(item, f.name)
        if isinstance(value, tuple):
            values[f.name] = ", ".join(f"{i}) {v}" for i, v in enumerate(value, start=1))
        elif isinstance(value, str | int) and not isinstance(value, bool):
            values[f.name] = str(value)
    return values


def render(
    item: Renderable, *, nome: str, rng: Random, extra: Mapping[str, str] | None = None
) -> str:
    key = template_key(item)
    values = {**format_fields(item), **(extra or {}), "mestre": f"Mestre {nome}"}
    missing = set(EXTRA_FIELDS.get(key, ())) - values.keys()
    if missing:
        raise KeyError(f"rendering {key} needs {sorted(missing)}")
    return rng.choice(TEMPLATES[key]).format(**values)
```

`src/sazed/core/persona/__init__.py`:
```python
"""Sazed's persona: one definition, pure rendering."""

from sazed.core.persona.definition import Prompt
from sazed.core.persona.render import render

__all__ = ["Prompt", "render"]
```

- [ ] **Step 7: Run tests, lint, types**

Run: `uv run pytest tests/core tests/support -v && uv run mypy && uv run ruff check .`
Expected: PASS. If `test_rng_reaches_every_variant` fails for a 3-variant key over 60 seeds, the bug is in `render` (not choosing with `rng`). Do not raise the seed count.

- [ ] **Step 8: Write `src/sazed/core/CLAUDE.md`**

```markdown
# sazed.core

Pure domain: value types, the decision policy, dialogue context, learning safeguards, the
coppermind *port*, the skill contract and the persona.

## Invariants (enforced by tests/test_architecture.py)
- Stdlib only. No numpy, no pydantic, no I/O, no `datetime.now()`, no env reads.
- Anything time-dependent takes `now` as a parameter; randomness takes an `rng`.

## Conventions
- Every value type is a `@dataclass(frozen=True)`. Context updates return new instances.
- Failures are *values* (`core.outcomes.Failure`), never raised. Exceptions are for
  programming errors only (a missing persona extra, an unknown intent id).
- A new `Outcome` or `Decision` type must be added to its union. The persona test then
  demands a template for it automatically. Do not hand-list types anywhere.
- Template placeholders are dataclass field names plus `{mestre}` and the documented
  `EXTRA_FIELDS`. Tuples render as "1) a, 2) b"; mappings and enums are never rendered.

## Traps
- `Slots` never contains `Ambiguous`: the policy turns ambiguity into `AskSlot`.
- `Unmatched` counts as a *given* slot, so the skill reports `AppNotFound` instead of asking again.
- Persona text is pt-BR and masculine ("Pronto", "Obrigado"). User-facing strings live
  here or in skill specs (`describe`, slot `question`), nowhere else.

## Not here
Embeddings and fuzzy matching (→ `nlu`), OS access (→ `adapters`), wiring and the clock (→ `runtime`).
```

- [ ] **Step 9: Commit**

```bash
git add src/sazed/core/persona src/sazed/core/CLAUDE.md tests/support tests/core/persona
git commit -m "feat(persona): add Sazed templates and pure renderer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: NLU normalisation, embedder port, intent index

**Files:**
- Create: `src/sazed/nlu/normalize.py`, `src/sazed/nlu/embedder.py`, `src/sazed/nlu/matcher.py`
- Create: `tests/fakes/__init__.py` (empty), `tests/fakes/embedder.py`, `tests/fakes/index.py`
- Test: `tests/nlu/test_normalize.py`, `tests/fakes/test_embedder.py`, `tests/fakes/test_index.py`, `tests/nlu/test_matcher.py`

**Interfaces:**
- Consumes: `IntentScore`, `Ranking` (Task 2).
- Produces:
  - `normalize(text: str) -> str` (lowercase, punctuation → space, collapsed whitespace, accents kept); `strip_accents(text: str) -> str`
  - `class Embedder(Protocol)`: `dim: int` (property), `embed(texts: Sequence[str]) -> NDArray[np.float32]` of shape `(n, dim)`, rows L2-normalised
  - `class IntentIndex(Protocol)`: `rank(text) -> Ranking`, `scores(text) -> dict[str, float]` (per-intent max cosine), `vectorize(text) -> bytes`, `add(intent_id, text, vector: bytes) -> None`, `remove(intent_id, text) -> bool`
  - `IntentMatcher(embedder)` implements `IntentIndex` plus `add_examples(intent_id, texts: Sequence[str]) -> None` (one batched embed call)
  - Fakes: `HashingEmbedder(dim=256)`, `ScriptedIndex(script: Mapping[str, Mapping[str, float]] | None)` with `.learned: list[tuple[str, str]]` (intent_id, text)

- [ ] **Step 1: Write the failing tests**

`tests/nlu/test_normalize.py`:
```python
from sazed.nlu.normalize import normalize, strip_accents


def test_lowercases_and_strips_punctuation() -> None:
    assert normalize("Abre o Chrome!!") == "abre o chrome"


def test_collapses_whitespace_and_drops_percent_sign() -> None:
    assert normalize("  volume   em 30% ") == "volume em 30"


def test_keeps_accents() -> None:
    assert normalize("Não, é o Discórdia.") == "não é o discórdia"


def test_strip_accents_removes_diacritics_only() -> None:
    assert strip_accents("não é ação") == "nao e acao"


def test_strip_accents_preserves_length_for_latin_text() -> None:
    text = "põe o volume no máximo"
    assert len(strip_accents(text)) == len(text)
```

`tests/fakes/test_embedder.py`:
```python
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
```

`tests/fakes/test_index.py`:
```python
import pytest
from fakes.index import ScriptedIndex

from sazed.core.types import IntentScore


def test_rank_orders_scripted_scores_best_first_with_id_tiebreak() -> None:
    idx = ScriptedIndex({"x": {"b": 0.5, "a": 0.5, "c": 0.9}})
    assert idx.rank("x") == (IntentScore("c", 0.9), IntentScore("a", 0.5), IntentScore("b", 0.5))


def test_unknown_text_ranks_empty() -> None:
    assert ScriptedIndex().rank("nada") == ()


def test_learned_text_scores_one_for_its_intent() -> None:
    idx = ScriptedIndex({"abre ai o chrome": {"abrir_app": 0.8, "fechar_app": 0.4}})
    idx.add("abrir_app", "abre ai o chrome", idx.vectorize("abre ai o chrome"))
    assert idx.scores("abre ai o chrome") == {"abrir_app": 1.0, "fechar_app": 0.4}


def test_add_rejects_a_vector_of_another_text() -> None:
    idx = ScriptedIndex()
    with pytest.raises(ValueError):
        idx.add("abrir_app", "abre", idx.vectorize("fecha"))


def test_remove_reports_whether_something_was_removed() -> None:
    idx = ScriptedIndex()
    idx.add("abrir_app", "abre", idx.vectorize("abre"))
    assert idx.remove("abrir_app", "abre") is True
    assert idx.remove("abrir_app", "abre") is False
    assert idx.scores("abre") == {}
```

`tests/nlu/test_matcher.py`:
```python
import numpy as np
import pytest
from fakes.embedder import HashingEmbedder

from sazed.nlu.matcher import IntentMatcher


@pytest.fixture
def matcher() -> IntentMatcher:
    m = IntentMatcher(HashingEmbedder())
    m.add_examples("abrir_app", ["abre o chrome", "abra o spotify"])
    m.add_examples("volume_aumentar", ["aumenta o volume", "sobe o som"])
    return m


def test_exact_example_scores_one_and_ranks_first(matcher: IntentMatcher) -> None:
    ranking = matcher.rank("abre o chrome")
    assert ranking[0].intent_id == "abrir_app"
    assert ranking[0].score == pytest.approx(1.0, abs=1e-5)


def test_intent_score_is_the_max_over_its_examples(matcher: IntentMatcher) -> None:
    embedder = HashingEmbedder()
    q, a, b = embedder.embed(["sobe o som agora", "aumenta o volume", "sobe o som"])
    expected = max(float(q @ a), float(q @ b))
    assert matcher.scores("sobe o som agora")["volume_aumentar"] == pytest.approx(expected, abs=1e-5)


def test_ranking_is_sorted_descending(matcher: IntentMatcher) -> None:
    scores = [s.score for s in matcher.rank("aumenta o volume do chrome")]
    assert scores == sorted(scores, reverse=True)


def test_empty_matcher_ranks_nothing() -> None:
    m = IntentMatcher(HashingEmbedder())
    assert m.rank("abre o chrome") == ()
    assert m.scores("abre o chrome") == {}


def test_vectorize_and_add_round_trip(matcher: IntentMatcher) -> None:
    text = "liga o navegador"
    matcher.add("abrir_app", text, matcher.vectorize(text))
    assert matcher.scores(text)["abrir_app"] == pytest.approx(1.0, abs=1e-5)


def test_add_rejects_a_vector_of_the_wrong_size(matcher: IntentMatcher) -> None:
    with pytest.raises(ValueError):
        matcher.add("abrir_app", "x", np.zeros(3, dtype=np.float32).tobytes())


def test_remove_drops_only_that_example(matcher: IntentMatcher) -> None:
    assert matcher.remove("abrir_app", "abre o chrome") is True
    assert matcher.rank("abre o chrome")[0].score < 0.999
    assert matcher.remove("abrir_app", "abre o chrome") is False
    assert "abrir_app" in matcher.scores("abra o spotify")


def test_add_examples_embeds_in_one_batch() -> None:
    calls: list[int] = []

    class Spy(HashingEmbedder):
        def embed(self, texts):  # type: ignore[no-untyped-def]
            calls.append(len(texts))
            return super().embed(texts)

    IntentMatcher(Spy()).add_examples("abrir_app", ["a", "b", "c"])
    assert calls == [3]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/nlu tests/fakes -v`
Expected: FAIL with `ModuleNotFoundError` for `sazed.nlu.normalize`, `fakes.embedder`, and the others.

- [ ] **Step 3: Implement normalisation and the embedder port**

`src/sazed/nlu/normalize.py`:
```python
"""Text normalisation. Accents are kept for the embedder and stripped only for matching."""

import re
import unicodedata

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str) -> str:
    return " ".join(_PUNCTUATION.sub(" ", text.lower()).split())


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))
```

`src/sazed/nlu/embedder.py`:
```python
from collections.abc import Sequence
from typing import Protocol

import numpy as np
import numpy.typing as npt


class Embedder(Protocol):
    """Turns sentences into L2-normalised float32 rows of length `dim`."""

    @property
    def dim(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> npt.NDArray[np.float32]: ...
```

- [ ] **Step 4: Implement the fakes**

`tests/fakes/embedder.py`:
```python
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
```

`tests/fakes/index.py`:
```python
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
```

- [ ] **Step 5: Implement the matcher**

`src/sazed/nlu/matcher.py`:
```python
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
```

- [ ] **Step 6: Run tests, types**

Run: `uv run pytest tests/nlu tests/fakes -v && uv run mypy && uv run ruff check .`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/sazed/nlu tests/nlu tests/fakes
git commit -m "feat(nlu): add normalisation, embedder port and intent matcher" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Slot extractors and control phrases

**Files:**
- Create: `src/sazed/nlu/slots/__init__.py`, `src/sazed/nlu/slots/app.py`, `src/sazed/nlu/slots/percent.py`, `src/sazed/nlu/slots/mute.py`, `src/sazed/nlu/control.py`, `src/sazed/nlu/CLAUDE.md`
- Test: `tests/nlu/test_slot_app.py`, `tests/nlu/test_slot_percent.py`, `tests/nlu/test_slot_mute.py`, `tests/nlu/test_control.py`

**Interfaces:**
- Consumes: `SlotValue`, `Ambiguous`, `Unmatched`, `Extraction` (Task 2), `normalize`/`strip_accents` (Task 6).
- Produces:
  - `extract_app(normalized: str, names: Sequence[str], aliases: Mapping[str, str]) -> Extraction | None` (None when the utterance names nothing, i.e. only command words). Constants `MIN_SCORE = 80`, `SUGGEST_SCORE = 60`, `MARGIN = 3`. `app_query(normalized) -> str`.
  - `extract_percent(normalized: str) -> SlotValue | None` (slot `percent`, int 0–100)
  - `extract_mute(normalized: str) -> SlotValue` (slot `mudo`, bool, always returns)
  - `ControlKind.{CONFIRM, DENY, CORRECT, FORGET, REPEAT}`; `Control(kind, rest: str = "")`; `parse_control(normalized) -> Control | None`; `pick_candidate(normalized, candidates: Sequence[str]) -> str | None`

- [ ] **Step 1: Write the failing tests**

`tests/nlu/test_slot_app.py`:
```python
from sazed.core.types import Ambiguous, SlotValue, Unmatched
from sazed.nlu.slots.app import extract_app

NAMES = [
    "Google Chrome",
    "Spotify",
    "Discord",
    "Visual Studio Code",
    "Claude Code",
    "Bloco de Notas",
    "Steam",
]


def test_word_contained_in_a_single_name_is_an_exact_match() -> None:
    assert extract_app("abre o chrome", NAMES, {}) == SlotValue(
        "app", "Google Chrome", "chrome", 1.0, exact=True
    )


def test_command_and_filler_words_are_ignored() -> None:
    result = extract_app("pode abrir o spotify pra mim por favor", NAMES, {})
    assert isinstance(result, SlotValue) and result.value == "Spotify"


def test_accents_and_case_do_not_matter() -> None:
    result = extract_app("abre o blóco de notas", NAMES, {})
    assert isinstance(result, SlotValue) and result.value == "Bloco de Notas"


def test_typo_matches_but_is_not_exact() -> None:
    result = extract_app("abre o crome", NAMES, {})
    assert isinstance(result, SlotValue)
    assert result.value == "Google Chrome"
    assert result.exact is False


def test_word_shared_by_two_names_is_ambiguous() -> None:
    assert extract_app("abre o code", NAMES, {}) == Ambiguous(
        "app", "code", ("Claude Code", "Visual Studio Code")
    )


def test_weak_match_is_unmatched_with_a_suggestion() -> None:
    assert extract_app("abre o disc", NAMES, {}) == Unmatched("app", "disc", "Discord")


def test_nothing_close_is_unmatched_without_suggestion() -> None:
    assert extract_app("abre o photoshop", NAMES, {}) == Unmatched("app", "photoshop", None)


def test_alias_wins_and_is_exact() -> None:
    result = extract_app("abre o zap", NAMES + ["WhatsApp"], {"zap": "WhatsApp"})
    assert result == SlotValue("app", "WhatsApp", "zap", 1.0, exact=True)


def test_alias_keys_are_normalised() -> None:
    result = extract_app("abre o código", NAMES, {"Código": "Visual Studio Code"})
    assert isinstance(result, SlotValue) and result.value == "Visual Studio Code"


def test_alias_to_an_app_that_no_longer_exists_is_ignored() -> None:
    assert extract_app("abre o zap", NAMES, {"zap": "WhatsApp"}) == Unmatched("app", "zap", None)


def test_only_command_words_means_no_app_named() -> None:
    assert extract_app("abre o programa", NAMES, {}) is None
```

`tests/nlu/test_slot_percent.py`:
```python
import pytest

from sazed.core.types import SlotValue
from sazed.nlu.slots.percent import extract_percent


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("volume em 30", 30),
        ("coloca o volume em 0", 0),
        ("volume em 100", 100),
        ("volume em trinta", 30),
        ("volume em trinta e cinco", 35),
        ("aumenta o volume em dez", 10),
        ("volume em quinze", 15),
        ("volume na metade", 50),
        ("volume no máximo", 100),
        ("volume no mínimo", 0),
        ("volume em cinco", 5),
    ],
)
def test_reads_numbers_and_words(text: str, value: int) -> None:
    result = extract_percent(text)
    assert isinstance(result, SlotValue)
    assert result.name == "percent"
    assert result.value == value


def test_no_number_gives_none() -> None:
    assert extract_percent("aumenta o volume") is None


def test_article_um_is_not_the_number_one() -> None:
    assert extract_percent("abaixa um pouco") is None


def test_out_of_range_number_is_ignored() -> None:
    assert extract_percent("volume em 150") is None
```

`tests/nlu/test_slot_mute.py`:
```python
import pytest

from sazed.nlu.slots.mute import extract_mute


@pytest.mark.parametrize("text", ["muta", "silencia", "coloca no mudo", "tira o som"])
def test_mute_phrases_mean_true(text: str) -> None:
    assert extract_mute(text).value is True


@pytest.mark.parametrize(
    "text", ["tira do mudo", "desmuta", "volta o som", "ativa o som", "liga o áudio"]
)
def test_unmute_phrases_mean_false(text: str) -> None:
    result = extract_mute(text)
    assert result.name == "mudo"
    assert result.value is False
```

`tests/nlu/test_control.py`:
```python
import pytest

from sazed.nlu.control import Control, ControlKind, parse_control, pick_candidate


@pytest.mark.parametrize("text", ["sim", "pode", "isso mesmo", "claro", "pode sim", "ok"])
def test_confirm(text: str) -> None:
    assert parse_control(text) == Control(ControlKind.CONFIRM)


@pytest.mark.parametrize("text", ["não", "nao", "cancela", "deixa pra lá", "melhor não"])
def test_deny(text: str) -> None:
    assert parse_control(text) == Control(ControlKind.DENY)


@pytest.mark.parametrize("text", ["esquece isso", "esqueça isso", "esquece"])
def test_forget(text: str) -> None:
    assert parse_control(text) == Control(ControlKind.FORGET)


@pytest.mark.parametrize("text", ["de novo", "outra vez", "mais", "mais um pouco"])
def test_repeat(text: str) -> None:
    assert parse_control(text) == Control(ControlKind.REPEAT)


@pytest.mark.parametrize(
    ("text", "rest"),
    [
        ("não era o discord", "discord"),
        ("era pra fechar", "fechar"),
        ("é o discord", "discord"),
        ("eu quis dizer spotify", "spotify"),
        ("não era o código", "código"),
    ],
)
def test_correction_keeps_the_rest_with_accents(text: str, rest: str) -> None:
    assert parse_control(text) == Control(ControlKind.CORRECT, rest)


@pytest.mark.parametrize("text", ["abre o chrome", "não é o discord", "e abre o spotify", ""])
def test_ordinary_commands_are_not_control(text: str) -> None:
    assert parse_control(text) is None


CANDIDATES = ("Claude Code", "Visual Studio Code")


@pytest.mark.parametrize(
    ("text", "choice"),
    [
        ("o segundo", "Visual Studio Code"),
        ("2", "Visual Studio Code"),
        ("primeiro", "Claude Code"),
        ("o último", "Visual Studio Code"),
        ("o visual studio", "Visual Studio Code"),
        ("claude", "Claude Code"),
    ],
)
def test_pick_candidate(text: str, choice: str) -> None:
    assert pick_candidate(text, CANDIDATES) == choice


@pytest.mark.parametrize("text", ["o terceiro", "5", "aumenta o volume", "code"])
def test_pick_candidate_refuses_unclear_answers(text: str) -> None:
    assert pick_candidate(text, CANDIDATES) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/nlu -v`
Expected: FAIL with `ModuleNotFoundError` for `sazed.nlu.slots` and `sazed.nlu.control`.

- [ ] **Step 3: Implement the app extractor**

`src/sazed/nlu/slots/__init__.py`:
```python
"""Slot extractors. Each returns SlotValue, Ambiguous, Unmatched, or None (nothing named)."""
```

`src/sazed/nlu/slots/app.py`:
```python
"""Match an app name in an utterance against the catalog and aliases. Pure."""

from collections.abc import Mapping, Sequence

from rapidfuzz import fuzz

from sazed.core.types import Ambiguous, Extraction, SlotValue, Unmatched
from sazed.nlu.normalize import normalize, strip_accents

MIN_SCORE = 80
SUGGEST_SCORE = 60
MARGIN = 3

COMMAND_WORDS = frozenset(
    """
    abre abra abrir abri inicia inicie iniciar executa execute executar roda rode rodar
    liga ligar fecha feche fechar encerra encerre encerrar mata mate matar sai sair
    desliga desligar processo
    o a os as um uma do da dos das de no na pro pra para mim me por favor ai
    app aplicativo programa sazed pode poderia voce consegue quero que agora e
    """.split()
)


def _key(text: str) -> str:
    return strip_accents(normalize(text))


def app_query(normalized: str) -> str:
    return " ".join(t for t in strip_accents(normalized).split() if t not in COMMAND_WORDS)


def _score(query: str, name_key: str) -> float:
    by_token = max((fuzz.ratio(query, token) for token in name_key.split()), default=0.0)
    return max(fuzz.token_set_ratio(query, name_key), by_token)


def extract_app(
    normalized: str, names: Sequence[str], aliases: Mapping[str, str]
) -> Extraction | None:
    query = app_query(normalized)
    if not query:
        return None

    known = set(names)
    alias_value = {_key(k): v for k, v in aliases.items()}.get(query)
    if alias_value is not None and alias_value in known:
        return SlotValue("app", alias_value, query, 1.0, exact=True)

    scored = sorted(((_score(query, _key(n)), n) for n in names), key=lambda sn: (-sn[0], sn[1]))
    if not scored:
        return Unmatched("app", query, None)
    best = scored[0][0]
    if best < MIN_SCORE:
        suggestion = scored[0][1] if best >= SUGGEST_SCORE else None
        return Unmatched("app", query, suggestion)
    top = tuple(n for s, n in scored if s >= best - MARGIN)
    if len(top) > 1:
        return Ambiguous("app", query, top[:5])
    return SlotValue("app", top[0], query, best / 100, exact=best == 100)
```

- [ ] **Step 4: Implement percent and mute**

`src/sazed/nlu/slots/percent.py`:
```python
"""Read a 0-100 percentage from digits or pt-BR number words. Pure."""

from sazed.core.types import SlotValue
from sazed.nlu.normalize import strip_accents

_UNITS = {
    "zero": 0, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9,
}
_TEENS = {
    "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14,
    "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19,
}
_TENS = {
    "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50,
    "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90,
}
_WORDS = {"metade": 50, "meio": 50, "maximo": 100, "tudo": 100, "cem": 100, "minimo": 0}
# "um"/"uma" are left out on purpose: in "abaixa um pouco" they are articles.
_UNITS_AFTER_E = {**_UNITS, "um": 1, "uma": 1}


def _value(n: int, raw: str) -> SlotValue | None:
    return SlotValue("percent", n, raw, 1.0) if 0 <= n <= 100 else None


def extract_percent(normalized: str) -> SlotValue | None:
    tokens = strip_accents(normalized).split()
    for token in tokens:
        if token.isdigit():
            return _value(int(token), token)
    for i, token in enumerate(tokens):
        if token in _WORDS:
            return _value(_WORDS[token], token)
        if token in _TENS:
            n = _TENS[token]
            if i + 2 < len(tokens) and tokens[i + 1] == "e" and tokens[i + 2] in _UNITS_AFTER_E:
                return _value(n + _UNITS_AFTER_E[tokens[i + 2]], " ".join(tokens[i : i + 3]))
            return _value(n, token)
        if token in _TEENS:
            return _value(_TEENS[token], token)
        if token in _UNITS:
            return _value(_UNITS[token], token)
    return None
```

`src/sazed/nlu/slots/mute.py`:
```python
"""Mute or unmute? Unmute phrases are listed; anything else under volume_mudo mutes. Pure."""

from sazed.core.types import SlotValue
from sazed.nlu.normalize import strip_accents

_UNMUTE = (
    "tira do mudo", "tirar do mudo", "desmuta", "desmutar", "desmute",
    "volta o som", "volta o audio", "ativa o som", "ativa o audio", "liga o som", "liga o audio",
)


def extract_mute(normalized: str) -> SlotValue:
    text = strip_accents(normalized)
    unmute = next((p for p in _UNMUTE if p in text), None)
    if unmute is not None:
        return SlotValue("mudo", False, unmute, 1.0)
    return SlotValue("mudo", True, text, 1.0)
```

- [ ] **Step 5: Implement control phrases**

`src/sazed/nlu/control.py`:
```python
"""Dialogue control phrases (yes, no, correction, forget, repeat). Deterministic, pure.

Matching runs on accent-stripped text. Accent stripping preserves length for Latin text, so
the correction's `rest` is sliced from the original normalised text and keeps its accents.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from rapidfuzz import fuzz

from sazed.nlu.normalize import normalize, strip_accents


class ControlKind(Enum):
    CONFIRM = "confirm"
    DENY = "deny"
    CORRECT = "correct"
    FORGET = "forget"
    REPEAT = "repeat"


@dataclass(frozen=True)
class Control:
    kind: ControlKind
    rest: str = ""


_CONFIRM = frozenset({
    "sim", "pode", "pode sim", "isso", "isso mesmo", "claro", "confirmo", "confirma",
    "exato", "positivo", "sim por favor", "pode ser", "manda ver", "ok", "certo",
})
_DENY = frozenset({
    "nao", "nao obrigado", "negativo", "cancela", "cancelar", "deixa", "deixa pra la",
    "deixa para la", "melhor nao", "agora nao",
})
_FORGET = frozenset({"esquece isso", "esqueca isso", "esquece", "esqueca", "pode esquecer"})
_REPEAT = frozenset({"de novo", "outra vez", "mais", "mais um pouco", "repete", "repita"})

# "não é o X" is deliberately absent: without punctuation it reads as a negation.
_CORRECT = re.compile(
    r"^(?:(?:nao\s+)?(?:eu\s+)?(?:quis|queria)\s+dizer\s+(?:o\s+|a\s+)?"
    r"|(?:nao\s+)?era\s+(?:pra\s+|para\s+)?(?:o\s+|a\s+)?"
    r"|e\s+(?:o|a)\s+)"
    r"(?P<rest>.+)$"
)

_ORDINALS = {
    "primeiro": 1, "primeira": 1, "segundo": 2, "segunda": 2, "terceiro": 3, "terceira": 3,
    "quarto": 4, "quarta": 4, "quinto": 5, "quinta": 5, "ultimo": -1, "ultima": -1,
}
_PICK_MIN = 85


def parse_control(normalized: str) -> Control | None:
    text = strip_accents(normalized)
    if text in _CONFIRM:
        return Control(ControlKind.CONFIRM)
    if text in _DENY:
        return Control(ControlKind.DENY)
    if text in _FORGET:
        return Control(ControlKind.FORGET)
    if text in _REPEAT:
        return Control(ControlKind.REPEAT)
    match = _CORRECT.match(text)
    if match:
        return Control(ControlKind.CORRECT, normalized[match.start("rest") :])
    return None


def pick_candidate(normalized: str, candidates: Sequence[str]) -> str | None:
    text = strip_accents(normalized)
    for token in text.split():
        if token.isdigit():
            n = int(token)
            return candidates[n - 1] if 1 <= n <= len(candidates) else None
        if token in _ORDINALS:
            n = _ORDINALS[token]
            if n == -1:
                return candidates[-1]
            return candidates[n - 1] if n <= len(candidates) else None
    scored = sorted(
        ((fuzz.token_set_ratio(text, strip_accents(normalize(c))), c) for c in candidates),
        key=lambda sc: -sc[0],
    )
    if not scored or scored[0][0] < _PICK_MIN:
        return None
    if len(scored) > 1 and scored[1][0] >= scored[0][0]:
        return None
    return scored[0][1]
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/nlu -v && uv run mypy && uv run ruff check .`
Expected: PASS. If a fuzzy case fails, print the scores (`fuzz.ratio`/`token_set_ratio`) and fix the scorer or the case's *expectation* only if the expectation was wrong about what a person means. Never adjust a threshold just to turn one test green, and record any change in `src/sazed/nlu/CLAUDE.md`.

- [ ] **Step 7: Write `src/sazed/nlu/CLAUDE.md`**

```markdown
# sazed.nlu

Understanding text: normalisation, the embedder port, intent ranking, slot extraction and
dialogue-control phrases. Pure functions over already-loaded data; no OS access, no clock.

## Conventions
- `normalize()` keeps accents (the embedder benefits). Every *matching* step uses
  `strip_accents()` on both sides. Never compare a stripped string with an unstripped one.
- Extractors return `SlotValue | Ambiguous | Unmatched | None`. `None` means "nothing was
  named", and the policy asks for it. `Unmatched` means "named, but unknown", and the skill reports it.
- App matching score = max(token_set_ratio(query, name), best per-token ratio). 100 is
  "exact" (no confirmation needed to close). Thresholds: MIN_SCORE 80, SUGGEST_SCORE 60, MARGIN 3.

## Traps
- `um`/`uma` are articles, not the number one ("abaixa um pouco").
- "não é o X" is not a correction: without the comma it is a negation.
- Numbers outside 0–100 are ignored, so the user is asked again instead of being clamped silently.
- `IntentMatcher.add_examples` embeds in one batch; adding seeds one at a time is ~N× slower with the real model.

## Not here
The ONNX model (→ `adapters/onnx`), app catalog I/O (→ `adapters/windows`), deciding what
to do with a match (→ `core.policy`).
```

- [ ] **Step 8: Commit**

```bash
git add src/sazed/nlu tests/nlu
git commit -m "feat(nlu): add app, percent and mute extractors and control phrases" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Skill contract and the PC skills

**Files:**
- Create: `src/sazed/core/skill.py`, `src/sazed/skills/pc/__init__.py`, `src/sazed/skills/pc/apps.py`, `src/sazed/skills/pc/volume.py`, `src/sazed/skills/CLAUDE.md`
- Create: `tests/fakes/ports.py`
- Test: `tests/fakes/test_ports.py`, `tests/skills/test_apps.py`, `tests/skills/test_volume.py`, `tests/skills/test_specs.py`

**Interfaces:**
- Consumes: types and outcomes (Task 2), `normalize` (Task 6, test only).
- Produces:
  - `SlotSpec(name: str, required: bool, question: str)`; `SkillContext(now: datetime)`
  - `IntentSpec(id, examples: tuple[str, ...], slots: tuple[SlotSpec, ...], describe: Callable[[Slots], str], requires_confirmation: Callable[[Slots], bool] = never)` with `.required -> frozenset[str]`, `.slot_names -> frozenset[str]`, `.question(slot) -> str`
  - `class Skill(Protocol)`: `id: str`, `intents: Sequence[IntentSpec]`, `execute(intent_id, slots, ctx) -> Outcome`
  - `AppEntry(name, target, shortcut)`; ports `AppCatalog.entries() -> Sequence[AppEntry]`, `AppLauncher.launch(entry)`, `.instances(entry) -> int`, `.close(entry) -> int`; `AppsSkill(catalog, launcher)` with intents `abrir_app`, `fechar_app`
  - `AudioControl.get_volume() -> int`, `.set_volume(percent)`, `.set_muted(muted)`; `VolumeSkill(audio)` with intents `volume_definir`, `volume_aumentar`, `volume_diminuir`, `volume_mudo`; `DEFAULT_STEP = 10`
  - Fakes: `FakeCatalog(names)`, `FakeLauncher` (`.launched`, `.closed`, `.running: dict[str, int]`, `.fail_with: Exception | None`), `FakeAudio` (`.volume`, `.muted`)

- [ ] **Step 1: Write the skill contract** (types only; exercised by every test below)

`src/sazed/core/skill.py`:
```python
"""What a skill is. Skills never touch the OS; they call ports."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sazed.core.outcomes import Outcome
from sazed.core.types import Slots


def never(slots: Slots) -> bool:
    return False


@dataclass(frozen=True)
class SlotSpec:
    name: str
    required: bool
    question: str
    """pt-BR question asked when the slot is missing, e.g. "Qual programa devo abrir?"."""


@dataclass(frozen=True)
class SkillContext:
    now: datetime


@dataclass(frozen=True)
class IntentSpec:
    id: str
    examples: tuple[str, ...]
    slots: tuple[SlotSpec, ...]
    describe: Callable[[Slots], str]
    """pt-BR infinitive phrase for confirmations and errors, e.g. "abrir Google Chrome"."""
    requires_confirmation: Callable[[Slots], bool] = never

    @property
    def required(self) -> frozenset[str]:
        return frozenset(s.name for s in self.slots if s.required)

    @property
    def slot_names(self) -> frozenset[str]:
        return frozenset(s.name for s in self.slots)

    def question(self, slot: str) -> str:
        return next(s.question for s in self.slots if s.name == slot)


class Skill(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def intents(self) -> Sequence[IntentSpec]: ...

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome: ...
```

- [ ] **Step 2: Write the failing tests for the fakes, then the skills**

`tests/fakes/test_ports.py`:
```python
import pytest
from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher


def test_catalog_builds_one_entry_per_name() -> None:
    names = [e.name for e in FakeCatalog(["Spotify", "Steam"]).entries()]
    assert names == ["Spotify", "Steam"]


def test_launch_records_and_counts_an_instance() -> None:
    (entry,) = FakeCatalog(["Spotify"]).entries()
    launcher = FakeLauncher()
    launcher.launch(entry)
    assert launcher.launched == ["Spotify"]
    assert launcher.instances(entry) == 1


def test_close_returns_instances_closed_and_clears_them() -> None:
    (entry,) = FakeCatalog(["Spotify"]).entries()
    launcher = FakeLauncher(running={"Spotify": 2})
    assert launcher.close(entry) == 2
    assert launcher.instances(entry) == 0
    assert launcher.closed == ["Spotify"]


def test_launcher_can_be_told_to_fail() -> None:
    (entry,) = FakeCatalog(["Spotify"]).entries()
    launcher = FakeLauncher(fail_with=OSError("boom"))
    with pytest.raises(OSError):
        launcher.launch(entry)
    assert launcher.launched == []


def test_audio_records_state() -> None:
    audio = FakeAudio(volume=40)
    audio.set_volume(70)
    audio.set_muted(True)
    assert (audio.get_volume(), audio.muted) == (70, True)
```

`tests/skills/test_apps.py`:
```python
from datetime import datetime

from fakes.ports import FakeCatalog, FakeLauncher

from sazed.core.outcomes import AppClosed, AppNotFound, AppNotRunning, AppOpened
from sazed.core.skill import SkillContext
from sazed.core.types import SlotValue, Unmatched
from sazed.skills.pc.apps import AppsSkill

CTX = SkillContext(now=datetime(2026, 10, 14, 12, 0))
CHROME = SlotValue("app", "Google Chrome", "chrome", 1.0, exact=True)
CROME = SlotValue("app", "Google Chrome", "crome", 0.91, exact=False)


def make(running: dict[str, int] | None = None) -> tuple[AppsSkill, FakeLauncher]:
    launcher = FakeLauncher(running=running)
    return AppsSkill(FakeCatalog(["Google Chrome", "Spotify"]), launcher), launcher


def spec(skill: AppsSkill, intent_id: str):  # type: ignore[no-untyped-def]
    return next(i for i in skill.intents if i.id == intent_id)


def test_open_launches_the_catalog_entry() -> None:
    skill, launcher = make()
    assert skill.execute("abrir_app", {"app": CHROME}, CTX) == AppOpened("Google Chrome")
    assert launcher.launched == ["Google Chrome"]


def test_open_unmatched_reports_not_found_and_launches_nothing() -> None:
    skill, launcher = make()
    outcome = skill.execute("abrir_app", {"app": Unmatched("app", "disc", "Discord")}, CTX)
    assert outcome == AppNotFound("disc", "Discord")
    assert launcher.launched == []


def test_open_value_missing_from_catalog_reports_not_found() -> None:
    skill, launcher = make()
    gone = SlotValue("app", "Steam", "steam", 1.0)
    assert skill.execute("abrir_app", {"app": gone}, CTX) == AppNotFound("steam", None)
    assert launcher.launched == []


def test_close_running_app_closes_it() -> None:
    skill, launcher = make(running={"Google Chrome": 1})
    assert skill.execute("fechar_app", {"app": CHROME}, CTX) == AppClosed("Google Chrome")
    assert launcher.closed == ["Google Chrome"]
    assert launcher.running == {}


def test_close_app_not_running_reports_it_and_closes_nothing() -> None:
    skill, launcher = make()
    assert skill.execute("fechar_app", {"app": CHROME}, CTX) == AppNotRunning("Google Chrome")
    assert launcher.closed == []


def test_close_exact_single_instance_needs_no_confirmation() -> None:
    skill, _ = make(running={"Google Chrome": 1})
    assert spec(skill, "fechar_app").requires_confirmation({"app": CHROME}) is False


def test_close_inexact_match_needs_confirmation() -> None:
    skill, _ = make(running={"Google Chrome": 1})
    assert spec(skill, "fechar_app").requires_confirmation({"app": CROME}) is True


def test_close_with_several_instances_needs_confirmation() -> None:
    skill, _ = make(running={"Google Chrome": 2})
    assert spec(skill, "fechar_app").requires_confirmation({"app": CHROME}) is True


def test_open_never_needs_confirmation() -> None:
    skill, _ = make(running={"Google Chrome": 2})
    assert spec(skill, "abrir_app").requires_confirmation({"app": CROME}) is False


def test_describe_is_a_pt_br_infinitive() -> None:
    skill, _ = make()
    assert spec(skill, "fechar_app").describe({"app": CHROME}) == "fechar Google Chrome"
    assert spec(skill, "abrir_app").describe({}) == "abrir um programa"
```

`tests/skills/test_volume.py`:
```python
from datetime import datetime

from fakes.ports import FakeAudio

from sazed.core.outcomes import Muted, Unmuted, VolumeChanged, VolumeSet
from sazed.core.skill import SkillContext
from sazed.core.types import SlotValue
from sazed.skills.pc.volume import VolumeSkill

CTX = SkillContext(now=datetime(2026, 10, 14, 12, 0))


def pct(n: int) -> dict[str, SlotValue]:
    return {"percent": SlotValue("percent", n, str(n), 1.0)}


def test_set_volume() -> None:
    audio = FakeAudio(volume=50)
    assert VolumeSkill(audio).execute("volume_definir", pct(30), CTX) == VolumeSet(30)
    assert audio.volume == 30


def test_increase_uses_default_step() -> None:
    audio = FakeAudio(volume=50)
    assert VolumeSkill(audio).execute("volume_aumentar", {}, CTX) == VolumeChanged(60)
    assert audio.volume == 60


def test_increase_uses_given_step() -> None:
    audio = FakeAudio(volume=50)
    VolumeSkill(audio).execute("volume_aumentar", pct(25), CTX)
    assert audio.volume == 75


def test_increase_clamps_at_100() -> None:
    audio = FakeAudio(volume=95)
    assert VolumeSkill(audio).execute("volume_aumentar", {}, CTX) == VolumeChanged(100)
    assert audio.volume == 100


def test_decrease_clamps_at_0() -> None:
    audio = FakeAudio(volume=5)
    VolumeSkill(audio).execute("volume_diminuir", {}, CTX)
    assert audio.volume == 0


def test_mute_and_unmute() -> None:
    audio = FakeAudio()
    skill = VolumeSkill(audio)
    assert skill.execute("volume_mudo", {"mudo": SlotValue("mudo", True, "muta", 1.0)}, CTX) == Muted()
    assert audio.muted is True
    off = {"mudo": SlotValue("mudo", False, "tira do mudo", 1.0)}
    assert skill.execute("volume_mudo", off, CTX) == Unmuted()
    assert audio.muted is False


def test_mute_without_slot_mutes() -> None:
    audio = FakeAudio()
    VolumeSkill(audio).execute("volume_mudo", {}, CTX)
    assert audio.muted is True
```

`tests/skills/test_specs.py`:
```python
from collections import Counter

import pytest
from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher

from sazed.core.skill import IntentSpec
from sazed.nlu.normalize import normalize
from sazed.skills.pc.apps import AppsSkill
from sazed.skills.pc.volume import VolumeSkill

SPECS: list[IntentSpec] = [
    *AppsSkill(FakeCatalog([]), FakeLauncher()).intents,
    *VolumeSkill(FakeAudio()).intents,
]


def test_intent_ids_are_unique() -> None:
    assert [i for i, n in Counter(s.id for s in SPECS).items() if n > 1] == []


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_each_intent_has_enough_seed_examples(spec: IntentSpec) -> None:
    assert len(spec.examples) >= 8


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_seed_examples_are_already_normalised(spec: IntentSpec) -> None:
    assert [e for e in spec.examples if normalize(e) != e] == []


def test_no_example_belongs_to_two_intents() -> None:
    counts = Counter(e for s in SPECS for e in s.examples)
    assert [e for e, n in counts.items() if n > 1] == []


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_every_slot_has_a_pt_br_question(spec: IntentSpec) -> None:
    assert all(s.question.endswith("?") for s in spec.slots)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/fakes/test_ports.py tests/skills -v`
Expected: FAIL with `ModuleNotFoundError` (`fakes.ports`, `sazed.skills.pc`).

- [ ] **Step 4: Implement the fakes**

`tests/fakes/ports.py`:
```python
"""In-memory ports. Tests assert their state, not only the response text."""

from collections.abc import Sequence

from sazed.skills.pc.apps import AppEntry


class FakeCatalog:
    def __init__(self, names: Sequence[str]) -> None:
        self._entries = [AppEntry(n, f"C:/Apps/{n}.exe", f"C:/Start/{n}.lnk") for n in names]

    def entries(self) -> Sequence[AppEntry]:
        return list(self._entries)


class FakeLauncher:
    def __init__(
        self, running: dict[str, int] | None = None, fail_with: Exception | None = None
    ) -> None:
        self.running: dict[str, int] = dict(running or {})
        self.launched: list[str] = []
        self.closed: list[str] = []
        self.fail_with = fail_with

    def launch(self, entry: AppEntry) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.launched.append(entry.name)
        self.running[entry.name] = self.running.get(entry.name, 0) + 1

    def instances(self, entry: AppEntry) -> int:
        return self.running.get(entry.name, 0)

    def close(self, entry: AppEntry) -> int:
        self.closed.append(entry.name)
        return self.running.pop(entry.name, 0)


class FakeAudio:
    def __init__(self, volume: int = 50, muted: bool = False) -> None:
        self.volume = volume
        self.muted = muted

    def get_volume(self) -> int:
        return self.volume

    def set_volume(self, percent: int) -> None:
        self.volume = percent

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
```

- [ ] **Step 5: Implement the skills**

`src/sazed/skills/pc/__init__.py`:
```python
"""PC control skills: apps and volume."""
```

`src/sazed/skills/pc/apps.py`:
```python
"""Open and close installed applications through ports."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sazed.core.outcomes import AppClosed, AppNotFound, AppNotRunning, AppOpened, Outcome
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue, Unmatched


@dataclass(frozen=True)
class AppEntry:
    name: str
    target: str
    shortcut: str


class AppCatalog(Protocol):
    def entries(self) -> Sequence[AppEntry]: ...


class AppLauncher(Protocol):
    def launch(self, entry: AppEntry) -> None: ...
    def instances(self, entry: AppEntry) -> int: ...
    def close(self, entry: AppEntry) -> int: ...


OPEN_EXAMPLES = (
    "abre o chrome", "abra o spotify", "abrir o discord", "inicia o steam",
    "executa o vscode", "pode abrir o word", "abre o bloco de notas pra mim",
    "quero abrir o excel", "liga o obs", "roda o firefox", "abre a calculadora",
    "inicie o teams", "me abre o whatsapp", "abre aí o explorador de arquivos",
)
CLOSE_EXAMPLES = (
    "fecha o chrome", "feche o spotify", "fechar o discord", "encerra o steam",
    "mata o processo do word", "pode fechar o excel", "fecha a calculadora",
    "sai do teams", "encerre o firefox", "fecha aí o obs", "quero fechar o whatsapp",
    "desliga o spotify",
)


def _label(slots: Slots) -> str:
    app = slots.get("app")
    if isinstance(app, SlotValue):
        return str(app.value)
    if isinstance(app, Unmatched):
        return app.raw
    return "um programa"


class AppsSkill:
    id = "apps"

    def __init__(self, catalog: AppCatalog, launcher: AppLauncher) -> None:
        self._catalog = catalog
        self._launcher = launcher
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "abrir_app",
                OPEN_EXAMPLES,
                (SlotSpec("app", True, "Qual programa devo abrir?"),),
                describe=lambda s: f"abrir {_label(s)}",
            ),
            IntentSpec(
                "fechar_app",
                CLOSE_EXAMPLES,
                (SlotSpec("app", True, "Qual programa devo fechar?"),),
                describe=lambda s: f"fechar {_label(s)}",
                requires_confirmation=self._close_needs_confirmation,
            ),
        )

    def _find(self, name: str) -> AppEntry | None:
        return next((e for e in self._catalog.entries() if e.name == name), None)

    def _close_needs_confirmation(self, slots: Slots) -> bool:
        app = slots.get("app")
        if not isinstance(app, SlotValue):
            return False
        entry = self._find(str(app.value))
        if entry is None:
            return False
        return not app.exact or self._launcher.instances(entry) > 1

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        app = slots.get("app")
        if isinstance(app, Unmatched):
            return AppNotFound(app.raw, app.suggestion)
        if app is None:
            raise ValueError(f"{intent_id} called without its required slot 'app'")
        entry = self._find(str(app.value))
        if entry is None:
            return AppNotFound(app.raw, None)
        if intent_id == "abrir_app":
            self._launcher.launch(entry)
            return AppOpened(entry.name)
        if intent_id == "fechar_app":
            if self._launcher.instances(entry) == 0:
                return AppNotRunning(entry.name)
            self._launcher.close(entry)
            return AppClosed(entry.name)
        raise ValueError(f"unknown intent {intent_id}")
```

`src/sazed/skills/pc/volume.py`:
```python
"""Master volume through the AudioControl port."""

from __future__ import annotations

from typing import Protocol

from sazed.core.outcomes import Muted, Outcome, Unmuted, VolumeChanged, VolumeSet
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue

DEFAULT_STEP = 10


class AudioControl(Protocol):
    def get_volume(self) -> int: ...
    def set_volume(self, percent: int) -> None: ...
    def set_muted(self, muted: bool) -> None: ...


SET_EXAMPLES = (
    "volume em 30", "coloca o volume em 50", "deixa o som em 20 por cento",
    "ajusta o volume pra 70", "volume no máximo", "volume na metade",
    "põe o volume em 10", "define o volume para 40", "som em 80", "quero o volume em 25",
)
UP_EXAMPLES = (
    "aumenta o volume", "aumenta o som", "sobe o volume", "mais alto",
    "aumenta o volume em 20", "sobe o som um pouco", "aumenta mais o volume",
    "coloca mais alto", "volume mais alto", "aumenta o áudio",
)
DOWN_EXAMPLES = (
    "diminui o volume", "abaixa o som", "baixa o volume", "mais baixo",
    "diminui o volume em 20", "abaixa um pouco", "reduz o volume",
    "volume mais baixo", "diminui o som", "abaixa o áudio",
)
MUTE_EXAMPLES = (
    "muta", "silencia", "mudo", "tira o som", "coloca no mudo", "tira do mudo",
    "desmuta", "volta o som", "ativa o som", "silencia o computador",
)


def _int(slots: Slots, name: str) -> int | None:
    value = slots.get(name)
    return int(value.value) if isinstance(value, SlotValue) else None


def _percent_label(slots: Slots) -> str:
    n = _int(slots, "percent")
    return f"{n}%" if n is not None else "um valor"


def _clamp(n: int) -> int:
    return max(0, min(100, n))


def _mute_label(slots: Slots) -> str:
    mute = slots.get("mudo")
    if isinstance(mute, SlotValue) and mute.value is False:
        return "reativar o som"
    return "silenciar o som"


class VolumeSkill:
    id = "volume"

    def __init__(self, audio: AudioControl) -> None:
        self._audio = audio
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "volume_definir",
                SET_EXAMPLES,
                (SlotSpec("percent", True, "Em quanto devo deixar o volume?"),),
                describe=lambda s: f"deixar o volume em {_percent_label(s)}",
            ),
            IntentSpec(
                "volume_aumentar",
                UP_EXAMPLES,
                (SlotSpec("percent", False, "Quanto devo aumentar?"),),
                describe=lambda s: "aumentar o volume",
            ),
            IntentSpec(
                "volume_diminuir",
                DOWN_EXAMPLES,
                (SlotSpec("percent", False, "Quanto devo diminuir?"),),
                describe=lambda s: "diminuir o volume",
            ),
            IntentSpec(
                "volume_mudo",
                MUTE_EXAMPLES,
                (SlotSpec("mudo", False, "Devo silenciar ou reativar o som?"),),
                describe=_mute_label,
            ),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id == "volume_definir":
            percent = _int(slots, "percent")
            if percent is None:
                raise ValueError("volume_definir called without its required slot 'percent'")
            self._audio.set_volume(_clamp(percent))
            return VolumeSet(_clamp(percent))
        if intent_id in ("volume_aumentar", "volume_diminuir"):
            step = _int(slots, "percent") or DEFAULT_STEP
            sign = 1 if intent_id == "volume_aumentar" else -1
            level = _clamp(self._audio.get_volume() + sign * step)
            self._audio.set_volume(level)
            return VolumeChanged(level)
        if intent_id == "volume_mudo":
            mute = slots.get("mudo")
            muted = bool(mute.value) if isinstance(mute, SlotValue) else True
            self._audio.set_muted(muted)
            return Muted() if muted else Unmuted()
        raise ValueError(f"unknown intent {intent_id}")
```
Note: `_int(...) or DEFAULT_STEP` treats an explicit `0` step as the default. That is intended, because "aumenta 0" is meaningless and a step of 0 would answer "Volume em 50%" without changing anything.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/fakes tests/skills -v && uv run mypy && uv run ruff check .`
Expected: PASS.

- [ ] **Step 7: Prove the destructive-action confirmation discriminates**

Mutation (a forgotten clause): in `_close_needs_confirmation`, change the return to `return not app.exact`.
Run: `uv run pytest tests/skills/test_apps.py -v`
Expected: `test_close_with_several_instances_needs_confirmation` FAILS. Paste the output under `## Destructive-action confirmation` in the proofs file. Revert, re-run, and expect everything to pass.

- [ ] **Step 8: Write `src/sazed/skills/CLAUDE.md`**

```markdown
# sazed.skills

Skills: intents, seed examples, slot schema, and `execute`. A skill decides *what* to do and
calls ports for *how*. Ports (`AppCatalog`, `AppLauncher`, `AudioControl`) are declared
next to the skill that needs them and implemented in `sazed.adapters`.

## Invariants
- No OS access, no I/O, no clock. Imports only `sazed.core` (tests/test_architecture.py).
- `execute` returns a failure *value* (`AppNotFound`, `AppNotRunning`) for expected
  problems. Adapter exceptions are not caught here: the runtime turns them into `ActionFailed`
  and logs them.
- Seed examples are pt-BR, already normalised (lowercase, no punctuation), unique across
  intents, at least 8 per intent (tests/skills/test_specs.py).
- `describe` returns a pt-BR infinitive ("abrir Google Chrome"); it is shown to the user.

## Traps
- `fechar_app` confirms when the match is inexact OR several root instances run. Both
  clauses are load-bearing (see the proofs file).
- Adding an intent with a new slot requires an extractor in `runtime/extractors.py`.
  `tests/runtime/test_extractors.py` fails until it exists.

## Not here
Text matching (→ `nlu`), Windows APIs (→ `adapters/windows`).
```

- [ ] **Step 9: Commit**

```bash
git add src/sazed/core/skill.py src/sazed/skills tests/fakes tests/skills docs/superpowers/proofs
git commit -m "feat(skills): add app and volume skills behind ports" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 9: SQLite coppermind

**Files:**
- Create: `src/sazed/adapters/sqlite/__init__.py`, `src/sazed/adapters/sqlite/coppermind.py`
- Test: `tests/adapters/test_sqlite_coppermind.py`

**Interfaces:**
- Consumes: the `Coppermind` port and its types (Task 4), `FAILURE_NAMES` (Task 2).
- Produces: `SqliteCoppermind(path: Path | str)` (`":memory:"` allowed) implementing `Coppermind`, plus `.schema_version -> int` and `.close()`. `MIGRATIONS: tuple[str, ...]`. `CoppermindVersionError(Exception)`.

- [ ] **Step 1: Write the failing tests**

`tests/adapters/test_sqlite_coppermind.py`:
```python
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from sazed.adapters.sqlite.coppermind import (
    MIGRATIONS,
    CoppermindVersionError,
    SqliteCoppermind,
)
from sazed.core.coppermind import (
    Episode,
    LearnedKind,
    NewAlias,
    NewExample,
    Reaction,
    StoredAlias,
)
from sazed.core.types import IntentScore

T0 = datetime(2026, 10, 14, 12, 0, 0)
EX = NewExample("abre aí o chrome", "abrir_app", b"\x01\x02\x03\x04", "confirmed")
AL = NewAlias("app", "zap", "WhatsApp")


def open_store(tmp_path: Path) -> SqliteCoppermind:
    return SqliteCoppermind(tmp_path / "sub" / "coppermind.db")


def test_learned_example_and_alias_survive_reopening(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    store.learn([EX], [AL], T0)
    store.close()
    reopened = open_store(tmp_path)
    (example,) = reopened.examples()
    assert (example.text, example.intent_id, example.embedding) == (
        "abre aí o chrome", "abrir_app", b"\x01\x02\x03\x04",
    )
    assert [(a.slot, a.alias, a.value) for a in reopened.aliases()] == [("app", "zap", "WhatsApp")]


def test_a_learning_step_that_fails_midway_leaves_no_rows(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    broken = NewAlias("app", "zap", None)  # type: ignore[arg-type]
    with pytest.raises(sqlite3.IntegrityError):
        store.learn([EX], [broken], T0)
    store.close()
    reopened = open_store(tmp_path)
    assert reopened.examples() == []
    assert reopened.learned() == []


def test_learned_lists_newest_first(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    store.learn([EX], [], T0)
    store.learn([], [AL], T0 + timedelta(seconds=5))
    assert [i.kind for i in store.learned()] == [LearnedKind.ALIAS, LearnedKind.EXAMPLE]


def test_forget_latest_removes_the_whole_latest_batch_and_nothing_else(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    store.learn([EX], [], T0)
    other = NewExample("liga o navegador", "abrir_app", b"\x00" * 4, "offered")
    store.learn([other], [AL], T0 + timedelta(seconds=5))
    forgotten = store.forget_latest()
    assert sorted(i.text for i in forgotten) == ["liga o navegador", "zap"]
    assert [e.text for e in store.examples()] == ["abre aí o chrome"]
    assert store.aliases() == []


def test_forget_latest_with_nothing_learned(tmp_path: Path) -> None:
    assert open_store(tmp_path).forget_latest() == []


def test_forget_by_id(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    (item,) = store.learn([EX], [], T0)
    assert store.forget(LearnedKind.EXAMPLE, item.id) == item
    assert store.examples() == []
    assert store.forget(LearnedKind.EXAMPLE, item.id) is None


def test_relearning_an_alias_replaces_its_value(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    store.learn([], [NewAlias("app", "code", "Claude Code")], T0)
    store.learn([], [NewAlias("app", "code", "Visual Studio Code")], T0)
    assert [(a.alias, a.value) for a in store.aliases()] == [("code", "Visual Studio Code")]


def test_fresh_database_is_at_the_latest_schema(tmp_path: Path) -> None:
    assert open_store(tmp_path).schema_version == len(MIGRATIONS)


def test_database_from_a_newer_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "coppermind.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    with pytest.raises(CoppermindVersionError):
        SqliteCoppermind(path)


def test_episode_round_trip_and_reaction_update(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    episode = Episode(
        utterance="Abre o Chrome!",
        at=T0,
        ranking=(IntentScore("abrir_app", 0.95), IntentScore("fechar_app", 0.6)),
        slots={"app": "Google Chrome"},
        decision="Execute",
        intent_id="abrir_app",
        outcome="AppOpened",
    )
    episode_id = store.record_episode(episode)
    store.set_reaction(episode_id, Reaction.CORRECTED)
    stored = store.episode(episode_id)
    assert stored is not None
    assert stored.episode.ranking == episode.ranking
    assert stored.episode.slots == {"app": "Google Chrome"}
    assert stored.episode.reaction is Reaction.CORRECTED
    assert stored.episode.at == T0


def test_recent_failures_selects_only_failures_newest_first(tmp_path: Path) -> None:
    store = open_store(tmp_path)

    def ep(decision: str, outcome: str, reaction: Reaction = Reaction.NONE) -> int:
        return store.record_episode(
            Episode("x", T0, (), {}, decision, None, outcome, reaction)
        )

    ok = ep("Execute", "AppOpened")
    not_understood = ep("NotUnderstood", "")
    denied = ep("Confirm", "", Reaction.DENIED)
    missing = ep("Execute", "AppNotFound")
    crashed = ep("error", "ActionFailed")
    ids = [s.id for s in store.recent_failures(10)]
    assert ids == [crashed, missing, denied, not_understood]
    assert ok not in ids


def test_aliases_are_returned_as_stored_values(tmp_path: Path) -> None:
    store = open_store(tmp_path)
    (item,) = store.learn([], [AL], T0)
    assert store.aliases() == [StoredAlias(item.id, "app", "zap", "WhatsApp")]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/adapters/test_sqlite_coppermind.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sazed.adapters.sqlite'`.

- [ ] **Step 3: Implement**

`src/sazed/adapters/sqlite/__init__.py`:
```python
"""SQLite persistence (the coppermind)."""
```

`src/sazed/adapters/sqlite/coppermind.py`:
```python
"""SQLite implementation of the coppermind port.

Schema versions live in PRAGMA user_version; MIGRATIONS[n] upgrades from n to n+1. Never
edit a shipped migration: append a new one.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from sazed.core.coppermind import (
    Episode,
    LearnedItem,
    LearnedKind,
    NewAlias,
    NewExample,
    Reaction,
    StoredAlias,
    StoredEpisode,
    StoredExample,
)
from sazed.core.outcomes import FAILURE_NAMES
from sazed.core.types import IntentScore

MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE learned_examples (
        id INTEGER PRIMARY KEY,
        text TEXT NOT NULL,
        intent_id TEXT NOT NULL,
        embedding BLOB NOT NULL,
        origin TEXT NOT NULL,
        batch INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE slot_aliases (
        id INTEGER PRIMARY KEY,
        slot TEXT NOT NULL,
        alias TEXT NOT NULL,
        value TEXT NOT NULL,
        batch INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (slot, alias)
    );
    CREATE TABLE episodes (
        id INTEGER PRIMARY KEY,
        utterance TEXT NOT NULL,
        at TEXT NOT NULL,
        ranking TEXT NOT NULL,
        slots TEXT NOT NULL,
        decision TEXT NOT NULL,
        intent_id TEXT,
        outcome TEXT NOT NULL,
        reaction TEXT NOT NULL
    );
    """,
)

_LEARNED = """
    SELECT 'example' AS kind, id, text, intent_id AS target, NULL AS slot, created_at, batch
      FROM learned_examples
    UNION ALL
    SELECT 'alias', id, alias, value, slot, created_at, batch FROM slot_aliases
"""
_FAILURE_OUTCOMES = sorted(FAILURE_NAMES)


class CoppermindVersionError(Exception):
    """The database was written by a newer Sazed than this one."""


def _item(row: sqlite3.Row | tuple[object, ...]) -> LearnedItem:
    kind, item_id, text, target, slot, created_at = row[:6]
    return LearnedItem(
        LearnedKind(kind), int(str(item_id)), str(text), str(target),
        None if slot is None else str(slot), datetime.fromisoformat(str(created_at)),
    )


class SqliteCoppermind:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._migrate()

    def _migrate(self) -> None:
        version = self.schema_version
        if version > len(MIGRATIONS):
            raise CoppermindVersionError(
                f"database schema {version} is newer than supported {len(MIGRATIONS)}"
            )
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            self._conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")

    @property
    def schema_version(self) -> int:
        (version,) = self._conn.execute("PRAGMA user_version").fetchone()
        return int(version)

    def close(self) -> None:
        self._conn.close()

    # learning ----------------------------------------------------------------

    def learn(
        self, examples: Sequence[NewExample], aliases: Sequence[NewAlias], now: datetime
    ) -> list[LearnedItem]:
        if not examples and not aliases:
            return []
        stamp = now.isoformat()
        items: list[LearnedItem] = []
        with self._conn:  # one transaction: commits on success, rolls back on any error
            (batch,) = self._conn.execute(
                "SELECT COALESCE(MAX(b), 0) + 1 FROM ("
                " SELECT MAX(batch) AS b FROM learned_examples"
                " UNION ALL SELECT MAX(batch) FROM slot_aliases)"
            ).fetchone()
            for ex in examples:
                cur = self._conn.execute(
                    "INSERT INTO learned_examples"
                    " (text, intent_id, embedding, origin, batch, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (ex.text, ex.intent_id, ex.embedding, ex.origin, batch, stamp),
                )
                assert cur.lastrowid is not None
                items.append(
                    LearnedItem(LearnedKind.EXAMPLE, cur.lastrowid, ex.text, ex.intent_id, None, now)
                )
            for al in aliases:
                self._conn.execute(
                    "INSERT INTO slot_aliases (slot, alias, value, batch, created_at)"
                    " VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT (slot, alias) DO UPDATE SET"
                    " value = excluded.value, batch = excluded.batch,"
                    " created_at = excluded.created_at",
                    (al.slot, al.alias, al.value, batch, stamp),
                )
                (alias_id,) = self._conn.execute(
                    "SELECT id FROM slot_aliases WHERE slot = ? AND alias = ?",
                    (al.slot, al.alias),
                ).fetchone()
                items.append(LearnedItem(LearnedKind.ALIAS, alias_id, al.alias, al.value, al.slot, now))
        return items

    def examples(self) -> list[StoredExample]:
        rows = self._conn.execute(
            "SELECT id, text, intent_id, embedding FROM learned_examples ORDER BY id"
        ).fetchall()
        return [StoredExample(i, t, intent, bytes(e)) for i, t, intent, e in rows]

    def aliases(self) -> list[StoredAlias]:
        rows = self._conn.execute(
            "SELECT id, slot, alias, value FROM slot_aliases ORDER BY id"
        ).fetchall()
        return [StoredAlias(*row) for row in rows]

    def learned(self) -> list[LearnedItem]:
        rows = self._conn.execute(f"{_LEARNED} ORDER BY batch DESC, id DESC").fetchall()
        return [_item(r) for r in rows]

    def forget(self, kind: LearnedKind, item_id: int) -> LearnedItem | None:
        table = "learned_examples" if kind is LearnedKind.EXAMPLE else "slot_aliases"
        row = self._conn.execute(
            f"SELECT * FROM ({_LEARNED}) WHERE kind = ? AND id = ?", (kind.value, item_id)
        ).fetchone()
        if row is None:
            return None
        with self._conn:
            self._conn.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
        return _item(row)

    def forget_latest(self) -> list[LearnedItem]:
        rows = self._conn.execute(
            f"SELECT * FROM ({_LEARNED}) WHERE batch = (SELECT MAX(batch) FROM ({_LEARNED}))"
        ).fetchall()
        if not rows:
            return []
        batch = rows[0][6]
        with self._conn:
            self._conn.execute("DELETE FROM learned_examples WHERE batch = ?", (batch,))
            self._conn.execute("DELETE FROM slot_aliases WHERE batch = ?", (batch,))
        return [_item(r) for r in rows]

    # episodes ----------------------------------------------------------------

    def record_episode(self, episode: Episode) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO episodes"
                " (utterance, at, ranking, slots, decision, intent_id, outcome, reaction)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    episode.utterance,
                    episode.at.isoformat(),
                    json.dumps([[s.intent_id, s.score] for s in episode.ranking]),
                    json.dumps(dict(episode.slots), ensure_ascii=False),
                    episode.decision,
                    episode.intent_id,
                    episode.outcome,
                    episode.reaction.value,
                ),
            )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def set_reaction(self, episode_id: int, reaction: Reaction) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE episodes SET reaction = ? WHERE id = ?", (reaction.value, episode_id)
            )

    def episodes(self, limit: int) -> list[StoredEpisode]:
        return self._episodes("1 = 1", (), limit)

    def episode(self, episode_id: int) -> StoredEpisode | None:
        found = self._episodes("id = ?", (episode_id,), 1)
        return found[0] if found else None

    def recent_failures(self, limit: int) -> list[StoredEpisode]:
        marks = ", ".join("?" for _ in _FAILURE_OUTCOMES)
        where = (
            "decision IN ('NotUnderstood', 'error')"
            " OR reaction IN ('denied', 'corrected')"
            f" OR outcome IN ({marks})"
        )
        return self._episodes(where, tuple(_FAILURE_OUTCOMES), limit)

    def _episodes(self, where: str, params: tuple[object, ...], limit: int) -> list[StoredEpisode]:
        rows = self._conn.execute(
            "SELECT id, utterance, at, ranking, slots, decision, intent_id, outcome, reaction"
            f" FROM episodes WHERE {where} ORDER BY id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [
            StoredEpisode(
                row_id,
                Episode(
                    utterance=utterance,
                    at=datetime.fromisoformat(at),
                    ranking=tuple(IntentScore(i, float(s)) for i, s in json.loads(ranking)),
                    slots=json.loads(slots),
                    decision=decision,
                    intent_id=intent_id,
                    outcome=outcome,
                    reaction=Reaction(reaction),
                ),
            )
            for row_id, utterance, at, ranking, slots, decision, intent_id, outcome, reaction in rows
        ]
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/adapters/test_sqlite_coppermind.py -v && uv run ruff check .`
Expected: PASS.

- [ ] **Step 5: Prove the learning transaction discriminates**

Mutation (an early commit, the classic partial write): inside `learn`, add `self._conn.commit()` right after the `INSERT INTO learned_examples` call.
Run: `uv run pytest tests/adapters/test_sqlite_coppermind.py::test_a_learning_step_that_fails_midway_leaves_no_rows -v`
Expected: FAIL. `reopened.examples()` contains the example. Paste the output under `## Learning transaction`. Revert, re-run, and expect PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sazed/adapters/sqlite tests/adapters/test_sqlite_coppermind.py docs/superpowers/proofs
git commit -m "feat(coppermind): add SQLite store with versioned schema" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Assistant — understand, execute, fail safely, record episodes

**Files:**
- Create: `src/sazed/runtime/extractors.py`, `src/sazed/runtime/assistant.py`
- Create: `tests/fakes/clock.py`, `tests/support/harness.py`, `tests/runtime/conftest.py`
- Test: `tests/fakes/test_clock.py`, `tests/support/test_harness.py`, `tests/runtime/test_extractors.py`, `tests/runtime/test_assistant_basic.py`

**Interfaces:**
- Consumes: everything from Tasks 2–9.
- Produces:
  - `SlotExtractor = Callable[[str, Mapping[str, str]], Extraction | None]` and `build_extractors(app_names: Sequence[str]) -> dict[str, SlotExtractor]` (keys `app`, `percent`, `mudo`) in `runtime/extractors.py`
  - `Settings(user_name: str, thresholds: Thresholds, learning: LearningThresholds, context_ttl_seconds: float)`
  - `Assistant(*, skills, index: IntentIndex, extractors, store: Coppermind, aliases: Mapping[str, Mapping[str, str]], settings, clock: Callable[[], datetime], rng: Random)` with `handle(text: str) -> Response`
  - `GENERIC_ACTION = "atender a esse pedido"`
  - Test harness fixture `make(script=None, *, running=None, volume=50, aliases=None, launcher_error=None, store=None, extra_skills=()) -> Harness` with `.say(text)`, `.assistant`, `.index`, `.store`, `.launcher`, `.audio`, `.clock`; `ManualClock` with `.advance(seconds)`

- [ ] **Step 1: Write the failing tests**

`tests/fakes/test_clock.py`:
```python
from datetime import datetime, timedelta

from fakes.clock import ManualClock


def test_clock_returns_its_time_and_advances() -> None:
    clock = ManualClock(datetime(2026, 10, 14, 12, 0))
    assert clock() == datetime(2026, 10, 14, 12, 0)
    clock.advance(61)
    assert clock() == datetime(2026, 10, 14, 12, 0) + timedelta(seconds=61)
```

`tests/runtime/test_extractors.py`:
```python
from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher

from sazed.core.types import SlotValue
from sazed.runtime.extractors import build_extractors
from sazed.skills.pc.apps import AppsSkill
from sazed.skills.pc.volume import VolumeSkill


def test_every_declared_slot_has_an_extractor() -> None:
    skills = [AppsSkill(FakeCatalog([]), FakeLauncher()), VolumeSkill(FakeAudio())]
    declared = {slot.name for skill in skills for spec in skill.intents for slot in spec.slots}
    assert declared <= set(build_extractors([]))


def test_app_extractor_uses_catalog_names_and_aliases() -> None:
    extract = build_extractors(["WhatsApp"])["app"]
    assert extract("abre o zap", {"zap": "WhatsApp"}) == SlotValue(
        "app", "WhatsApp", "zap", 1.0, exact=True
    )
```

`tests/fakes/clock.py`:
```python
from datetime import datetime, timedelta


class ManualClock:
    def __init__(self, start: datetime = datetime(2026, 10, 14, 12, 0)) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
```

`tests/support/harness.py` (importable as `support.harness`; a `conftest.py` is not importable under `--import-mode=importlib`):
```python
"""Assistant wired to fakes, for runtime tests."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from random import Random

from fakes.clock import ManualClock
from fakes.index import ScriptedIndex
from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher

from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.learning import LearningThresholds
from sazed.core.policy import Thresholds
from sazed.core.response import Response
from sazed.core.skill import Skill
from sazed.runtime.assistant import Assistant, Settings
from sazed.runtime.extractors import build_extractors
from sazed.skills.pc.apps import AppsSkill
from sazed.skills.pc.volume import VolumeSkill

APPS = ["Google Chrome", "Spotify", "Discord", "Visual Studio Code", "Claude Code"]
SETTINGS = Settings(
    user_name="Artur",
    thresholds=Thresholds(t_exec=0.90, t_confirm=0.70, g_min=0.05),
    learning=LearningThresholds(t_conflict=0.85, t_dup=0.97),
    context_ttl_seconds=60,
)


@dataclass
class Harness:
    assistant: Assistant
    index: ScriptedIndex
    store: SqliteCoppermind
    launcher: FakeLauncher
    audio: FakeAudio
    clock: ManualClock

    def say(self, text: str) -> Response:
        return self.assistant.handle(text)


Make = Callable[..., Harness]


def build_harness(
    script: Mapping[str, Mapping[str, float]] | None = None,
    *,
    running: dict[str, int] | None = None,
    volume: int = 50,
    aliases: Mapping[str, str] | None = None,
    launcher_error: Exception | None = None,
    store: SqliteCoppermind | None = None,
    extra_skills: Sequence[Skill] = (),
) -> Harness:
    index = ScriptedIndex(script)
    store = store or SqliteCoppermind(":memory:")
    launcher = FakeLauncher(running=running, fail_with=launcher_error)
    audio = FakeAudio(volume=volume)
    clock = ManualClock()
    skills: list[Skill] = [AppsSkill(FakeCatalog(APPS), launcher), VolumeSkill(audio)]
    assistant = Assistant(
        skills=[*skills, *extra_skills],
        index=index,
        extractors=build_extractors(APPS),
        store=store,
        aliases={"app": dict(aliases or {})},
        settings=SETTINGS,
        clock=clock,
        rng=Random(0),
    )
    return Harness(assistant, index, store, launcher, audio, clock)
```

`tests/runtime/conftest.py`:
```python
import pytest
from support.harness import Make, build_harness


@pytest.fixture
def make() -> Make:
    return build_harness
```

`tests/support/test_harness.py` (the harness is shared, so it is proven first):
```python
from support.harness import build_harness


def test_harness_wires_fakes_into_the_assistant() -> None:
    h = build_harness({"volume em 30": {"volume_definir": 0.97}})
    h.say("volume em 30")
    assert h.audio.volume == 30
    assert len(h.store.episodes(5)) == 1


def test_harness_clock_drives_the_assistant() -> None:
    h = build_harness()
    h.clock.advance(5)
    h.say("nada")
    assert h.store.episodes(1)[0].episode.at == h.clock.now
```

`tests/runtime/test_assistant_basic.py`:
```python
import logging

import pytest
from support.harness import Make

from sazed.core.decisions import AskSlot, Confirm, Execute, NotUnderstood
from sazed.core.outcomes import ActionFailed, AppNotFound, AppOpened, VolumeSet
from sazed.core.persona.definition import TEMPLATES

OPEN_CHROME = {"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60}}
VOLUME_30 = {"volume em 30": {"volume_definir": 0.97, "volume_aumentar": 0.70}}


def test_clear_command_executes_and_opens_the_app(make: Make) -> None:
    h = make(OPEN_CHROME)
    r = h.say("Abre o Chrome!")
    assert h.launcher.launched == ["Google Chrome"]
    assert r.outcome == AppOpened("Google Chrome")
    assert isinstance(r.decision, Execute)
    assert "Google Chrome" in r.text


def test_unknown_text_is_not_understood_and_does_nothing(make: Make) -> None:
    h = make(OPEN_CHROME)
    r = h.say("qual o sentido da vida")
    assert r.decision == NotUnderstood()
    assert h.launcher.launched == []
    assert r.text in {t.format(mestre="Mestre Artur") for t in TEMPLATES["NotUnderstood"]}


def test_low_score_asks_for_confirmation_without_executing(make: Make) -> None:
    h = make({"abre aí o chrome": {"abrir_app": 0.80, "fechar_app": 0.30}})
    r = h.say("abre aí o chrome")
    assert isinstance(r.decision, Confirm)
    assert h.launcher.launched == []
    assert "abrir Google Chrome" in r.text
    assert "abrir_app" not in r.text


def test_missing_slot_asks_the_slot_question(make: Make) -> None:
    h = make({"abre o programa": {"abrir_app": 0.95, "fechar_app": 0.40}})
    r = h.say("abre o programa")
    assert isinstance(r.decision, AskSlot)
    assert "Qual programa devo abrir?" in r.text


def test_unknown_app_reports_not_found(make: Make) -> None:
    h = make({"abre o photoshop": {"abrir_app": 0.95, "fechar_app": 0.40}})
    r = h.say("abre o photoshop")
    assert r.outcome == AppNotFound("photoshop", None)
    assert "photoshop" in r.text
    assert h.launcher.launched == []


def test_volume_command_changes_the_audio_state(make: Make) -> None:
    h = make(VOLUME_30)
    r = h.say("volume em 30")
    assert h.audio.volume == 30
    assert r.outcome == VolumeSet(30)
    assert "30%" in r.text


def test_skill_exception_is_rendered_politely_and_logged(
    make: Make, caplog: pytest.LogCaptureFixture
) -> None:
    h = make({**OPEN_CHROME, **VOLUME_30}, launcher_error=OSError("WinError 2: secret internals"))
    with caplog.at_level(logging.ERROR):
        r = h.say("abre o chrome")
    assert r.outcome == ActionFailed("abrir Google Chrome")
    assert "secret internals" not in r.text
    assert "WinError" not in r.text
    assert "secret internals" in caplog.text
    assert h.say("volume em 30").outcome == VolumeSet(30)


def test_unexpected_error_outside_skills_is_generic(
    make: Make, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = make(VOLUME_30)

    def explode(text: str) -> object:
        raise RuntimeError("index exploded")

    monkeypatch.setattr(h.index, "rank", explode)
    with caplog.at_level(logging.ERROR):
        r = h.say("volume em 30")
    assert r.outcome == ActionFailed("atender a esse pedido")
    assert "exploded" not in r.text
    assert "index exploded" in caplog.text
    monkeypatch.undo()
    assert h.say("volume em 30").outcome == VolumeSet(30)


def test_every_turn_records_an_episode(make: Make) -> None:
    h = make(OPEN_CHROME)
    h.say("Abre o Chrome!")
    h.say("qual o sentido da vida")
    newest, older = h.store.episodes(10)
    assert older.episode.utterance == "Abre o Chrome!"
    assert older.episode.decision == "Execute"
    assert older.episode.outcome == "AppOpened"
    assert older.episode.intent_id == "abrir_app"
    assert older.episode.ranking[0].intent_id == "abrir_app"
    assert older.episode.slots == {"app": "Google Chrome"}
    assert newest.episode.decision == "NotUnderstood"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/runtime tests/fakes/test_clock.py tests/support -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sazed.runtime.assistant'` (and `fakes.clock` until created).

- [ ] **Step 3: Implement the extractor registry**

`src/sazed/runtime/extractors.py`:
```python
"""Which extractor fills which slot name."""

from collections.abc import Callable, Mapping, Sequence

from sazed.core.types import Extraction
from sazed.nlu.slots.app import extract_app
from sazed.nlu.slots.mute import extract_mute
from sazed.nlu.slots.percent import extract_percent

SlotExtractor = Callable[[str, Mapping[str, str]], Extraction | None]
"""(normalized utterance, aliases for this slot) -> extraction."""


def build_extractors(app_names: Sequence[str]) -> dict[str, SlotExtractor]:
    names = list(app_names)

    def app(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_app(text, names, aliases)

    def percent(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_percent(text)

    def mute(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_mute(text)

    return {"app": app, "percent": percent, "mudo": mute}
```

- [ ] **Step 4: Implement the assistant (first version)**

`src/sazed/runtime/assistant.py`:
```python
"""The assistant: one utterance in, one Response out. The only place the clock is read."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from random import Random

from sazed.core.context import (
    AliasCandidate,
    AwaitConfirm,
    AwaitSlot,
    DialogueContext,
    LastKind,
    LastTurn,
)
from sazed.core.coppermind import Coppermind, Episode
from sazed.core.decisions import (
    AskSlot,
    Confirm,
    ConfirmReason,
    Decision,
    Execute,
    NotUnderstood,
)
from sazed.core.learning import LearningThresholds
from sazed.core.outcomes import ActionFailed, AppNotFound, Outcome, is_failure
from sazed.core.persona import Prompt, render
from sazed.core.policy import IntentRequirements, Thresholds, decide
from sazed.core.response import Response
from sazed.core.skill import IntentSpec, Skill, SkillContext
from sazed.core.types import (
    Ambiguous,
    Extraction,
    ParseResult,
    Ranking,
    Slots,
    SlotValue,
    Unmatched,
    Utterance,
)
from sazed.nlu.matcher import IntentIndex
from sazed.nlu.normalize import normalize, strip_accents
from sazed.runtime.extractors import SlotExtractor

log = logging.getLogger(__name__)

GENERIC_ACTION = "atender a esse pedido"


@dataclass(frozen=True)
class Settings:
    user_name: str
    thresholds: Thresholds
    learning: LearningThresholds
    context_ttl_seconds: float


@dataclass
class _Turn:
    texts: list[str]
    outcome: Outcome | None = None
    decision: Decision | None = None
    intent_id: str | None = None
    ranking: Ranking = ()
    slots: Mapping[str, Extraction] = field(default_factory=dict)


def _given(slots: Mapping[str, Extraction]) -> dict[str, SlotValue | Unmatched]:
    return {n: v for n, v in slots.items() if not isinstance(v, Ambiguous)}


def _alias_key(alias: str) -> str:
    return strip_accents(normalize(alias))


def _slot_summary(slots: Mapping[str, Extraction]) -> dict[str, str]:
    summary: dict[str, str] = {}
    for name, value in slots.items():
        if isinstance(value, SlotValue):
            summary[name] = str(value.value)
        elif isinstance(value, Unmatched):
            summary[name] = f"?{value.raw}"
        else:
            summary[name] = "|".join(value.candidates)
    return summary


class Assistant:
    def __init__(
        self,
        *,
        skills: Sequence[Skill],
        index: IntentIndex,
        extractors: Mapping[str, SlotExtractor],
        store: Coppermind,
        aliases: Mapping[str, Mapping[str, str]],
        settings: Settings,
        clock: Callable[[], datetime],
        rng: Random,
    ) -> None:
        self._specs: dict[str, tuple[Skill, IntentSpec]] = {
            spec.id: (skill, spec) for skill in skills for spec in skill.intents
        }
        self._index = index
        self._extractors = extractors
        self._store = store
        self._base_aliases = {
            slot: {_alias_key(k): v for k, v in m.items()} for slot, m in aliases.items()
        }
        self._aliases = {slot: dict(m) for slot, m in self._base_aliases.items()}
        self._settings = settings
        self._clock = clock
        self._rng = rng
        self._ctx = DialogueContext()
        self._now = datetime.min
        self._last_episode: int | None = None

    # entry point ---------------------------------------------------------------

    def handle(self, text: str) -> Response:
        self._now = self._clock()
        self._ctx = self._ctx.expire(self._now, self._settings.context_ttl_seconds)
        utterance = Utterance(text=text, normalized=normalize(text), received_at=self._now)
        try:
            turn = self._dispatch(utterance)
        except Exception:
            self._ctx = DialogueContext()
            failure = ActionFailed(action=GENERIC_ACTION)
            episode_id = self._record(utterance, _Turn([], outcome=failure), decision="error")
            log.exception("turn failed (episode %s)", episode_id)
            return Response(self._say(failure), failure, None)
        log.debug("ranking for %r: %s", utterance.normalized, turn.ranking)
        self._last_episode = self._record(utterance, turn)
        return Response(" ".join(turn.texts), turn.outcome, turn.decision)

    def _dispatch(self, u: Utterance) -> _Turn:
        return self._understand(u)

    # understanding ---------------------------------------------------------------

    def _understand(self, u: Utterance) -> _Turn:
        ranking = self._index.rank(u.normalized)
        if not ranking or ranking[0].intent_id not in self._specs:
            return self._not_understood(u, ranking)
        _, spec = self._specs[ranking[0].intent_id]
        slots = self._extract(spec, u.normalized)
        parse = ParseResult(u, ranking, slots, frozenset(spec.required - set(slots)))
        requirements = IntentRequirements(spec.required, spec.requires_confirmation(_given(slots)))
        decision = decide(parse, requirements, self._settings.thresholds)
        turn = self._enact(decision, spec, u)
        turn.ranking, turn.slots = ranking, slots
        return turn

    def _enact(self, decision: Decision, spec: IntentSpec, u: Utterance) -> _Turn:
        if isinstance(decision, Execute):
            turn = self._execute(spec, decision.slots, u)
            if turn.decision is None:
                turn.decision = decision
            return turn
        if isinstance(decision, Confirm):
            return self._confirm(spec, decision, u)
        if isinstance(decision, AskSlot):
            return self._ask(spec, decision, u)
        return self._not_understood(u)

    def _extract(self, spec: IntentSpec, text: str) -> dict[str, Extraction]:
        found: dict[str, Extraction] = {}
        for slot in spec.slots:
            value = self._extractors[slot.name](text, self._aliases.get(slot.name, {}))
            if value is not None:
                found[slot.name] = value
        return found

    # acting --------------------------------------------------------------------

    def _execute(self, spec: IntentSpec, slots: Slots, u: Utterance) -> _Turn:
        skill, _ = self._specs[spec.id]
        try:
            outcome = skill.execute(spec.id, slots, SkillContext(now=self._now))
        except Exception:
            log.exception("skill %s failed executing %s", skill.id, spec.id)
            outcome = ActionFailed(action=spec.describe(slots))
        if isinstance(outcome, AppNotFound):
            last = LastTurn(LastKind.APP_NOT_FOUND, u.normalized, spec.id, slots, outcome.query)
            self._ctx = self._ctx.with_last(last, self._now)
        elif not is_failure(outcome):
            last = LastTurn(LastKind.EXECUTED, u.normalized, spec.id, slots, None)
            self._ctx = self._ctx.with_last(last, self._now)
        return _Turn([self._say(outcome)], outcome=outcome, intent_id=spec.id)

    def _confirm(
        self, spec: IntentSpec, decision: Confirm, u: Utterance, alias: AliasCandidate | None = None
    ) -> _Turn:
        pending = AwaitConfirm(
            spec.id,
            decision.slots,
            u.normalized,
            learn_example=decision.reason is not ConfirmReason.DESTRUCTIVE,
            alias=alias,
        )
        self._ctx = self._ctx.with_pending(pending, self._now)
        text = self._say(decision, acao=spec.describe(decision.slots))
        return _Turn([text], decision=decision, intent_id=spec.id)

    def _ask(self, spec: IntentSpec, decision: AskSlot, u: Utterance) -> _Turn:
        pending = AwaitSlot(
            spec.id, decision.slots, decision.slot, decision.candidates, decision.raw, u.normalized
        )
        self._ctx = self._ctx.with_pending(pending, self._now)
        text = self._say(decision, pergunta=spec.question(decision.slot))
        return _Turn([text], decision=decision, intent_id=spec.id)

    def _not_understood(self, u: Utterance, ranking: Ranking = ()) -> _Turn:
        last = LastTurn(LastKind.NOT_UNDERSTOOD, u.normalized, None, {}, None)
        self._ctx = self._ctx.with_last(last, self._now)
        decision = NotUnderstood()
        return _Turn([self._say(decision)], decision=decision, ranking=ranking)

    # plumbing ------------------------------------------------------------------

    def _say(self, item: Outcome | Decision | Prompt, **extra: str) -> str:
        return render(item, nome=self._settings.user_name, rng=self._rng, extra=extra)

    def _record(self, u: Utterance, turn: _Turn, decision: str | None = None) -> int | None:
        episode = Episode(
            utterance=u.text,
            at=u.received_at,
            ranking=turn.ranking[:5],
            slots=_slot_summary(turn.slots),
            decision=decision or (type(turn.decision).__name__ if turn.decision else "control"),
            intent_id=turn.intent_id,
            outcome=type(turn.outcome).__name__ if turn.outcome is not None else "",
        )
        try:
            return self._store.record_episode(episode)
        except Exception:
            log.exception("could not record the episode")
            return None
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/runtime tests/fakes tests/support -v && uv run ruff check .`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sazed/runtime tests/runtime tests/fakes tests/support
git commit -m "feat(runtime): add assistant turn loop with safe failures and episodes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Assistant — dialogue (confirm, ask, repeat, TTL)

**Files:**
- Modify: `src/sazed/runtime/assistant.py`
- Test: `tests/runtime/test_assistant_dialogue.py`

**Interfaces:**
- Consumes: Task 10's `Assistant`, `parse_control`/`pick_candidate`/`ControlKind` (Task 7), `Reaction` (Task 4).
- Produces: internal methods `_answer(pending, u, control) -> _Turn | None`, `_proceed(intent_id, slots, u, *, alias=None) -> _Turn`, `_resolve_answer(pending: AwaitSlot, u) -> SlotValue | Unmatched | None`, `_cancelled() -> _Turn`, `_react(reaction) -> None`. Task 12 extends `_dispatch`, `_answer` and `_proceed`.

- [ ] **Step 1: Write the failing tests**

`tests/runtime/test_assistant_dialogue.py`:
```python
from collections.abc import Sequence
from datetime import datetime

from support.harness import Make

from sazed.core.coppermind import Reaction
from sazed.core.decisions import AskSlot, Confirm, ConfirmReason, NotUnderstood
from sazed.core.outcomes import AmbiguousSlot, AppOpened, Cancelled, Outcome
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue

LOW_CHROME = {"abre aí o chrome": {"abrir_app": 0.80, "fechar_app": 0.30}}
VOLUME_30 = {"volume em 30": {"volume_definir": 0.97, "volume_aumentar": 0.70}}
OPEN_SOMETHING = {"abre o programa": {"abrir_app": 0.95, "fechar_app": 0.40}}


def test_yes_executes_the_confirmed_command(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    r = h.say("sim")
    assert h.launcher.launched == ["Google Chrome"]
    assert r.outcome == AppOpened("Google Chrome")


def test_yes_marks_the_question_episode_confirmed(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.say("sim")
    question = h.store.episodes(2)[1]
    assert question.episode.reaction is Reaction.CONFIRMED


def test_no_cancels_and_marks_the_question_denied(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    r = h.say("não")
    assert r.outcome == Cancelled()
    assert h.launcher.launched == []
    assert h.store.episodes(2)[1].episode.reaction is Reaction.DENIED


def test_unrelated_reply_drops_pending_and_is_understood(make: Make) -> None:
    h = make({**LOW_CHROME, **VOLUME_30})
    h.say("abre aí o chrome")
    h.say("volume em 30")
    assert h.audio.volume == 30
    assert h.say("sim").decision == NotUnderstood()
    assert h.launcher.launched == []


def test_yes_with_nothing_pending_is_not_understood(make: Make) -> None:
    h = make()
    assert h.say("sim").decision == NotUnderstood()


def test_yes_after_ttl_is_not_understood(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.clock.advance(61)
    assert h.say("sim").decision == NotUnderstood()
    assert h.launcher.launched == []


def test_yes_exactly_at_ttl_is_still_an_answer(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.clock.advance(60)
    h.say("sim")
    assert h.launcher.launched == ["Google Chrome"]


def test_missing_slot_answer_completes_the_command(make: Make) -> None:
    h = make(OPEN_SOMETHING)
    h.say("abre o programa")
    h.say("o spotify")
    assert h.launcher.launched == ["Spotify"]


def test_new_command_instead_of_a_slot_answer_is_handled_as_a_command(make: Make) -> None:
    h = make({**OPEN_SOMETHING, **VOLUME_30})
    h.say("abre o programa")
    h.say("volume em 30")
    assert h.audio.volume == 30
    assert h.launcher.launched == []


def test_yes_to_a_slot_question_is_not_an_app_name(make: Make) -> None:
    h = make(OPEN_SOMETHING)
    h.say("abre o programa")
    assert h.say("sim").decision == NotUnderstood()
    assert h.launcher.launched == []


def test_ambiguous_app_is_chosen_by_ordinal(make: Make) -> None:
    h = make({"abre o code": {"abrir_app": 0.95, "fechar_app": 0.40}})
    r = h.say("abre o code")
    assert "1) Claude Code, 2) Visual Studio Code" in r.text
    h.say("o segundo")
    assert h.launcher.launched == ["Visual Studio Code"]


def test_destructive_close_confirms_then_closes(make: Make) -> None:
    h = make({"fecha o chrome": {"fechar_app": 0.97, "abrir_app": 0.60}}, running={"Google Chrome": 2})
    r = h.say("fecha o chrome")
    assert isinstance(r.decision, Confirm) and r.decision.reason is ConfirmReason.DESTRUCTIVE
    assert h.launcher.closed == []
    h.say("sim")
    assert h.launcher.closed == ["Google Chrome"]


def test_slot_answer_for_a_destructive_close_still_confirms(make: Make) -> None:
    h = make({"fecha o programa": {"fechar_app": 0.95, "abrir_app": 0.4}}, running={"Google Chrome": 2})
    h.say("fecha o programa")
    r = h.say("o chrome")
    assert isinstance(r.decision, Confirm)
    assert h.launcher.closed == []
    h.say("sim")
    assert h.launcher.closed == ["Google Chrome"]


def test_repeat_reruns_the_last_command(make: Make) -> None:
    h = make({"aumenta o volume": {"volume_aumentar": 0.97, "volume_diminuir": 0.6}})
    h.say("aumenta o volume")
    h.say("de novo")
    assert h.audio.volume == 70


def test_repeat_after_ttl_does_not_rerun(make: Make) -> None:
    h = make({"aumenta o volume": {"volume_aumentar": 0.97, "volume_diminuir": 0.6}})
    h.say("aumenta o volume")
    h.clock.advance(61)
    assert h.say("de novo").decision == NotUnderstood()
    assert h.audio.volume == 60


def test_not_found_with_suggestion_asks_and_yes_opens_it(make: Make) -> None:
    h = make({"abre o disc": {"abrir_app": 0.95, "fechar_app": 0.40}})
    r = h.say("abre o disc")
    assert "Discord" in r.text
    h.say("sim")
    assert h.launcher.launched == ["Discord"]


class PickySkill:
    """Returns AmbiguousSlot from execute, as a skill with its own disambiguation would."""

    id = "picky"
    intents: Sequence[IntentSpec] = (
        IntentSpec(
            "escolher",
            ("escolhe um",),
            (SlotSpec("app", False, "Qual deles?"),),
            describe=lambda s: "escolher um programa",
        ),
    )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        app = slots.get("app")
        if isinstance(app, SlotValue):
            return AppOpened(str(app.value))
        return AmbiguousSlot("app", ("Alfa", "Beta"))


def test_ambiguous_outcome_from_a_skill_becomes_a_question(make: Make) -> None:
    h = make({"escolhe um": {"escolher": 0.95}}, extra_skills=[PickySkill()])
    r = h.say("escolhe um")
    assert isinstance(r.decision, AskSlot)
    assert "1) Alfa, 2) Beta" in r.text
    assert h.say("o segundo").outcome == AppOpened("Beta")


def test_context_uses_the_injected_clock_only(make: Make) -> None:
    h = make(LOW_CHROME)
    h.clock.now = datetime(2030, 1, 1, 0, 0)
    h.say("abre aí o chrome")
    h.clock.advance(30)
    h.say("sim")
    assert h.launcher.launched == ["Google Chrome"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/runtime/test_assistant_dialogue.py -v`
Expected: FAIL. "sim" is not understood (no pending answering yet), the ordinal choice launches nothing, and similar.

- [ ] **Step 3: Implement the dialogue**

In `src/sazed/runtime/assistant.py`, extend the existing import blocks with these names (then `uv run ruff check --fix .`):
```python
from sazed.core.context import Pending
from sazed.core.coppermind import Reaction
from sazed.core.outcomes import AmbiguousSlot, Cancelled
from sazed.nlu.control import Control, ControlKind, parse_control, pick_candidate
```

Replace `_dispatch` with:
```python
    def _dispatch(self, u: Utterance) -> _Turn:
        control = parse_control(u.normalized)
        pending = self._ctx.pending
        if pending is not None:
            self._ctx = self._ctx.without_pending()
            answered = self._answer(pending, u, control)
            if answered is not None:
                return answered
        if control is not None:
            last = self._ctx.last
            if (
                control.kind is ControlKind.REPEAT
                and last is not None
                and last.kind is LastKind.EXECUTED
                and last.intent_id is not None
            ):
                return self._proceed(last.intent_id, last.slots, u)
            if control.kind in (ControlKind.CONFIRM, ControlKind.DENY):
                return self._not_understood(u)
        return self._understand(u)
```

Add these methods (in a `# dialogue` section after `_understand`):
```python
    # dialogue ------------------------------------------------------------------

    def _answer(self, pending: Pending, u: Utterance, control: Control | None) -> _Turn | None:
        """Try `u` as the answer to `pending`. None means "not an answer": handle it normally."""
        kind = control.kind if control is not None else None
        if isinstance(pending, AwaitSlot):
            if kind is ControlKind.DENY:
                return self._cancelled()
            if kind is not None:
                return None
            value = self._resolve_answer(pending, u)
            if value is None:
                return None
            alias = None
            if pending.candidates and pending.raw and isinstance(value, SlotValue):
                alias = AliasCandidate(pending.slot, pending.raw, str(value.value))
            slots = {**pending.slots, pending.slot: value}
            return self._proceed(pending.intent_id, slots, u, alias=alias)
        if kind is ControlKind.DENY:
            if isinstance(pending, AwaitConfirm):
                self._react(Reaction.DENIED)
            return self._cancelled()
        if kind is not ControlKind.CONFIRM:
            return None
        if isinstance(pending, AwaitConfirm):
            self._react(Reaction.CONFIRMED)
            _, spec = self._specs[pending.intent_id]
            return self._execute(spec, pending.slots, u)
        return None

    def _resolve_answer(self, pending: AwaitSlot, u: Utterance) -> SlotValue | Unmatched | None:
        if pending.candidates:
            choice = pick_candidate(u.normalized, pending.candidates)
            if choice is None:
                return None
            return SlotValue(pending.slot, choice, pending.raw or u.normalized, 1.0, exact=True)
        aliases = self._aliases.get(pending.slot, {})
        extracted = self._extractors[pending.slot](u.normalized, aliases)
        if isinstance(extracted, SlotValue):
            return extracted
        if isinstance(extracted, Unmatched):
            ranking = self._index.rank(u.normalized)
            looks_like_a_command = (
                bool(ranking) and ranking[0].score >= self._settings.thresholds.t_confirm
            )
            return None if looks_like_a_command else extracted
        return None

    def _proceed(
        self, intent_id: str, slots: Slots, u: Utterance, *, alias: AliasCandidate | None = None
    ) -> _Turn:
        """Continue a command whose intent is already settled (answer, repeat, correction)."""
        _, spec = self._specs[intent_id]
        missing = sorted(spec.required - set(slots))
        if missing:
            return self._ask(spec, AskSlot(intent_id, slots, missing[0], (), ""), u)
        if spec.requires_confirmation(slots):
            decision = Confirm(intent_id, slots, ConfirmReason.DESTRUCTIVE)
            return self._confirm(spec, decision, u, alias=alias)
        turn = self._execute(spec, slots, u)
        if turn.decision is None:
            turn.decision = Execute(intent_id, slots)
        return turn

    def _cancelled(self) -> _Turn:
        outcome = Cancelled()
        return _Turn([self._say(outcome)], outcome=outcome)

    def _react(self, reaction: Reaction) -> None:
        if self._last_episode is None:
            return
        try:
            self._store.set_reaction(self._last_episode, reaction)
        except Exception:
            log.exception("could not record the reaction")
```

In `_execute`, after the `try/except` block and before the `AppNotFound` branch, insert:
```python
        if isinstance(outcome, AmbiguousSlot):
            ask = AskSlot(spec.id, slots, outcome.slot, outcome.candidates, "")
            return self._ask(spec, ask, u)
```
and extend the `AppNotFound` branch so it reads:
```python
        if isinstance(outcome, AppNotFound):
            last = LastTurn(LastKind.APP_NOT_FOUND, u.normalized, spec.id, slots, outcome.query)
            self._ctx = self._ctx.with_last(last, self._now)
            if outcome.suggestion is not None:
                # AppNotFound is specific to the "app" slot, so the slot name is fixed here.
                fixed = {
                    **slots,
                    "app": SlotValue("app", outcome.suggestion, outcome.query, 1.0, exact=True),
                }
                offer = AwaitConfirm(
                    spec.id,
                    fixed,
                    u.normalized,
                    learn_example=False,
                    alias=AliasCandidate("app", outcome.query, outcome.suggestion),
                )
                self._ctx = self._ctx.with_pending(offer, self._now)
```

- [ ] **Step 4: Run all runtime tests**

Run: `uv run pytest tests/runtime -v && uv run ruff check .`
Expected: PASS, including Task 10's tests.

- [ ] **Step 5: Commit**

```bash
git add src/sazed/runtime/assistant.py tests/runtime/test_assistant_dialogue.py
git commit -m "feat(runtime): answer confirmations and slot questions within the TTL" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Assistant — learning signals and forgetting

**Files:**
- Modify: `src/sazed/runtime/assistant.py`
- Test: `tests/runtime/test_assistant_learning.py`

**Interfaces:**
- Consumes: `judge_example`, `Verdict` (Task 4); `NewExample`, `NewAlias`, `LearnedKind` (Task 4); `AwaitLearn` (Task 3).
- Produces: internal `_learn(examples: Sequence[tuple[str, str, str]], aliases: Sequence[AliasCandidate], *, ignore=frozenset(), announce=False, allow_conflict=False) -> tuple[list[str], Outcome | None]` (tuples are `(normalized text, intent_id, origin)`; origins `confirmed`, `corrected`, `offered`), `_forget()`, `_correct(u, last, rest)`. The assistant loads learned examples and aliases from the store at construction.

- [ ] **Step 1: Write the failing tests**

`tests/runtime/test_assistant_learning.py`:
```python
from datetime import datetime

from support.harness import Make
from fakes.index import ScriptedIndex

from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.coppermind import LearnedKind, NewAlias, NewExample, Reaction
from sazed.core.decisions import AskSlot, Confirm, Execute
from sazed.core.outcomes import ExampleLearned, Forgotten, NothingToForget

LOW_CHROME = {"abre aí o chrome": {"abrir_app": 0.80, "fechar_app": 0.30}}
CODE = {"abre o code": {"abrir_app": 0.95, "fechar_app": 0.40}}
T0 = datetime(2026, 10, 14, 11, 0)


def learned(h) -> list[tuple[LearnedKind, str, str]]:  # type: ignore[no-untyped-def]
    return [(i.kind, i.text, i.target) for i in h.store.learned()]


def test_confirmed_command_is_learned_and_executes_next_time(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.say("sim")
    assert learned(h) == [(LearnedKind.EXAMPLE, "abre aí o chrome", "abrir_app")]
    assert isinstance(h.say("abre aí o chrome").decision, Execute)
    assert h.launcher.launched == ["Google Chrome", "Google Chrome"]


def test_destructive_confirmation_teaches_nothing(make: Make) -> None:
    h = make({"fecha o chrome": {"fechar_app": 0.97, "abrir_app": 0.6}}, running={"Google Chrome": 2})
    h.say("fecha o chrome")
    h.say("sim")
    assert learned(h) == []


def test_denied_confirmation_teaches_nothing(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.say("não")
    assert learned(h) == []


def test_conflicting_example_is_asked_before_saving(make: Make) -> None:
    h = make({"fecha aí o chrome": {"fechar_app": 0.88, "abrir_app": 0.86}}, running={"Google Chrome": 1})
    h.say("fecha aí o chrome")
    r = h.say("sim")
    assert h.launcher.closed == ["Google Chrome"]
    assert "fecha aí o chrome" in r.text
    assert learned(h) == []
    r = h.say("sim")
    assert isinstance(r.outcome, ExampleLearned)
    assert learned(h) == [(LearnedKind.EXAMPLE, "fecha aí o chrome", "fechar_app")]


def test_near_duplicate_is_not_saved(make: Make) -> None:
    h = make({"abre o chrome agora": {"abrir_app": 0.98, "fechar_app": 0.95}})
    assert isinstance(h.say("abre o chrome agora").decision, Confirm)
    h.say("sim")
    assert h.launcher.launched == ["Google Chrome"]
    assert learned(h) == []


def test_choosing_an_ambiguous_app_learns_the_alias(make: Make) -> None:
    h = make(CODE)
    h.say("abre o code")
    r = h.say("o segundo")
    assert learned(h) == [(LearnedKind.ALIAS, "code", "Visual Studio Code")]
    assert "'code'" in r.text
    assert isinstance(h.say("abre o code").decision, Execute)
    assert h.launcher.launched == ["Visual Studio Code", "Visual Studio Code"]


def test_naming_the_app_after_not_found_learns_the_alias(make: Make) -> None:
    h = make({"abre o zap": {"abrir_app": 0.95, "fechar_app": 0.40}})
    h.say("abre o zap")
    h.say("é o discord")
    assert h.launcher.launched == ["Discord"]
    assert learned(h) == [(LearnedKind.ALIAS, "zap", "Discord")]
    assert h.store.episodes(2)[1].episode.reaction is Reaction.CORRECTED


def test_accepted_suggestion_learns_the_alias(make: Make) -> None:
    h = make({"abre o disc": {"abrir_app": 0.95, "fechar_app": 0.40}})
    h.say("abre o disc")
    h.say("sim")
    assert learned(h) == [(LearnedKind.ALIAS, "disc", "Discord")]


def test_correction_after_a_wrong_execution_learns_the_right_intent(make: Make) -> None:
    h = make({
        "fecha o chrome": {"abrir_app": 0.93, "fechar_app": 0.80},
        "fechar": {"fechar_app": 0.91, "abrir_app": 0.50},
    })
    h.say("fecha o chrome")
    assert h.launcher.launched == ["Google Chrome"]
    h.say("não, era pra fechar")
    assert h.launcher.closed == ["Google Chrome"]
    assert learned(h) == [(LearnedKind.EXAMPLE, "fecha o chrome", "fechar_app")]
    assert h.store.episodes(2)[1].episode.reaction is Reaction.CORRECTED


def test_correcting_only_the_app_reruns_with_the_new_one(make: Make) -> None:
    h = make({"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60}})
    h.say("abre o chrome")
    h.say("não, era o spotify")
    assert h.launcher.launched == ["Google Chrome", "Spotify"]
    assert learned(h) == []


def test_rephrase_after_not_understood_offers_to_learn(make: Make) -> None:
    h = make({"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60}})
    h.say("chrome por favor abre")
    r = h.say("abre o chrome")
    assert "chrome por favor abre" in r.text
    r = h.say("sim")
    assert isinstance(r.outcome, ExampleLearned)
    assert learned(h) == [(LearnedKind.EXAMPLE, "chrome por favor abre", "abrir_app")]
    assert isinstance(h.say("chrome por favor abre").decision, Execute)
    assert h.launcher.launched == ["Google Chrome", "Google Chrome"]


def test_declined_offer_learns_nothing(make: Make) -> None:
    h = make({"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60}})
    h.say("liga o navegador")
    h.say("abre o chrome")
    h.say("não")
    assert learned(h) == []


def test_forget_removes_the_latest_alias_from_store_and_memory(make: Make) -> None:
    h = make(CODE)
    h.say("abre o code")
    h.say("o segundo")
    r = h.say("esquece isso")
    assert isinstance(r.outcome, Forgotten)
    assert h.store.aliases() == []
    assert isinstance(h.say("abre o code").decision, AskSlot)


def test_forget_removes_a_learned_example_from_the_index(make: Make) -> None:
    h = make(LOW_CHROME)
    h.say("abre aí o chrome")
    h.say("sim")
    h.say("esquece isso")
    assert h.index.learned == []
    assert isinstance(h.say("abre aí o chrome").decision, Confirm)


def test_forget_with_nothing_learned(make: Make) -> None:
    assert make().say("esquece isso").outcome == NothingToForget()


def test_learned_state_is_loaded_at_startup(make: Make) -> None:
    store = SqliteCoppermind(":memory:")
    vector = ScriptedIndex().vectorize("liga o navegador")
    store.learn(
        [NewExample("liga o navegador", "abrir_app", vector, "confirmed")],
        [NewAlias("app", "zap", "Discord")],
        T0,
    )
    h = make({"abre o zap": {"abrir_app": 0.95, "fechar_app": 0.4}}, store=store)
    assert h.index.learned == [("abrir_app", "liga o navegador")]
    h.say("abre o zap")
    assert h.launcher.launched == ["Discord"]


def test_forgetting_a_learned_alias_restores_the_configured_one(make: Make) -> None:
    store = SqliteCoppermind(":memory:")
    store.learn([], [NewAlias("app", "code", "Visual Studio Code")], T0)
    h = make(CODE, aliases={"code": "Claude Code"}, store=store)
    h.say("abre o code")
    h.say("esquece isso")
    h.say("abre o code")
    assert h.launcher.launched == ["Visual Studio Code", "Claude Code"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/runtime/test_assistant_learning.py -v`
Expected: FAIL. Nothing is learned yet, so `learned(h) == []` where an item is expected, and "esquece isso" is not understood.

- [ ] **Step 3: Implement learning**

Extend the existing import blocks with these names (then `uv run ruff check --fix .` sorts them):
```python
from sazed.core.context import AwaitLearn
from sazed.core.coppermind import LearnedItem, LearnedKind, NewAlias, NewExample
from sazed.core.learning import Verdict, judge_example
from sazed.core.outcomes import (
    AliasLearned,
    AlreadyKnown,
    ExampleLearned,
    Forgotten,
    NothingToForget,
)
```

At the end of `__init__`, load what was learned before:
```python
        for example in store.examples():
            index.add(example.intent_id, example.text, example.embedding)
        for alias in store.aliases():
            self._aliases.setdefault(alias.slot, {})[_alias_key(alias.alias)] = alias.value
```

Replace `_dispatch` with the final version:
```python
    def _dispatch(self, u: Utterance) -> _Turn:
        control = parse_control(u.normalized)
        pending = self._ctx.pending
        if pending is not None:
            self._ctx = self._ctx.without_pending()
            answered = self._answer(pending, u, control)
            if answered is not None:
                return answered
        if control is not None:
            last = self._ctx.last
            if control.kind is ControlKind.FORGET:
                return self._forget()
            if (
                control.kind is ControlKind.REPEAT
                and last is not None
                and last.kind is LastKind.EXECUTED
                and last.intent_id is not None
            ):
                return self._proceed(last.intent_id, last.slots, u)
            if control.kind is ControlKind.CORRECT and last is not None:
                return self._correct(u, last, control.rest)
            if control.kind in (ControlKind.CONFIRM, ControlKind.DENY):
                return self._not_understood(u)
        return self._understand(u)
```

In `_enact`, replace the `Execute` branch with (offer to learn after a rephrase):
```python
        if isinstance(decision, Execute):
            previous = self._ctx.last
            turn = self._execute(spec, decision.slots, u)
            if turn.decision is None:
                turn.decision = decision
            rephrased = previous is not None and previous.kind is LastKind.NOT_UNDERSTOOD
            if (
                rephrased
                and previous is not None
                and isinstance(turn.decision, Execute)
                and not is_failure(turn.outcome)
                and self._ctx.pending is None
            ):
                self._ctx = self._ctx.with_pending(AwaitLearn(previous.utterance, spec.id), self._now)
                turn.texts.append(self._say(Prompt.OFFER_LEARN, original=previous.utterance))
            return turn
```

In `_answer`, replace the final `AwaitConfirm` block and the trailing `return None` with:
```python
        if isinstance(pending, AwaitConfirm):
            self._react(Reaction.CONFIRMED)
            _, spec = self._specs[pending.intent_id]
            turn = self._execute(spec, pending.slots, u)
            if not is_failure(turn.outcome):
                examples = [(pending.utterance, spec.id, "confirmed")] if pending.learn_example else []
                aliases = [pending.alias] if pending.alias is not None else []
                texts, _ = self._learn(examples, aliases)
                turn.texts.extend(texts)
            return turn
        texts, outcome = self._learn(
            [(pending.text, pending.intent_id, "offered")], [], announce=True, allow_conflict=True
        )
        return _Turn(texts, outcome=outcome)
```

In `_proceed`, before the final `return turn`, add:
```python
        if alias is not None and not is_failure(turn.outcome):
            texts, _ = self._learn([], [alias])
            turn.texts.extend(texts)
```

Add the learning section:
```python
    # learning ------------------------------------------------------------------

    def _learn(
        self,
        examples: Sequence[tuple[str, str, str]],
        aliases: Sequence[AliasCandidate],
        *,
        ignore: frozenset[str] = frozenset(),
        announce: bool = False,
        allow_conflict: bool = False,
    ) -> tuple[list[str], Outcome | None]:
        """Validate every candidate, then write all of them in one store transaction."""
        texts: list[str] = []
        outcome: Outcome | None = None
        new_examples: list[NewExample] = []
        for text, intent_id, origin in examples:
            scores = self._index.scores(text)
            verdict = judge_example(scores, intent_id, self._settings.learning, ignore)
            if verdict is Verdict.DUPLICATE:
                if announce:
                    outcome = AlreadyKnown()
                    texts.append(self._say(outcome))
                continue
            if verdict is Verdict.CONFLICT and not allow_conflict:
                _, spec = self._specs[intent_id]
                self._ctx = self._ctx.with_pending(AwaitLearn(text, intent_id), self._now)
                texts.append(self._say(Prompt.CONFLICT_ASK, texto=text, acao=spec.describe({})))
                continue
            new_examples.append(NewExample(text, intent_id, self._index.vectorize(text), origin))
        new_aliases = [
            NewAlias(a.slot, a.alias, a.value)
            for a in aliases
            if self._aliases.get(a.slot, {}).get(_alias_key(a.alias)) != a.value
        ]
        if new_examples or new_aliases:
            self._store.learn(new_examples, new_aliases, self._now)
            for ex in new_examples:
                self._index.add(ex.intent_id, ex.text, ex.embedding)
            for al in new_aliases:
                self._aliases.setdefault(al.slot, {})[_alias_key(al.alias)] = al.value
        if announce and new_examples:
            outcome = ExampleLearned(new_examples[0].text)
            texts.append(self._say(outcome))
        for al in new_aliases:
            outcome = AliasLearned(al.alias, al.value)
            texts.append(self._say(outcome))
        return texts, outcome

    def _forget(self) -> _Turn:
        items = self._store.forget_latest()
        if not items:
            nothing = NothingToForget()
            return _Turn([self._say(nothing)], outcome=nothing)
        for item in items:
            if item.kind is LearnedKind.EXAMPLE:
                self._index.remove(item.target, item.text)
            else:
                self._unlearn_alias(item.slot or "", item.text)
        outcome = Forgotten(_describe_learned(items))
        return _Turn([self._say(outcome)], outcome=outcome)

    def _unlearn_alias(self, slot: str, alias: str) -> None:
        key = _alias_key(alias)
        configured = self._base_aliases.get(slot, {}).get(key)
        current = self._aliases.setdefault(slot, {})
        if configured is None:
            current.pop(key, None)
        else:
            current[key] = configured

    def _correct(self, u: Utterance, last: LastTurn, rest: str) -> _Turn:
        rest_norm = normalize(rest)
        if last.kind is LastKind.APP_NOT_FOUND and last.intent_id is not None and last.raw_query:
            _, spec = self._specs[last.intent_id]
            found = self._extractors["app"](rest_norm, self._aliases.get("app", {}))
            if found is None:
                return self._not_understood(u)
            self._react(Reaction.CORRECTED)
            if isinstance(found, Ambiguous):
                ask = AskSlot(spec.id, last.slots, "app", found.candidates, last.raw_query)
                return self._ask(spec, ask, u)
            alias = None
            if isinstance(found, SlotValue):
                alias = AliasCandidate("app", last.raw_query, str(found.value))
            return self._proceed(spec.id, {**last.slots, "app": found}, u, alias=alias)

        if last.kind is LastKind.EXECUTED and last.intent_id is not None:
            ranking = self._index.rank(rest_norm)
            top = ranking[0] if ranking else None
            if (
                top is None
                or top.score < self._settings.thresholds.t_confirm
                or top.intent_id == last.intent_id
                or top.intent_id not in self._specs
            ):
                # Same intent: the user is correcting a slot ("não, era o spotify").
                _, spec = self._specs[last.intent_id]
                fixed = {
                    n: v for n, v in self._extract(spec, rest_norm).items()
                    if isinstance(v, SlotValue)
                }
                if not fixed:
                    return self._not_understood(u)
                self._react(Reaction.CORRECTED)
                return self._proceed(spec.id, {**last.slots, **fixed}, u)
            # Another intent: the last command misfired. Learn the original phrase for the
            # right intent; resembling the misfired intent is expected, so it is ignored.
            _, spec = self._specs[top.intent_id]
            carried = {n: v for n, v in last.slots.items() if n in spec.slot_names}
            fresh = _given(self._extract(spec, rest_norm))
            self._react(Reaction.CORRECTED)
            turn = self._proceed(spec.id, {**carried, **fresh}, u)
            texts, _ = self._learn(
                [(last.utterance, spec.id, "corrected")], [], ignore=frozenset({last.intent_id})
            )
            turn.texts.extend(texts)
            return turn

        return self._understand(Utterance(rest, rest_norm, u.received_at))
```

Add the module-level helper next to `_slot_summary`:
```python
def _describe_learned(items: Sequence[LearnedItem]) -> str:
    parts = [
        f"'{i.text}' como {i.target}" if i.kind is LearnedKind.ALIAS else f"'{i.text}'"
        for i in items
    ]
    return " e ".join(parts)
```

- [ ] **Step 4: Run every runtime test**

Run: `uv run pytest tests/runtime -v && uv run ruff check .`
Expected: PASS (Tasks 10, 11 and 12). The `test_choosing_an_ambiguous_app_learns_the_alias` text assertion is loose on purpose, because `AliasLearned` has two variants and the rng picks one.

- [ ] **Step 5: Prove forgetting discriminates**

Mutation (the realistic bug: forgetting only on disk): in `_forget`, delete the `for item in items:` loop.
Run: `uv run pytest tests/runtime/test_assistant_learning.py -v -k forget`
Expected: `test_forget_removes_the_latest_alias_from_store_and_memory` and `test_forget_removes_a_learned_example_from_the_index` FAIL. The store is empty, but memory still holds the item, so `abre o code` executes. Paste the output under `## Forget`. Revert and re-run.

- [ ] **Step 6: Commit**

```bash
git add src/sazed/runtime/assistant.py tests/runtime/test_assistant_learning.py docs/superpowers/proofs
git commit -m "feat(runtime): learn from confirmations, corrections and choices; forget on request" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 13: Configuration, wiring, and persistence end to end

**Files:**
- Create: `src/sazed/runtime/config.py`, `src/sazed/runtime/wiring.py`, `config.example.toml`
- Test: `tests/runtime/test_config.py`, `tests/runtime/test_wiring.py`

**Interfaces:**
- Consumes: `Assistant`, `Settings`, `build_extractors` (Task 10), `IntentMatcher` (Task 6), `SqliteCoppermind` (Task 9), skills (Task 8).
- Produces:
  - `Config` (pydantic, `extra="forbid"`) with sections `user.name`, `nlu.{t_exec,t_confirm,g_min}`, `learning.{t_conflict,t_dup}`, `dialogue.context_ttl_seconds`, `model.embedder_path`, `data.dir`, `logging.debug`, and `aliases: dict[str, str]`; `load_config(path: Path) -> Config` (a missing file gives defaults); `ConfigError(Exception)` whose `str()` is a pt-BR message ready to print; `DEFAULT_CONFIG_PATH`
  - `SazedApp(assistant, store, index, skills, config, rng)` with `.greeting() -> str`, `.farewell() -> str`, `.close()`; `settings_from(config) -> Settings`; `build_app(config, *, embedder, catalog, launcher, audio, clock=None, rng=None) -> SazedApp`

- [ ] **Step 1: Write the failing config tests**

`tests/runtime/test_config.py`:
```python
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel

from sazed.runtime.config import Config, ConfigError, load_config

ROOT = Path(__file__).resolve().parents[2]
ENGLISH_MARKERS = ("Input should", "Field required", "Value error", "Extra inputs", "should be")


def leaf_paths(model: type[BaseModel], prefix: tuple[str, ...] = ()) -> Iterator[tuple[str, ...]]:
    for name, field in model.model_fields.items():
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            yield from leaf_paths(annotation, (*prefix, name))
        else:
            yield (*prefix, name)


LEAVES = list(leaf_paths(Config))


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def toml_setting(path: tuple[str, ...], value: str) -> str:
    if len(path) == 1:
        return f"{path[0]} = {value}\n"
    return f"[{path[0]}]\n{path[1]} = {value}\n"


def test_leaf_walk_finds_nested_fields() -> None:
    assert ("nlu", "t_exec") in LEAVES and ("aliases",) in LEAVES


@pytest.mark.parametrize("path", LEAVES, ids=".".join)
def test_wrong_type_in_any_field_gets_a_pt_br_message(tmp_path: Path, path: tuple[str, ...]) -> None:
    with pytest.raises(ConfigError) as caught:
        load_config(write(tmp_path, toml_setting(path, "[1, 2]")))
    message = str(caught.value)
    assert ".".join(path) in message
    assert not any(marker in message for marker in ENGLISH_MARKERS), message


def test_out_of_range_threshold(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        load_config(write(tmp_path, "[nlu]\nt_exec = 1.5\n"))
    assert "nlu.t_exec: deve ser no máximo 1" in str(caught.value)


def test_confirm_threshold_above_exec_threshold_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        load_config(write(tmp_path, "[nlu]\nt_exec = 0.8\nt_confirm = 0.9\n"))
    assert "t_confirm não pode ser maior que t_exec" in str(caught.value)


def test_unknown_key_is_rejected_in_pt_br(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        load_config(write(tmp_path, "[user]\nnome = 'Artur'\n"))
    assert "user.nome: não é uma chave reconhecida" in str(caught.value)


def test_malformed_toml_is_reported_in_pt_br(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        load_config(write(tmp_path, "[user\nname = \n"))
    assert "TOML" in str(caught.value)
    assert not any(marker in str(caught.value) for marker in ENGLISH_MARKERS)


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_config(tmp_path / "absent.toml") == Config()


def test_valid_file_is_read(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, "[user]\nname = 'Kelsier'\n[aliases]\nzap = 'WhatsApp'\n"))
    assert config.user.name == "Kelsier"
    assert config.aliases == {"zap": "WhatsApp"}


def test_example_config_documents_the_real_defaults() -> None:
    assert load_config(ROOT / "config.example.toml") == Config()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/runtime/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sazed.runtime.config'`.

- [ ] **Step 3: Implement the configuration**

`src/sazed/runtime/config.py`:
```python
"""config.toml, validated at startup. Every message a person can see is pt-BR."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "multilingual-e5-small"


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "Sazed" if base else Path.home() / ".sazed"


DEFAULT_CONFIG_PATH = default_data_dir() / "config.toml"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserConfig(_Section):
    name: str = Field("Artur", min_length=1)


class NluConfig(_Section):
    # Placeholders until Task 17 tunes them against the NLU fixture.
    t_exec: float = Field(0.90, ge=0, le=1)
    t_confirm: float = Field(0.84, ge=0, le=1)
    g_min: float = Field(0.02, ge=0, le=1)

    @model_validator(mode="after")
    def _confirm_below_exec(self) -> NluConfig:
        if self.t_confirm > self.t_exec:
            raise ValueError("t_confirm não pode ser maior que t_exec")
        return self


class LearningConfig(_Section):
    t_conflict: float = Field(0.92, ge=0, le=1)
    t_dup: float = Field(0.97, ge=0, le=1)


class DialogueConfig(_Section):
    context_ttl_seconds: float = Field(60.0, gt=0)


class ModelConfig(_Section):
    embedder_path: Path = DEFAULT_MODEL_DIR


class DataConfig(_Section):
    dir: Path = Field(default_factory=default_data_dir)


class LoggingConfig(_Section):
    debug: bool = False


class Config(_Section):
    user: UserConfig = Field(default_factory=UserConfig)
    nlu: NluConfig = Field(default_factory=NluConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    dialogue: DialogueConfig = Field(default_factory=DialogueConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    aliases: dict[str, str] = Field(default_factory=dict)


class ConfigError(Exception):
    """Startup must stop. `str(error)` is a pt-BR message meant for the user."""


_MESSAGES = {
    "float_parsing": "deve ser um número",
    "float_type": "deve ser um número",
    "greater_than_equal": "deve ser no mínimo {ge}",
    "less_than_equal": "deve ser no máximo {le}",
    "greater_than": "deve ser maior que {gt}",
    "string_too_short": "não pode ficar vazio",
    "string_type": "deve ser um texto",
    "bool_parsing": "deve ser verdadeiro ou falso (true/false)",
    "bool_type": "deve ser verdadeiro ou falso (true/false)",
    "extra_forbidden": "não é uma chave reconhecida",
    "path_type": "deve ser um caminho",
    "dict_type": "deve ser uma tabela",
    "model_type": "deve ser uma seção [tabela]",
    "model_attributes_type": "deve ser uma seção [tabela]",
}
_FALLBACK = "valor inválido"


def _message(error: Any) -> str:
    context = error.get("ctx", {})
    if error["type"] == "value_error":
        return str(context.get("error", _FALLBACK))
    return _MESSAGES.get(error["type"], _FALLBACK).format(**context)


def _describe(err: ValidationError) -> list[str]:
    lines = []
    for error in err.errors():
        where = ".".join(str(part) for part in error["loc"]) or "arquivo"
        lines.append(f"- {where}: {_message(error)}")
    return lines


def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        raise ConfigError(
            f"Não consegui ler {path}: o arquivo não está em formato TOML válido."
        ) from None
    try:
        return Config.model_validate(data)
    except ValidationError as err:
        raise ConfigError(
            "\n".join([f"Configuração inválida em {path}:", *_describe(err)])
        ) from None
```

`config.example.toml` (it must equal the defaults; a test enforces this):
```toml
# Copy to %LOCALAPPDATA%\Sazed\config.toml and edit.
# Every value below is the default; the test suite checks that this file stays true.

[user]
name = "Artur"

[nlu]
# Tuned against tests/fixtures/nlu_cases.toml (scripts/tune_thresholds.py).
t_exec = 0.90
t_confirm = 0.84
g_min = 0.02

[learning]
t_conflict = 0.92
t_dup = 0.97

[dialogue]
context_ttl_seconds = 60.0

[logging]
debug = false

# [model]
# embedder_path = "C:/caminho/para/models/multilingual-e5-small"
# [data]
# dir = "C:/Users/<você>/AppData/Local/Sazed"

[aliases]
# zap = "WhatsApp"
```

Run: `uv run pytest tests/runtime/test_config.py -v`
Expected: PASS. If a field's wrong-type error has a pydantic type missing from `_MESSAGES`, the message falls back to "valor inválido" and still passes. Add the specific pt-BR message anyway.

- [ ] **Step 4: Write the failing wiring tests**

`tests/runtime/test_wiring.py`:
```python
from pathlib import Path
from random import Random

from fakes.clock import ManualClock
from fakes.embedder import HashingEmbedder
from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher

from sazed.core.decisions import Confirm, Execute
from sazed.runtime.config import Config, DataConfig, LearningConfig, NluConfig
from sazed.runtime.wiring import SazedApp, build_app, settings_from


def boot(config: Config) -> SazedApp:
    return build_app(
        config,
        embedder=HashingEmbedder(),
        catalog=FakeCatalog(["Google Chrome"]),
        launcher=FakeLauncher(),
        audio=FakeAudio(),
        clock=ManualClock(),
        rng=Random(0),
    )


def test_settings_follow_the_config() -> None:
    config = Config()
    settings = settings_from(config)
    assert settings.user_name == config.user.name
    assert settings.thresholds.t_exec == config.nlu.t_exec
    assert settings.thresholds.t_confirm == config.nlu.t_confirm
    assert settings.thresholds.g_min == config.nlu.g_min
    assert settings.learning.t_conflict == config.learning.t_conflict
    assert settings.learning.t_dup == config.learning.t_dup
    assert settings.context_ttl_seconds == config.dialogue.context_ttl_seconds


def test_learning_persists_across_restarts_and_changes_the_decision(tmp_path: Path) -> None:
    # Thresholds chosen so only an exact (learned) example executes: everything else confirms.
    config = Config(
        data=DataConfig(dir=tmp_path),
        nlu=NluConfig(t_exec=0.999, t_confirm=0.0, g_min=0.0),
        learning=LearningConfig(t_conflict=1.0, t_dup=0.999),
    )
    app = boot(config)
    first = app.assistant.handle("abre o chrome agora")
    assert isinstance(first.decision, Confirm)
    assert first.decision.intent_id == "abrir_app"
    app.assistant.handle("sim")
    app.close()

    restarted = boot(config)
    again = restarted.assistant.handle("abre o chrome agora")
    assert isinstance(again.decision, Execute)
    assert (tmp_path / "coppermind.db").exists()


def test_greeting_addresses_the_configured_user(tmp_path: Path) -> None:
    app = boot(Config(data=DataConfig(dir=tmp_path)))
    assert app.farewell() == "Até logo, Mestre Artur."
    assert "Mestre Artur" in app.greeting()
```

- [ ] **Step 5: Run to verify failure**

Run: `uv run pytest tests/runtime/test_wiring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sazed.runtime.wiring'`.

- [ ] **Step 6: Implement the wiring**

`src/sazed/runtime/wiring.py`:
```python
"""Build the application from a Config. The only place adapters are chosen."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from random import Random

from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.learning import LearningThresholds
from sazed.core.persona import Prompt, render
from sazed.core.policy import Thresholds
from sazed.core.skill import Skill
from sazed.nlu.embedder import Embedder
from sazed.nlu.matcher import IntentMatcher
from sazed.runtime.assistant import Assistant, Settings
from sazed.runtime.config import Config
from sazed.runtime.extractors import build_extractors
from sazed.skills.pc.apps import AppCatalog, AppLauncher, AppsSkill
from sazed.skills.pc.volume import AudioControl, VolumeSkill


@dataclass
class SazedApp:
    assistant: Assistant
    store: SqliteCoppermind
    index: IntentMatcher
    skills: Sequence[Skill]
    config: Config
    rng: Random
    clock: Callable[[], datetime]

    def greeting(self) -> str:
        return render(Prompt.GREETING, nome=self.config.user.name, rng=self.rng)

    def farewell(self) -> str:
        return render(Prompt.FAREWELL, nome=self.config.user.name, rng=self.rng)

    def close(self) -> None:
        self.store.close()


def settings_from(config: Config) -> Settings:
    return Settings(
        user_name=config.user.name,
        thresholds=Thresholds(config.nlu.t_exec, config.nlu.t_confirm, config.nlu.g_min),
        learning=LearningThresholds(config.learning.t_conflict, config.learning.t_dup),
        context_ttl_seconds=config.dialogue.context_ttl_seconds,
    )


def build_app(
    config: Config,
    *,
    embedder: Embedder,
    catalog: AppCatalog,
    launcher: AppLauncher,
    audio: AudioControl,
    clock: Callable[[], datetime] | None = None,
    rng: Random | None = None,
) -> SazedApp:
    clock = clock or datetime.now
    rng = rng or Random()
    store = SqliteCoppermind(config.data.dir / "coppermind.db")
    skills: list[Skill] = [AppsSkill(catalog, launcher), VolumeSkill(audio)]
    index = IntentMatcher(embedder)
    for skill in skills:
        for spec in skill.intents:
            index.add_examples(spec.id, spec.examples)
    names = [entry.name for entry in catalog.entries()]
    assistant = Assistant(
        skills=skills,
        index=index,
        extractors=build_extractors(names),
        store=store,
        aliases={"app": config.aliases},
        settings=settings_from(config),
        clock=clock,
        rng=rng,
    )
    return SazedApp(assistant, store, index, skills, config, rng, clock)
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/runtime -v && uv run ruff check .`
Expected: PASS. If `first.decision.intent_id` is `fechar_app` with the hashing fake, the fake's trigram overlap misled it. Rephrase the test utterance to another seed-plus-one-word ("abre o chrome pra mim"), and do not loosen the assertion.

- [ ] **Step 8: Commit**

```bash
git add src/sazed/runtime/config.py src/sazed/runtime/wiring.py config.example.toml tests/runtime/test_config.py tests/runtime/test_wiring.py
git commit -m "feat(runtime): add validated pt-BR config and application wiring" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: ONNX embedder and the one-time model download

**Files:**
- Create: `scripts/fetch_model.py`, `scripts/measure_embedder.py`, `src/sazed/adapters/onnx/__init__.py`, `src/sazed/adapters/onnx/embedder.py`
- Test: `tests/adapters/test_onnx_embedder.py` (`@pytest.mark.model`)
- Modify: `CLAUDE.md` (measured figures)

**Interfaces:**
- Consumes: the `Embedder` protocol (Task 6).
- Produces: `OnnxEmbedder(model_dir: Path, *, max_length: int = 128, threads: int = 0)` implementing `Embedder` (dim 384); `QUERY_PREFIX = "query: "`. Files expected in `model_dir`: `model.onnx`, `tokenizer.json`.

- [ ] **Step 1: Write the download script and run it** (network is used here and nowhere else)

`scripts/fetch_model.py`:
```python
"""Download intfloat/multilingual-e5-small (ONNX + tokenizer) once.

This is the only code in Sazed that touches the network. After it runs, everything is offline.
Usage: uv run python scripts/fetch_model.py [--variant qint8|fp32]
"""

import argparse
import urllib.request
from pathlib import Path

REPO = "https://huggingface.co/intfloat/multilingual-e5-small/resolve/main"
VARIANTS = {
    "qint8": "onnx/model_qint8_avx512_vnni.onnx",  # ~118 MB, needs AVX-512 VNNI for speed
    "fp32": "onnx/model.onnx",  # ~470 MB
}
TARGET = Path(__file__).resolve().parents[1] / "models" / "multilingual-e5-small"


def fetch(url: str, dest: Path) -> None:
    partial = dest.with_name(dest.name + ".part")
    urllib.request.urlretrieve(url, partial)
    partial.replace(dest)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="qint8")
    parser.add_argument("--dir", type=Path, default=TARGET)
    args = parser.parse_args(argv)
    args.dir.mkdir(parents=True, exist_ok=True)
    fetch(f"{REPO}/tokenizer.json", args.dir / "tokenizer.json")
    fetch(f"{REPO}/{VARIANTS[args.variant]}", args.dir / "model.onnx")
    (args.dir / "VARIANT").write_text(args.variant, encoding="utf-8")
    for file in sorted(args.dir.iterdir()):
        print(f"{file.name}: {file.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
```

Run: `uv run python scripts/fetch_model.py`
Expected output (sizes from Hugging Face, checked 2026-10-14):
```
VARIANT: 0.0 MB
model.onnx: 118.3 MB
tokenizer.json: 17.1 MB
```

- [ ] **Step 2: Write the failing adapter tests**

`tests/adapters/test_onnx_embedder.py`:
```python
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


def test_padding_does_not_change_a_sentence_vector(embedder: OnnxEmbedder) -> None:
    alone = embedder.embed(["abre o chrome"])[0]
    batched = embedder.embed(["abre o chrome", "uma frase bem mais longa para forçar padding no lote"])[0]
    assert np.allclose(alone, batched, atol=1e-4)


def test_paraphrase_is_closer_than_another_intent(embedder: OnnxEmbedder) -> None:
    base, para, other = embedder.embed(["abre o chrome", "abra o google chrome", "aumenta o volume"])
    assert float(base @ para) > float(base @ other)


def test_empty_batch(embedder: OnnxEmbedder) -> None:
    assert embedder.embed([]).shape == (0, 384)
```

Run: `uv run pytest -m model tests/adapters/test_onnx_embedder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sazed.adapters.onnx'`.

- [ ] **Step 3: Implement the adapter**

`src/sazed/adapters/onnx/__init__.py`:
```python
"""ONNX Runtime adapters."""
```

`src/sazed/adapters/onnx/embedder.py`:
```python
"""multilingual-e5-small on onnxruntime (CPU). Mean pooling over the attention mask, then L2.

e5 expects a prefix. Commands and examples are compared symmetrically, so both sides use
"query: " (the e5 recommendation for non-retrieval similarity). Apply it here only.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
import onnxruntime as ort
from tokenizers import Tokenizer

QUERY_PREFIX = "query: "


class OnnxEmbedder:
    def __init__(self, model_dir: Path, *, max_length: int = 128, threads: int = 0) -> None:
        tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=max_length)
        pad_id = tokenizer.token_to_id("<pad>")
        tokenizer.enable_padding(pad_id=pad_id, pad_token="<pad>")
        self._tokenizer = tokenizer
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        self._session = ort.InferenceSession(
            str(model_dir / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._inputs = {i.name for i in self._session.get_inputs()}
        self._dim = int(self._run(["dimensão"]).shape[1])

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> npt.NDArray[np.float32]:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        return self._run(texts)

    def _run(self, texts: Sequence[str]) -> npt.NDArray[np.float32]:
        encodings = self._tokenizer.encode_batch([QUERY_PREFIX + t for t in texts])
        ids = np.array([e.ids for e in encodings], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self._session.run(None, feed)[0]
        weights = mask[..., np.newaxis].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        pooled /= np.linalg.norm(pooled, axis=1, keepdims=True)
        return pooled.astype(np.float32)
```

- [ ] **Step 4: Run the model tests**

Run: `uv run pytest -m model tests/adapters/test_onnx_embedder.py -v`
Expected: PASS.

- [ ] **Step 5: Prove the padding test discriminates**

Mutation (the classic pooling bug): replace the pooled line with `pooled = hidden.mean(axis=1)`.
Run the same command. Expected: `test_padding_does_not_change_a_sentence_vector` FAILS. Paste it under `## Mask-aware pooling`. Revert, re-run, and expect PASS.

- [ ] **Step 6: Measure on this machine** (spec §9 and §12)

The script below uses `DryRunPorts` from `sazed.runtime.evaluation`, which Task 17 creates.
In this task, write the script and run it with a temporary inline stand-in, or defer
running it until Task 17 Step 3. Either way, record the numbers before Task 17 is committed.

`scripts/measure_embedder.py`:
```python
"""Measure the embedder's RAM and latency on this machine. Usage: uv run python scripts/measure_embedder.py"""

import statistics
import time

import psutil

from sazed.adapters.onnx.embedder import OnnxEmbedder
from sazed.runtime.config import DEFAULT_MODEL_DIR
from sazed.runtime.evaluation import DryRunPorts
from sazed.skills.pc.apps import AppsSkill
from sazed.skills.pc.volume import VolumeSkill


def main() -> None:
    process = psutil.Process()
    before = process.memory_info().rss
    started = time.perf_counter()
    embedder = OnnxEmbedder(DEFAULT_MODEL_DIR)
    load_s = time.perf_counter() - started
    after_load = process.memory_info().rss

    ports = DryRunPorts([])
    skills = (AppsSkill(ports, ports), VolumeSkill(ports))
    seeds = [e for skill in skills for spec in skill.intents for e in spec.examples]
    started = time.perf_counter()
    embedder.embed(seeds)
    seeds_s = time.perf_counter() - started

    timings = []
    for _ in range(200):
        started = time.perf_counter()
        embedder.embed(["abre o google chrome pra mim"])
        timings.append((time.perf_counter() - started) * 1000)
    variant = (DEFAULT_MODEL_DIR / "VARIANT").read_text(encoding="utf-8").strip()
    print(f"variant: {variant}")
    total_mb = process.memory_info().rss / 1e6
    print(f"load: {load_s:.2f} s, RSS +{(after_load - before) / 1e6:.0f} MB, total {total_mb:.0f} MB")
    print(f"{len(seeds)} seed examples: {seeds_s * 1000:.0f} ms")
    print(f"single sentence: median {statistics.median(timings):.1f} ms, p95 {sorted(timings)[189]:.1f} ms")


if __name__ == "__main__":
    main()
```

Run: `uv run python scripts/measure_embedder.py`
Expected: real numbers. Spec expectations are ~200 MB RAM, a few ms per sentence, and seeds under 1 s. Add them to root `CLAUDE.md` under a new `## Measurements` heading with the date, the variant, and the exact output. If seeds take over 1 s, report it. The spec says a cache comes only after measurement; do not add one in this task.

- [ ] **Step 7: Commit**

```bash
git add scripts/fetch_model.py scripts/measure_embedder.py src/sazed/adapters/onnx tests/adapters/test_onnx_embedder.py CLAUDE.md docs/superpowers/proofs
git commit -m "feat(onnx): add e5-small embedder with mask-aware pooling" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Windows adapters — app catalog, launcher, audio

**Files:**
- Create: `src/sazed/adapters/windows/__init__.py`, `catalog.py`, `launcher.py`, `audio.py`, `src/sazed/adapters/CLAUDE.md`
- Test: `tests/adapters/test_windows_pure.py`, `tests/adapters/test_windows_integration.py` (`@pytest.mark.windows`)

**Interfaces:**
- Consumes: `AppEntry`, `AppCatalog`, `AppLauncher` (Task 8), `AudioControl` (Task 8).
- Produces: `build_entries(shortcuts: Iterable[tuple[str, str, str]]) -> list[AppEntry]` (pure); `StartMenuCatalog(dirs: Sequence[Path] | None = None)`; `root_pids(processes: Iterable[tuple[int, int, str | None]], target: str) -> list[int]` (pure); `WindowsLauncher()`; `PycawAudio()` with `get_volume`, `set_volume`, `set_muted`, `is_muted`.

- [ ] **Step 1: Write the failing pure tests**

`tests/adapters/test_windows_pure.py`:
```python
from sazed.adapters.windows.catalog import build_entries
from sazed.adapters.windows.launcher import root_pids
from sazed.skills.pc.apps import AppEntry


def test_build_entries_drops_uninstallers_docs_and_non_executables() -> None:
    entries = build_entries([
        ("Spotify", r"C:\Apps\Spotify.exe", r"C:\Start\Spotify.lnk"),
        ("Desinstalar Spotify", r"C:\Apps\unins000.exe", r"C:\Start\u.lnk"),
        ("Uninstall Steam", r"C:\Steam\uninstall.exe", r"C:\Start\s.lnk"),
        ("Leia-me", r"C:\Apps\readme.txt", r"C:\Start\r.lnk"),
        ("Site oficial", "https://example.com", r"C:\Start\w.lnk"),
    ])
    assert entries == [AppEntry("Spotify", r"C:\Apps\Spotify.exe", r"C:\Start\Spotify.lnk")]


def test_build_entries_keeps_the_first_of_duplicate_names_and_sorts() -> None:
    entries = build_entries([
        ("Steam", r"C:\User\Steam.exe", r"C:\U\Steam.lnk"),
        ("discord", r"C:\D\Update.exe", r"C:\U\Discord.lnk"),
        ("steam", r"C:\All\Steam.exe", r"C:\A\Steam.lnk"),
    ])
    assert [(e.name, e.target) for e in entries] == [
        ("discord", r"C:\D\Update.exe"),
        ("Steam", r"C:\User\Steam.exe"),
    ]


def test_root_pids_ignore_child_processes_of_the_same_app() -> None:
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    processes = [
        (100, 1, chrome),
        (101, 100, chrome),
        (102, 100, chrome),
        (200, 1, chrome.upper()),
        (300, 1, r"C:\Windows\explorer.exe"),
        (400, 1, None),
    ]
    assert root_pids(processes, chrome) == [100, 200]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/adapters/test_windows_pure.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sazed.adapters.windows'`.

- [ ] **Step 3: Implement the adapters**

`src/sazed/adapters/windows/__init__.py`:
```python
"""Windows implementations of the PC skill ports."""
```

`src/sazed/adapters/windows/catalog.py`:
```python
"""Installed apps from Start Menu shortcuts (.lnk). Store (UWP) apps are not covered."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from sazed.skills.pc.apps import AppEntry

log = logging.getLogger(__name__)

EXCLUDED_WORDS = ("uninstall", "desinstalar", "remover", "readme", "leia-me", "help", "ajuda")
_PROGRAMS = Path("Microsoft") / "Windows" / "Start Menu" / "Programs"


def start_menu_dirs() -> list[Path]:
    roots = [os.environ.get("APPDATA"), os.environ.get("PROGRAMDATA")]
    return [Path(r) / _PROGRAMS for r in roots if r]


def build_entries(shortcuts: Iterable[tuple[str, str, str]]) -> list[AppEntry]:
    """(display name, target, shortcut path) → entries. The first of duplicate names wins."""
    seen: set[str] = set()
    entries: list[AppEntry] = []
    for name, target, shortcut in shortcuts:
        key = name.strip().lower()
        if any(word in key for word in EXCLUDED_WORDS):
            continue
        if not target.lower().endswith(".exe"):
            continue
        if key in seen:
            continue
        seen.add(key)
        entries.append(AppEntry(name.strip(), target, shortcut))
    return sorted(entries, key=lambda e: e.name.lower())


class StartMenuCatalog:
    def __init__(self, dirs: Sequence[Path] | None = None) -> None:
        self._dirs = list(dirs) if dirs is not None else start_menu_dirs()
        self._entries: list[AppEntry] | None = None

    def entries(self) -> Sequence[AppEntry]:
        if self._entries is None:
            self._entries = build_entries(self._scan())
        return list(self._entries)

    def _scan(self) -> Iterator[tuple[str, str, str]]:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        for directory in self._dirs:
            if not directory.exists():
                continue
            for link in sorted(directory.rglob("*.lnk")):
                try:
                    target = str(shell.CreateShortcut(str(link)).TargetPath)
                except Exception:
                    log.warning("could not resolve shortcut %s", link, exc_info=True)
                    continue
                yield link.stem, target, str(link)
```

`src/sazed/adapters/windows/launcher.py`:
```python
"""Start apps through their shortcut; close them gracefully with WM_CLOSE."""

from __future__ import annotations

import os
from collections.abc import Iterable

import psutil

from sazed.skills.pc.apps import AppEntry


def _same_path(a: str | None, b: str) -> bool:
    return a is not None and os.path.normcase(os.path.normpath(a)) == os.path.normcase(
        os.path.normpath(b)
    )


def root_pids(processes: Iterable[tuple[int, int, str | None]], target: str) -> list[int]:
    """PIDs running `target` whose parent is not also running it (one per app instance)."""
    matching = {pid: ppid for pid, ppid, exe in processes if _same_path(exe, target)}
    return sorted(pid for pid, ppid in matching.items() if ppid not in matching)


def _snapshot() -> list[tuple[int, int, str | None]]:
    rows: list[tuple[int, int, str | None]] = []
    for proc in psutil.process_iter(["pid", "ppid", "exe"]):
        info = proc.info
        rows.append((info["pid"], info["ppid"] or 0, info.get("exe")))
    return rows


class WindowsLauncher:
    def launch(self, entry: AppEntry) -> None:
        os.startfile(entry.shortcut)  # type: ignore[attr-defined]  # Windows only

    def instances(self, entry: AppEntry) -> int:
        return len(root_pids(_snapshot(), entry.target))

    def close(self, entry: AppEntry) -> int:
        import win32con
        import win32gui
        import win32process

        pids = {pid for pid, _, exe in _snapshot() if _same_path(exe, entry.target)}
        closed: set[int] = set()

        def on_window(hwnd: int, _: object) -> bool:
            if win32gui.IsWindowVisible(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in pids:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    closed.add(pid)
            return True

        win32gui.EnumWindows(on_window, None)
        return len(closed)
```

`src/sazed/adapters/windows/audio.py`:
```python
"""Master volume through pycaw. The default device is re-read on every call (headphones change it)."""

from __future__ import annotations

from typing import Any


def _endpoint() -> Any:
    from pycaw.pycaw import AudioUtilities

    speakers = AudioUtilities.GetSpeakers()
    endpoint = getattr(speakers, "EndpointVolume", None)
    if endpoint is not None:
        return endpoint
    # Older pycaw: activate the interface by hand.
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume

    interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


class PycawAudio:
    def get_volume(self) -> int:
        return round(_endpoint().GetMasterVolumeLevelScalar() * 100)

    def set_volume(self, percent: int) -> None:
        _endpoint().SetMasterVolumeLevelScalar(max(0, min(100, percent)) / 100, None)

    def set_muted(self, muted: bool) -> None:
        _endpoint().SetMute(int(muted), None)

    def is_muted(self) -> bool:
        return bool(_endpoint().GetMute())
```

- [ ] **Step 4: Run the pure tests**

Run: `uv run pytest tests/adapters/test_windows_pure.py -v && uv run ruff check .`
Expected: PASS.

- [ ] **Step 5: Write and run the integration tests** (they open Character Map, a classic Win32 app that still exists on Windows 11, and change the real volume, then restore it)

`tests/adapters/test_windows_integration.py`:
```python
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from sazed.adapters.windows.audio import PycawAudio
from sazed.adapters.windows.catalog import StartMenuCatalog
from sazed.adapters.windows.launcher import WindowsLauncher

pytestmark = pytest.mark.windows
CHARMAP = r"C:\Windows\System32\charmap.exe"


def wait_until(condition: Callable[[], bool], seconds: float = 8.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.2)
    return False


@pytest.fixture
def shortcut_dir(tmp_path: Path) -> Path:
    import win32com.client

    link = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(tmp_path / "Mapa Teste.lnk"))
    link.TargetPath = CHARMAP
    link.Save()
    return tmp_path


def test_catalog_resolves_a_shortcut(shortcut_dir: Path) -> None:
    (entry,) = StartMenuCatalog([shortcut_dir]).entries()
    assert entry.name == "Mapa Teste"
    assert entry.target.lower() == CHARMAP.lower()


def test_launch_counts_and_closes_a_real_app(shortcut_dir: Path) -> None:
    (entry,) = StartMenuCatalog([shortcut_dir]).entries()
    launcher = WindowsLauncher()
    assert launcher.instances(entry) == 0, "close Character Map before running this test"
    launcher.launch(entry)
    assert wait_until(lambda: launcher.instances(entry) == 1)
    assert wait_until(lambda: launcher.close(entry) >= 1 or launcher.instances(entry) == 0)
    assert wait_until(lambda: launcher.instances(entry) == 0)


def test_real_start_menu_has_apps() -> None:
    assert len(StartMenuCatalog().entries()) > 0


def test_volume_set_read_and_restore() -> None:
    audio = PycawAudio()
    original, was_muted = audio.get_volume(), audio.is_muted()
    try:
        audio.set_volume(37)
        assert audio.get_volume() == 37
        audio.set_muted(True)
        assert audio.is_muted() is True
    finally:
        audio.set_volume(original)
        audio.set_muted(was_muted)
```

Run: `uv run pytest -m windows -v`
Expected: PASS. If `GetSpeakers()` has no `EndpointVolume` *and* the fallback fails, stop and report the installed pycaw version (`uv pip show pycaw`). Do not guess another API.

- [ ] **Step 6: Write `src/sazed/adapters/CLAUDE.md`**

```markdown
# sazed.adapters

Implementations of ports: `sqlite/` (coppermind), `onnx/` (embedder), `windows/` (catalog,
launcher, audio). This is the only package allowed to touch the OS, files, or models.

## Conventions
- Keep the Windows-API part thin and push decisions into pure functions (`build_entries`,
  `root_pids`) that are tested without Windows.
- Windows-only imports (`win32*`, `pycaw`, `comtypes`) are done inside methods, so the module
  imports on any machine and pure tests run anywhere.
- Integration tests are `@pytest.mark.windows` (real apps, real volume) or `@pytest.mark.model`.

## Traps
- Store (UWP) apps have no `.lnk`: WhatsApp, the new Notepad and Calculator are invisible
  to `StartMenuCatalog`. Integration tests use `charmap.exe` for that reason.
- Some shortcuts target a launcher (`Discord` → `Update.exe`), so closing cannot find their process.
- Closing posts `WM_CLOSE` and never terminates, so unsaved work gets the app's own prompt.
- `root_pids` counts instances by parent/child, otherwise Chrome's helpers look like many instances.
- SQLite migrations are append-only, and `PRAGMA user_version` is the schema version.
- e5 needs the `"query: "` prefix on both sides; it is applied only in `OnnxEmbedder`.
```

- [ ] **Step 7: Commit**

```bash
git add src/sazed/adapters/windows src/sazed/adapters/CLAUDE.md tests/adapters/test_windows_pure.py tests/adapters/test_windows_integration.py
git commit -m "feat(windows): add start-menu catalog, graceful launcher and pycaw audio" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Text CLI, logging, `aprendizado` and `revisar`

**Files:**
- Create: `src/sazed/runtime/logs.py`, `src/sazed/runtime/admin.py`, `src/sazed/interfaces/cli/main.py`
- Modify: `src/sazed/runtime/wiring.py` (add `StartupError`, `start()`, `build_default_app()`)
- Test: `tests/runtime/test_logs.py`, `tests/runtime/test_admin.py`, `tests/interfaces/test_cli.py`

**Interfaces:**
- Consumes: `SazedApp`, `build_app`, `load_config`, `ConfigError` (Task 13); adapters (Tasks 9, 14, 15).
- Produces:
  - `setup_logging(log_dir: Path, *, debug: bool) -> Path`
  - `StartupError(Exception)` (pt-BR `str()`), `start(config_path: Path | None) -> SazedApp`, `build_default_app(config) -> SazedApp`
  - admin: `LearnedRow(ref, kind, text, meaning, created_at)`, `EpisodeRow(id, at, utterance, what)`, `learned_rows(app)`, `forget_learned(app, ref) -> LearnedRow | None`, `failure_rows(app, limit)`, `intent_rows(app) -> list[tuple[str, str]]`, `label_episode(app, episode_id, intent_id) -> bool`, `DECISION_LABELS`, `REACTION_LABELS`
  - `main(argv: list[str] | None = None, *, build: Callable[[Path | None], SazedApp] | None = None, stdin: TextIO | None = None) -> int`

- [ ] **Step 1: Write the failing tests**

`tests/runtime/test_logs.py`:
```python
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from sazed.runtime.logs import setup_logging


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in root.handlers:
        handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


def test_logging_goes_to_the_file(tmp_path: Path) -> None:
    path = setup_logging(tmp_path / "logs", debug=False)
    logging.getLogger("sazed.test").error("algo quebrou: %s", "detalhe interno")
    assert "detalhe interno" in path.read_text(encoding="utf-8")


def test_logging_never_writes_to_the_console(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(tmp_path, debug=False)
    try:
        raise RuntimeError("stack trace secreto")
    except RuntimeError:
        logging.getLogger("sazed.test").exception("falhou")
    captured = capsys.readouterr()
    assert "secreto" not in captured.out + captured.err


def test_debug_only_when_enabled(tmp_path: Path) -> None:
    quiet = setup_logging(tmp_path / "a", debug=False)
    logging.getLogger("sazed.test").debug("ranking detalhado")
    assert "ranking detalhado" not in quiet.read_text(encoding="utf-8")
    loud = setup_logging(tmp_path / "b", debug=True)
    logging.getLogger("sazed.test").debug("ranking detalhado")
    assert "ranking detalhado" in loud.read_text(encoding="utf-8")
```

`tests/runtime/test_admin.py`:
```python
from datetime import datetime
from pathlib import Path
from random import Random
from typing import get_args

from fakes.clock import ManualClock
from fakes.embedder import HashingEmbedder
from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher

from sazed.core.coppermind import Episode, NewAlias, Reaction
from sazed.core.decisions import Decision
from sazed.runtime.admin import (
    DECISION_LABELS,
    REACTION_LABELS,
    failure_rows,
    forget_learned,
    intent_rows,
    label_episode,
    learned_rows,
)
from sazed.runtime.config import Config, DataConfig
from sazed.runtime.wiring import SazedApp, build_app

T0 = datetime(2026, 10, 14, 12, 0)


def boot(tmp_path: Path) -> SazedApp:
    return build_app(
        Config(data=DataConfig(dir=tmp_path)),
        embedder=HashingEmbedder(),
        catalog=FakeCatalog(["WhatsApp"]),
        launcher=FakeLauncher(),
        audio=FakeAudio(),
        clock=ManualClock(),
        rng=Random(0),
    )


def test_every_decision_and_reaction_has_a_pt_br_label() -> None:
    names = {t.__name__ for t in get_args(Decision)} | {"control", "error"}
    assert names <= set(DECISION_LABELS)
    assert set(Reaction) == set(REACTION_LABELS)


def test_learned_rows_describe_items_without_internal_ids(tmp_path: Path) -> None:
    app = boot(tmp_path)
    app.store.learn([], [NewAlias("app", "zap", "WhatsApp")], T0)
    (row,) = learned_rows(app)
    assert (row.ref, row.kind, row.text, row.meaning) == ("a1", "apelido", "zap", "WhatsApp")


def test_forget_learned_by_ref(tmp_path: Path) -> None:
    app = boot(tmp_path)
    app.store.learn([], [NewAlias("app", "zap", "WhatsApp")], T0)
    assert forget_learned(app, "a1") is not None
    assert app.store.aliases() == []
    assert forget_learned(app, "a1") is None
    assert forget_learned(app, "x9") is None
    assert forget_learned(app, "abc") is None


def test_failures_are_listed_with_labels(tmp_path: Path) -> None:
    app = boot(tmp_path)
    app.store.record_episode(Episode("liga o navegador", T0, (), {}, "NotUnderstood", None, ""))
    (row,) = failure_rows(app, 10)
    assert row.utterance == "liga o navegador"
    assert row.what == "não entendido"


def test_label_episode_learns_the_normalised_utterance(tmp_path: Path) -> None:
    app = boot(tmp_path)
    episode_id = app.store.record_episode(
        Episode("Liga o navegador!", T0, (), {}, "NotUnderstood", None, "")
    )
    assert label_episode(app, episode_id, "abrir_app") is True
    assert [(e.text, e.intent_id) for e in app.store.examples()] == [("liga o navegador", "abrir_app")]


def test_label_episode_refuses_unknown_intent_or_episode(tmp_path: Path) -> None:
    app = boot(tmp_path)
    episode_id = app.store.record_episode(Episode("x", T0, (), {}, "NotUnderstood", None, ""))
    assert label_episode(app, episode_id, "inexistente") is False
    assert label_episode(app, 999, "abrir_app") is False
    assert app.store.examples() == []


def test_intent_rows_describe_in_pt_br(tmp_path: Path) -> None:
    rows = dict(intent_rows(boot(tmp_path)))
    assert rows["abrir_app"] == "abrir um programa"
```

`tests/interfaces/test_cli.py`:
```python
import io
from datetime import datetime
from pathlib import Path
from random import Random

import pytest
from fakes.clock import ManualClock
from fakes.embedder import HashingEmbedder
from fakes.ports import FakeAudio, FakeCatalog, FakeLauncher

from sazed.core.coppermind import Episode, NewAlias
from sazed.interfaces.cli.main import main
from sazed.runtime.config import Config, DataConfig
from sazed.runtime.wiring import SazedApp, StartupError, build_app

T0 = datetime(2026, 10, 14, 12, 0)


@pytest.fixture
def audio() -> FakeAudio:
    return FakeAudio(volume=50)


@pytest.fixture
def app(tmp_path: Path, audio: FakeAudio) -> SazedApp:
    return build_app(
        Config(data=DataConfig(dir=tmp_path)),
        embedder=HashingEmbedder(),
        catalog=FakeCatalog(["WhatsApp", "Google Chrome"]),
        launcher=FakeLauncher(),
        audio=audio,
        clock=ManualClock(),
        rng=Random(0),
    )


def run(app: SazedApp, argv: list[str], stdin: str = "") -> int:
    return main(argv, build=lambda _path: app, stdin=io.StringIO(stdin))


def test_repl_greets_executes_and_says_goodbye(
    app: SazedApp, audio: FakeAudio, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(app, [], "volume em 30\nsair\n") == 0
    out = capsys.readouterr().out
    assert audio.volume == 30
    assert "30%" in out
    assert "Até logo, Mestre Artur." in out


def test_repl_ends_on_end_of_input(app: SazedApp, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(app, [], "") == 0
    assert "Até logo" in capsys.readouterr().out


def test_learned_list_and_forget(app: SazedApp, capsys: pytest.CaptureFixture[str]) -> None:
    app.store.learn([], [NewAlias("app", "zap", "WhatsApp")], T0)
    assert run(app, ["aprendizado"]) == 0
    out = capsys.readouterr().out
    assert "a1" in out and "apelido" in out and "zap" in out and "WhatsApp" in out
    assert run(app, ["aprendizado", "--esquecer", "a1"]) == 0
    assert app.store.aliases() == []


def test_forgetting_an_unknown_ref_is_explained(app: SazedApp, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(app, ["aprendizado", "--esquecer", "a9"]) == 1
    assert "a9" in capsys.readouterr().out


def test_review_lists_and_labels(app: SazedApp, capsys: pytest.CaptureFixture[str]) -> None:
    episode_id = app.store.record_episode(Episode("liga o navegador", T0, (), {}, "NotUnderstood", None, ""))
    assert run(app, ["revisar"]) == 0
    assert "liga o navegador" in capsys.readouterr().out
    assert run(app, ["revisar", "--rotular", str(episode_id), "abrir_app"]) == 0
    assert [e.intent_id for e in app.store.examples()] == ["abrir_app"]


def test_review_rejects_an_unknown_intent(app: SazedApp, capsys: pytest.CaptureFixture[str]) -> None:
    episode_id = app.store.record_episode(Episode("x", T0, (), {}, "NotUnderstood", None, ""))
    assert run(app, ["revisar", "--rotular", str(episode_id), "voar"]) == 1
    assert "abrir_app" in capsys.readouterr().out  # lists the valid intents


def test_startup_error_is_shown_without_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    def broken(_path: Path | None) -> SazedApp:
        raise StartupError("Configuração inválida em config.toml:\n- nlu.t_exec: deve ser no máximo 1")

    assert main([], build=broken, stdin=io.StringIO("")) == 2
    out = capsys.readouterr()
    assert "deve ser no máximo 1" in out.out
    assert "Traceback" not in out.out + out.err


def test_help_is_in_pt_br(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--ajuda"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert "uso:" in out and "aprendizado" in out
    for english in ("usage:", "options:", "show this help", "positional arguments"):
        assert english not in out


def test_bad_arguments_are_explained_in_pt_br(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["voar"])
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert "--ajuda" in captured.out + captured.err
    assert "invalid choice" not in captured.out + captured.err
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/runtime/test_logs.py tests/runtime/test_admin.py tests/interfaces -v`
Expected: FAIL with `ModuleNotFoundError` for `sazed.runtime.logs`, `sazed.runtime.admin`, and `sazed.interfaces.cli.main`.

- [ ] **Step 3: Implement logging**

`src/sazed/runtime/logs.py`:
```python
"""Logs go to a rotating file only. Nothing internal ever reaches the console."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path, *, debug: bool) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "sazed.log"
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
        old.close()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    logging.captureWarnings(True)
    return path
```

- [ ] **Step 4: Implement admin**

`src/sazed/runtime/admin.py`:
```python
"""Read and edit what Sazed learned, for the `aprendizado` and `revisar` commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sazed.core.coppermind import LearnedItem, LearnedKind, NewExample, Reaction
from sazed.core.outcomes import FAILURE_NAMES
from sazed.nlu.normalize import normalize
from sazed.runtime.wiring import SazedApp

KIND_LABELS = {LearnedKind.EXAMPLE: "exemplo", LearnedKind.ALIAS: "apelido"}
KIND_PREFIX = {LearnedKind.EXAMPLE: "e", LearnedKind.ALIAS: "a"}
DECISION_LABELS = {
    "Execute": "executado",
    "Confirm": "pediu confirmação",
    "AskSlot": "pediu um detalhe",
    "NotUnderstood": "não entendido",
    "control": "resposta",
    "error": "erro interno",
}
REACTION_LABELS = {
    Reaction.NONE: "",
    Reaction.CONFIRMED: "confirmado",
    Reaction.DENIED: "negado",
    Reaction.CORRECTED: "corrigido",
}


@dataclass(frozen=True)
class LearnedRow:
    ref: str
    kind: str
    text: str
    meaning: str
    created_at: datetime


@dataclass(frozen=True)
class EpisodeRow:
    id: int
    at: datetime
    utterance: str
    what: str


def _describe_intent(app: SazedApp, intent_id: str) -> str:
    for skill in app.skills:
        for spec in skill.intents:
            if spec.id == intent_id:
                return spec.describe({})
    return "pedido desconhecido"


def _row(app: SazedApp, item: LearnedItem) -> LearnedRow:
    meaning = item.target if item.kind is LearnedKind.ALIAS else _describe_intent(app, item.target)
    return LearnedRow(
        f"{KIND_PREFIX[item.kind]}{item.id}", KIND_LABELS[item.kind], item.text, meaning,
        item.created_at,
    )


def learned_rows(app: SazedApp) -> list[LearnedRow]:
    return [_row(app, item) for item in app.store.learned()]


def forget_learned(app: SazedApp, ref: str) -> LearnedRow | None:
    kind = next((k for k, p in KIND_PREFIX.items() if ref[:1] == p), None)
    if kind is None or not ref[1:].isdigit():
        return None
    item = app.store.forget(kind, int(ref[1:]))
    return None if item is None else _row(app, item)


def failure_rows(app: SazedApp, limit: int) -> list[EpisodeRow]:
    rows = []
    for stored in app.store.recent_failures(limit):
        ep = stored.episode
        parts = [DECISION_LABELS.get(ep.decision, ep.decision), REACTION_LABELS[ep.reaction]]
        if ep.outcome in FAILURE_NAMES:
            parts.append("falhou")
        rows.append(EpisodeRow(stored.id, ep.at, ep.utterance, ", ".join(p for p in parts if p)))
    return rows


def intent_rows(app: SazedApp) -> list[tuple[str, str]]:
    return [(spec.id, spec.describe({})) for skill in app.skills for spec in skill.intents]


def label_episode(app: SazedApp, episode_id: int, intent_id: str) -> bool:
    known = {spec.id for skill in app.skills for spec in skill.intents}
    stored = app.store.episode(episode_id)
    if stored is None or intent_id not in known:
        return False
    text = normalize(stored.episode.utterance)
    app.store.learn([NewExample(text, intent_id, app.index.vectorize(text), "review")], [], app.clock())
    return True
```

- [ ] **Step 5: Add startup to the wiring**

Append to `src/sazed/runtime/wiring.py`:
```python
import logging
from pathlib import Path

from sazed.adapters.sqlite.coppermind import CoppermindVersionError
from sazed.runtime.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from sazed.runtime.logs import setup_logging

log = logging.getLogger(__name__)


class StartupError(Exception):
    """Sazed cannot start. `str(error)` is a pt-BR message meant for the user."""


def build_default_app(config: Config) -> SazedApp:
    from sazed.adapters.onnx.embedder import OnnxEmbedder
    from sazed.adapters.windows.audio import PycawAudio
    from sazed.adapters.windows.catalog import StartMenuCatalog
    from sazed.adapters.windows.launcher import WindowsLauncher

    return build_app(
        config,
        embedder=OnnxEmbedder(config.model.embedder_path),
        catalog=StartMenuCatalog(),
        launcher=WindowsLauncher(),
        audio=PycawAudio(),
    )


def start(config_path: Path | None) -> SazedApp:
    path = config_path or DEFAULT_CONFIG_PATH
    try:
        config = load_config(path)
    except ConfigError as err:
        raise StartupError(str(err)) from None
    setup_logging(config.data.dir / "logs", debug=config.logging.debug)
    if not (config.model.embedder_path / "model.onnx").exists():
        raise StartupError(
            f"Não encontrei o modelo em {config.model.embedder_path}. "
            "Rode uma vez: uv run python scripts/fetch_model.py"
        )
    try:
        return build_default_app(config)
    except CoppermindVersionError:
        log.exception("coppermind schema is newer than this version")
        raise StartupError(
            "Minha mente de cobre foi gravada por uma versão mais nova de Sazed. "
            "Atualize o programa antes de continuar."
        ) from None
    except Exception:
        log.exception("startup failed")
        raise StartupError(
            "Peço desculpas, não consegui iniciar. Os detalhes estão no arquivo de log."
        ) from None
```
Move the new imports to the top of the module with the others (ruff enforces it).

- [ ] **Step 6: Implement the CLI**

`src/sazed/interfaces/cli/main.py`:
```python
"""Terminal interface. Talks only to sazed.runtime; every string here is pt-BR."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, TextIO

from sazed.runtime.admin import (
    failure_rows,
    forget_learned,
    intent_rows,
    label_episode,
    learned_rows,
)
from sazed.runtime.wiring import SazedApp, StartupError, start

EXIT_WORDS = {"sair", "tchau", "até logo", "ate logo"}


class _Formatter(argparse.HelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):  # type: ignore[no-untyped-def]
        return super().add_usage(usage, actions, groups, prefix="uso: ")


class _Parser(argparse.ArgumentParser):
    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(add_help=False, formatter_class=_Formatter, **kwargs)
        self._positionals.title = "comandos"
        self._optionals.title = "opções"
        self.add_argument("-h", "--ajuda", action="help", help="mostra esta ajuda e sai")

    def error(self, message: str) -> NoReturn:
        self.exit(2, "Comando não reconhecido. Use 'sazed --ajuda' para ver as opções.\n")


def _parser() -> _Parser:
    parser = _Parser(prog="sazed", description="Sazed, seu assistente local.")
    parser.add_argument("--config", type=Path, default=None, help="caminho do config.toml")
    commands = parser.add_subparsers(dest="command", parser_class=_Parser, metavar="comando")
    learned = commands.add_parser("aprendizado", help="lista o que Sazed aprendeu")
    learned.add_argument("--esquecer", metavar="REF", help="remove um item (ex.: e3, a5)")
    review = commands.add_parser("revisar", help="lista falhas recentes para rotular")
    review.add_argument("--rotular", nargs=2, metavar=("EPISODIO", "PEDIDO"))
    review.add_argument("--limite", type=int, default=20, help="quantas falhas listar")
    return parser


def _learned(app: SazedApp, args: argparse.Namespace) -> int:
    if args.esquecer:
        row = forget_learned(app, args.esquecer)
        if row is None:
            print(f"Não encontrei '{args.esquecer}' em minha mente de cobre.")
            return 1
        print(f"Esquecido: {row.kind} '{row.text}' → {row.meaning}.")
        return 0
    rows = learned_rows(app)
    if not rows:
        print("Ainda não aprendi nada, Mestre.")
    for row in rows:
        print(f"{row.ref:>5}  {row.kind:<8} '{row.text}' → {row.meaning}  ({row.created_at:%d/%m/%Y %H:%M})")
    return 0


def _review(app: SazedApp, args: argparse.Namespace) -> int:
    if args.rotular:
        episode, intent = args.rotular
        if not episode.isdigit() or not label_episode(app, int(episode), intent):
            print("Não consegui rotular. Pedidos válidos:")
            for intent_id, description in intent_rows(app):
                print(f"  {intent_id:<16} {description}")
            return 1
        print("Guardado em minha mente de cobre.")
        return 0
    rows = failure_rows(app, args.limite)
    if not rows:
        print("Nenhuma falha recente, Mestre.")
    for row in rows:
        print(f"{row.id:>5}  {row.at:%d/%m %H:%M}  '{row.utterance}'  [{row.what}]")
    return 0


def _repl(app: SazedApp, stdin: TextIO) -> int:
    print(app.greeting())
    try:
        while True:
            sys.stdout.write("> ")
            sys.stdout.flush()
            line = stdin.readline()
            if not line:
                break
            text = line.strip()
            if not text:
                continue
            if text.lower() in EXIT_WORDS:
                break
            print(app.assistant.handle(text).text)
    except KeyboardInterrupt:
        print()
    print(app.farewell())
    return 0


def main(
    argv: list[str] | None = None,
    *,
    build: Callable[[Path | None], SazedApp] | None = None,
    stdin: TextIO | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        app = (build or start)(args.config)
    except StartupError as err:
        print(str(err))
        return 2
    try:
        if args.command == "aprendizado":
            return _learned(app, args)
        if args.command == "revisar":
            return _review(app, args)
        return _repl(app, stdin or sys.stdin)
    finally:
        app.close()
```
Note the subparsers are built with `parser_class=_Parser`, so they also get pt-BR help and errors.

- [ ] **Step 7: Run all tests**

Run: `uv run pytest -v && uv run ruff check . && uv run mypy`
Expected: PASS. `test_repl_greets_executes_and_says_goodbye` depends on the hashing fake ranking "volume em 30" first. It is a seed example (score 1.0), so this is deterministic.

- [ ] **Step 8: Verify by hand with the real model and desktop**

Run `uv run sazed` and type, in order: `volume em 30`, `aumenta o volume`, `de novo`, `muta`, `tira do mudo`, `abre o <an app from your Start Menu>`, `fecha o <same app>`, `sim` if asked, `abre aí o <app>` (expect a confirmation or execution), `esquece isso`, `sair`. Then run `uv run sazed aprendizado` and `uv run sazed revisar`.
Record in the root `CLAUDE.md` under `## Verified by hand` each command, what happened, and the date. Mark anything that did not work, and anything you could not try, as **unverified**.

- [ ] **Step 9: Commit**

```bash
git add src/sazed/runtime src/sazed/interfaces tests/runtime tests/interfaces CLAUDE.md
git commit -m "feat(cli): add pt-BR REPL with aprendizado and revisar commands" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: NLU fixture, threshold tuning, and documentation

**Files:**
- Create: `src/sazed/runtime/evaluation.py`, `tests/fixtures/nlu_cases.toml`, `scripts/tune_thresholds.py`
- Test: `tests/runtime/test_evaluation.py`, `tests/nlu/test_fixture.py` (`@pytest.mark.model`)
- Modify: `src/sazed/runtime/config.py` (tuned defaults), `config.example.toml`, `CLAUDE.md`

**Interfaces:**
- Consumes: `Assistant`, `build_extractors`, skills, `IntentIndex`.
- Produces: `NO_INTENT = "none"`; `NluCase(text, intent, app=None, percent=None)`; `CaseResult(case, top_intent: str | None, decision: Decision | None)`; `Report(results, accuracy, false_execute_rate, confirm_rate)` with `.false_executes() -> list[CaseResult]` and `.misranked() -> list[CaseResult]`; `load_cases(path) -> tuple[list[str], list[NluCase]]` (app names, cases); `evaluate(cases, *, index, app_names, thresholds) -> Report`; `MIN_ACCURACY = 0.90`, `MAX_FALSE_EXECUTE = 0.02`.

- [ ] **Step 1: Write the failing evaluation tests** (the evaluator is a shared helper for the fixture test and the tuning script, so its arithmetic is proven on hand-made data first)

`tests/runtime/test_evaluation.py`:
```python
import pytest
from fakes.index import ScriptedIndex

from sazed.core.policy import Thresholds
from sazed.runtime.evaluation import NO_INTENT, NluCase, evaluate

TH = Thresholds(t_exec=0.90, t_confirm=0.70, g_min=0.05)
APPS = ["Google Chrome", "Spotify"]
INDEX = ScriptedIndex({
    "abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.6},   # right, executes
    "fecha o spotify": {"abrir_app": 0.95, "fechar_app": 0.6},  # wrong intent, executes
    "abre ai o spotify": {"abrir_app": 0.80, "fechar_app": 0.3},  # right, confirms
    "que horas sao": {"volume_mudo": 0.95},                      # out of domain, executes
    "conta uma piada": {"volume_mudo": 0.20},                    # out of domain, not understood
})
CASES = [
    NluCase("abre o chrome", "abrir_app", app="Google Chrome"),
    NluCase("fecha o spotify", "fechar_app", app="Spotify"),
    NluCase("abre ai o spotify", "abrir_app", app="Spotify"),
    NluCase("que horas sao", NO_INTENT),
    NluCase("conta uma piada", NO_INTENT),
]


def test_report_arithmetic() -> None:
    report = evaluate(CASES, index=INDEX, app_names=APPS, thresholds=TH)
    assert report.accuracy == pytest.approx(2 / 3)
    assert report.false_execute_rate == pytest.approx(2 / 5)
    assert report.confirm_rate == pytest.approx(1 / 5)
    assert [r.case.text for r in report.false_executes()] == ["fecha o spotify", "que horas sao"]
    assert [r.case.text for r in report.misranked()] == ["fecha o spotify"]


def test_executing_the_right_intent_with_the_wrong_app_is_a_false_execute() -> None:
    case = NluCase("abre o chrome", "abrir_app", app="Spotify")
    report = evaluate([case], index=INDEX, app_names=APPS, thresholds=TH)
    assert report.false_execute_rate == 1.0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/runtime/test_evaluation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sazed.runtime.evaluation'`.

- [ ] **Step 3: Implement the evaluator**

`src/sazed/runtime/evaluation.py`:
```python
"""Run labelled phrases through the real decision path with dry-run ports.

Used by the NLU fixture test and scripts/tune_thresholds.py. Each case gets a fresh
Assistant, so cases never influence each other; the index is shared (embeddings are the
expensive part).
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from random import Random

from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.core.decisions import AskSlot, Confirm, Decision, Execute
from sazed.core.learning import LearningThresholds
from sazed.core.policy import Thresholds
from sazed.core.types import SlotValue
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

    def false_executes(self) -> list[CaseResult]:
        return [r for r in self.results if _is_false_execute(r)]

    def misranked(self) -> list[CaseResult]:
        return [r for r in self.results if r.case.intent != NO_INTENT and r.top_intent != r.case.intent]


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
    if case.intent == NO_INTENT or decision.intent_id != case.intent:
        return True
    for name, expected in (("app", case.app), ("percent", case.percent)):
        if expected is None:
            continue
        value = decision.slots.get(name)
        if not isinstance(value, SlotValue) or value.value != expected:
            return True
    return False


def load_cases(path: Path) -> tuple[list[str], list[NluCase]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cases = [
        NluCase(c["text"], c["intent"], c.get("app"), c.get("percent")) for c in data["case"]
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
        results.append(CaseResult(case, ranking[0].intent_id if ranking else None, response.decision))

    in_domain = [r for r in results if r.case.intent != NO_INTENT]
    correct = sum(1 for r in in_domain if r.top_intent == r.case.intent)
    asked = sum(1 for r in results if isinstance(r.decision, Confirm | AskSlot))
    return Report(
        results=results,
        accuracy=correct / len(in_domain) if in_domain else 1.0,
        false_execute_rate=sum(_is_false_execute(r) for r in results) / len(results),
        confirm_rate=asked / len(results),
    )
```
Note: `instances` returns 1, so `fechar_app` only confirms on inexact matches, which is what the fixture measures.

Run: `uv run pytest tests/runtime/test_evaluation.py -v`. Expected: PASS.

- [ ] **Step 4: Write the fixture**

`tests/fixtures/nlu_cases.toml`, with phrases that are **not** seed examples. Learned examples never go here. Use this content and extend it to at least 80 cases, keeping roughly this mix: ~45% apps (open/close, including the opposite-verb pairs), ~30% volume, ~25% out of domain:
```toml
# Labelled pt-BR phrases for the real embedder (tests/nlu/test_fixture.py).
# Rules: never copy a seed example; never add learned examples; intent "none" = must not execute.
apps = [
    "Google Chrome", "Spotify", "Discord", "Visual Studio Code", "Steam",
    "Microsoft Word", "Microsoft Excel", "Firefox", "OBS Studio", "Calculadora",
]

[[case]]
text = "abre o google chrome"
intent = "abrir_app"
app = "Google Chrome"

[[case]]
text = "fecha o google chrome"
intent = "fechar_app"
app = "Google Chrome"

[[case]]
text = "pode iniciar o spotify"
intent = "abrir_app"
app = "Spotify"

[[case]]
text = "encerra o spotify agora"
intent = "fechar_app"
app = "Spotify"

[[case]]
text = "quero jogar abre a steam"
intent = "abrir_app"
app = "Steam"

[[case]]
text = "fecha a steam por favor"
intent = "fechar_app"
app = "Steam"

[[case]]
text = "abre o discord pra mim"
intent = "abrir_app"
app = "Discord"

[[case]]
text = "sai do discord"
intent = "fechar_app"
app = "Discord"

[[case]]
text = "preciso do word aberto"
intent = "abrir_app"
app = "Microsoft Word"

[[case]]
text = "fecha o excel"
intent = "fechar_app"
app = "Microsoft Excel"

[[case]]
text = "deixa o volume em quarenta"
intent = "volume_definir"
percent = 40

[[case]]
text = "som em 15 por cento"
intent = "volume_definir"
percent = 15

[[case]]
text = "aumenta um pouco o som"
intent = "volume_aumentar"

[[case]]
text = "sobe o volume em 30"
intent = "volume_aumentar"
percent = 30

[[case]]
text = "baixa um pouco"
intent = "volume_diminuir"

[[case]]
text = "abaixa o volume em dez"
intent = "volume_diminuir"
percent = 10

[[case]]
text = "silencia tudo"
intent = "volume_mudo"

[[case]]
text = "pode tirar do mudo"
intent = "volume_mudo"

[[case]]
text = "que horas são"
intent = "none"

[[case]]
text = "me conta uma piada"
intent = "none"

[[case]]
text = "qual a previsão do tempo para amanhã"
intent = "none"

[[case]]
text = "quem foi o senhor soberano"
intent = "none"

[[case]]
text = "me lembra de beber água"
intent = "none"

[[case]]
text = "obrigado sazed"
intent = "none"
```

- [ ] **Step 5: Write the fixture test**

`tests/nlu/test_fixture.py`:
```python
from pathlib import Path

import pytest

from sazed.adapters.onnx.embedder import OnnxEmbedder
from sazed.core.policy import Thresholds
from sazed.nlu.matcher import IntentMatcher
from sazed.runtime.config import DEFAULT_MODEL_DIR, Config
from sazed.runtime.evaluation import (
    MAX_FALSE_EXECUTE,
    MIN_ACCURACY,
    DryRunPorts,
    evaluate,
    load_cases,
)
from sazed.skills.pc.apps import AppsSkill
from sazed.skills.pc.volume import VolumeSkill

pytestmark = pytest.mark.model
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nlu_cases.toml"


def test_fixture_meets_accuracy_and_false_execute_thresholds_with_default_config() -> None:
    if not (DEFAULT_MODEL_DIR / "model.onnx").exists():
        pytest.fail("model missing: run `uv run python scripts/fetch_model.py` first")
    app_names, cases = load_cases(FIXTURE)
    assert len(cases) >= 80
    index = IntentMatcher(OnnxEmbedder(DEFAULT_MODEL_DIR))
    ports = DryRunPorts(app_names)
    for skill in (AppsSkill(ports, ports), VolumeSkill(ports)):
        for spec in skill.intents:
            index.add_examples(spec.id, spec.examples)
    nlu = Config().nlu
    report = evaluate(
        cases, index=index, app_names=app_names,
        thresholds=Thresholds(nlu.t_exec, nlu.t_confirm, nlu.g_min),
    )
    detail = "\n".join(
        f"{r.case.text!r}: expected {r.case.intent}, top {r.top_intent}, {type(r.decision).__name__}"
        for r in report.false_executes() + report.misranked()
    )
    assert report.accuracy >= MIN_ACCURACY, detail
    assert report.false_execute_rate <= MAX_FALSE_EXECUTE, detail
```

Run: `uv run pytest -m model tests/nlu/test_fixture.py -v`
Expected: the outcome is unknown until tuned, because the defaults are placeholders. Record the first run's accuracy and false-execute rate.

- [ ] **Step 6: Tune the thresholds**

`scripts/tune_thresholds.py`:
```python
"""Sweep t_exec / t_confirm / g_min over the NLU fixture and print the safest good settings.

Usage: uv run python scripts/tune_thresholds.py
"""

from functools import lru_cache
from pathlib import Path

from sazed.adapters.onnx.embedder import OnnxEmbedder
from sazed.core.policy import Thresholds
from sazed.core.types import Ranking
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
                if report.accuracy >= MIN_ACCURACY and report.false_execute_rate <= MAX_FALSE_EXECUTE:
                    grid.append((report.confirm_rate, -th.t_exec, th, report))
    if not grid:
        print("No setting meets the thresholds. Improve seeds/fixture before tuning.")
        return
    grid.sort(key=lambda row: (row[0], row[1]))
    for confirm_rate, _, th, report in grid[:5]:
        print(f"{th}  accuracy={report.accuracy:.3f}  false_exec={report.false_execute_rate:.3f}  ask={confirm_rate:.3f}")


if __name__ == "__main__":
    main()
```

Run: `uv run python scripts/tune_thresholds.py`. It takes a few minutes, because every grid point re-runs every case through a fresh assistant. The embeddings themselves are cached.
Pick the first row: it asks the fewest questions, breaking ties toward the higher `t_exec`. Put its values in `NluConfig` defaults (`src/sazed/runtime/config.py`) **and** in `config.example.toml` (the example-config test keeps them equal), and remove the "Placeholders" comment. If no setting qualifies, stop and report the misranked cases. The fix is better seed examples (a skills change with its own test), never a lower bar.

Also run the int8-vs-fp32 check (deviation 1). `uv run python scripts/fetch_model.py --variant fp32 --dir models/e5-fp32`, then point `DEFAULT_MODEL_DIR` at it temporarily (an env-free local edit you revert) and re-run the tuner. Keep int8 unless fp32 is the only one that meets the bar. Record both results.

- [ ] **Step 7: Run the fixture test and the full suite**

Run: `uv run pytest -m model -v && uv run pytest -v && uv run pytest -m windows -v && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: all PASS. Paste the fixture's final accuracy and false-execute rate into the commit body.

- [ ] **Step 8: Update the root `CLAUDE.md`**

Replace the **Status** section with:
```markdown
## Status

- 2026-10-14: sub-project 1 (core + text CLI + PC slice) implemented per
  `docs/superpowers/plans/2026-10-14-sazed-core.md`. Discrimination proofs:
  `docs/superpowers/proofs/2026-10-14-sub-project-1.md`.
- NLU fixture (<N> cases): accuracy <A>, false-execute <F> with t_exec=<x>, t_confirm=<y>, g_min=<z> (embedder variant <qint8|fp32>).
- **Unverified:** `learning.t_conflict` / `t_dup` are placeholders (no fixture measures them yet);
  Store (UWP) apps are not in the catalog; closing apps whose shortcut targets a launcher.
- **Next step:** brainstorm sub-project 2 (PC skills).
```
Fill the `<…>` from the real run. These are measured values, not placeholders: leaving any `<…>` in the file is a failed step.

- [ ] **Step 9: Commit**

```bash
git add src/sazed/runtime/evaluation.py src/sazed/runtime/config.py config.example.toml tests/fixtures tests/runtime/test_evaluation.py tests/nlu/test_fixture.py scripts/tune_thresholds.py CLAUDE.md
git commit -m "test(nlu): add labelled fixture and tune decision thresholds" -m "<accuracy / false-execute / thresholds from the run>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
