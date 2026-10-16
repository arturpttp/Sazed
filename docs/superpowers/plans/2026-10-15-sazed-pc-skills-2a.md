# Sazed Sub-project 2a (one-shot PC skills) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Typed pt-BR commands control media, lock/power the PC (always confirmed), take screenshots, open Settings pages, set brightness, open websites, search the web, report memory/CPU/disk, and open/close Store apps; sub-project 1's deferred minors are fixed first.

**Architecture:** Each area is a skill in `src/sazed/skills/pc/` declaring its ports; Windows adapters live in `src/sazed/adapters/windows/`. Sites and Store apps join the app catalog behind the existing `abrir_app`/`fechar_app` intents. A new `runtime/skills.py` builds every skill from one `PcPorts` bundle, used by wiring, evaluation and the test harness alike.

**Tech Stack:** Python 3.12 (uv), existing core; new: `winrt-*` packages (media sessions, Store package folders), `Pillow` (screenshots); `pywin32` (WMI brightness, `shell:AppsFolder`), `psutil` (status).

**Spec:** `docs/superpowers/specs/2026-10-15-sazed-pc-skills-2a-design.md` (builds on `docs/superpowers/specs/2026-10-14-sazed-core-design.md`).

## Global Constraints

- TDD for every change; each property-pinning test gets a discrimination proof (mutation → FAIL output) appended to `docs/superpowers/proofs/2026-10-15-sub-project-2a.md`.
- Pure packages (`core`, `nlu`) never read the clock, env, or do I/O; `core` is stdlib-only (`tests/test_architecture.py`). Skills import only `sazed.core` and `sazed.skills`.
- Windows-only imports happen inside adapter methods, so modules import anywhere.
- User-facing text is pt-BR (masculine Sazed, "Mestre Artur"); code, comments, docs, commits in English. Conventional Commits, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Seed examples: pt-BR, already normalised (lowercase, no punctuation, accents kept), ≥ 8 per intent, unique across intents (`tests/skills/test_specs.py`). Opposing intents share objects so the verb decides.
- A power action never runs without confirmation, at any score, after any learning. Power intents are never learned.
- Only `http`/`https` URLs in config; search queries are URL-encoded and never reach a shell.
- No test ever executes a power action.
- NLU fixture bar unchanged: accuracy ≥ 0.90, false-execute ≤ 0.02.
- Local `CLAUDE.md` files change in the same commit as the convention they describe.

## Review Focus

1. "abre o whatsapp" when both the app **WhatsApp** and the site **WhatsApp Web** exist must open the app, not ask "qual deles?" (token-set fuzzy scores a contained name 100). Pinned in Task 6.
2. "pesquisa no youtube" with no query asks "O que devo pesquisar?", and a bare answer like "lofi" (no trigger verb) must be taken as the query. Pinned in Task 8.
3. A power intent at score 0.80 confirmed with "sim" must not be learned (score-1.0 confirms are DESTRUCTIVE and already skip learning, so only a LOW_SCORE confirm proves the gate). Pinned in Task 10.
4. A Store app whose visible window belongs to `ApplicationFrameHost.exe` (Calculator, verified 2026-10-15) must still close. Pinned in Task 7.
5. "mais" / "de novo" right after opening an app must not open a second copy, and a bare "mais" with nothing to repeat must never be ranked as a command. Pinned in Task 3.

## Deviations from the spec (decided while planning)

Each is smaller than what the spec described and gives the user the same result:

1. **Power acknowledges before acting** (spec §3.2 said "a deferred action the runtime runs last"): the Windows adapter delays the action itself — `shutdown /s /t 5` (cancellable with `shutdown /a`) and a 2 s timer for sleep and sign-out. The core is unchanged.
2. **Sites reuse `AppOpened`** instead of a separate `SiteOpened` ("Abrindo YouTube" reads the same).
3. **Media outcomes:** `MediaNext` / `MediaPrevious` instead of `MediaSkipped(direction)` (cleaner pt-BR templates); `NothingPlaying` is folded into `NoMediaSession`.
4. **Power outcomes:** `Locked`, `ShuttingDown`, `Restarting`, `Suspending`, `SigningOut` instead of `PowerAction(kind)` (one template each, no enum rendering).
5. **Out-of-range numbers** (spec §8 item 3 said "ask"): Sazed answers with the valid range (`InvalidPercent`) instead of asking again; one reply instead of a loop.
6. **Unknown Settings page:** an honest `UnknownSettingsPage` failure; nothing is opened.
7. **Settings page names** are matched with the app scoring but exact names first, like apps (Task 6's rule).

## Facts checked before writing this plan (2026-10-15)

- WinRT media session works from Python 3.12 (`winrt-Windows.Media.Control`): it saw a Vivaldi session with title, artist and status.
- `Shell.Application` → `NameSpace("shell:AppsFolder").Items()` lists 238 apps; Store apps have a path `<PackageFamilyName>!<AppId>` (e.g. `Microsoft.WindowsCalculator_8wekyb3d8bbwe!App`). Their display names may be **English** ("Calculator", "Notepad").
- `PackageManager.find_packages_by_user_security_id_package_family_name("", family)` returns the install folder (`C:\Program Files\WindowsApps\Microsoft.WindowsCalculator_11.2607.0.0_x64__8wekyb3d8bbwe`).
- Calculator's process is `CalculatorApp.exe` under that folder, but its visible window is owned by `ApplicationFrameHost.exe`; posting `WM_CLOSE` to that frame window closed the app.
- WMI `WmiMonitorBrightness` reports one monitor (of two) at 100.

---

### Task 1: Percent edge cases (deferred minor #7) and shared level helpers

Fixes: an explicit step of 0 becomes 10 (truthy check), and an out-of-range number is silently ignored (the step falls back to 10). Out-of-range numbers become `Unmatched`, and the skill answers with the valid range. The level arithmetic moves to `skills/pc/levels.py` so brightness (Task 12) reuses it.

**Files:**
- Modify: `src/sazed/nlu/slots/percent.py`, `src/sazed/nlu/slots/target.py`
- Create: `src/sazed/skills/pc/levels.py`
- Modify: `src/sazed/skills/pc/volume.py`, `src/sazed/core/outcomes.py`, `src/sazed/core/persona/definition.py`, `src/sazed/nlu/CLAUDE.md`
- Test: `tests/nlu/test_slot_percent.py`, `tests/nlu/test_slot_target.py`, `tests/skills/test_volume.py`, `tests/runtime/test_assistant_basic.py`

**Interfaces:**
- Produces: `extract_percent(normalized) -> SlotValue | Unmatched | None`; `extract_target(normalized) -> SlotValue | Unmatched | None`; outcome `InvalidPercent(raw: str)` (a Failure); `sazed.skills.pc.levels`: `DEFAULT_STEP = 10`, `int_slot(slots, name) -> int | None`, `invalid_level(slots) -> InvalidPercent | None`, `clamp(n) -> int`, `stepped(current: int, sign: int, slots) -> tuple[int, bool]` (level, absolute), `level_label(default: str, noun: str) -> Callable[[Slots], str]`.

- [ ] **Step 1: Write the failing tests**

In `tests/nlu/test_slot_percent.py`, replace `test_out_of_range_number_is_ignored` with:

```python
def test_out_of_range_number_is_unmatched_so_the_skill_can_explain() -> None:
    assert extract_percent("volume em 150") == Unmatched("percent", "150", None)
```

and add `Unmatched` to the import from `sazed.core.types`.

In `tests/nlu/test_slot_target.py`, remove `"abaixa o volume para 150",  # out of range: ask instead of clamping` from `test_no_level_gives_none`, and add:

```python
def test_out_of_range_level_is_unmatched() -> None:
    assert extract_target("abaixa o volume para 150") == Unmatched("alvo", "150", None)
```

with `from sazed.core.types import SlotValue, Unmatched`.

Append to `tests/skills/test_volume.py`:

```python
def test_an_explicit_step_of_zero_changes_nothing() -> None:
    audio = FakeAudio(volume=50)
    assert VolumeSkill(audio).execute("volume_aumentar", pct(0), CTX) == VolumeChanged(50)
    assert audio.volume == 50


def test_out_of_range_step_is_explained_and_changes_nothing() -> None:
    audio = FakeAudio(volume=50)
    slots = {"percent": Unmatched("percent", "150", None)}
    assert VolumeSkill(audio).execute("volume_aumentar", slots, CTX) == InvalidPercent("150")
    assert audio.volume == 50


def test_out_of_range_level_is_explained_and_changes_nothing() -> None:
    audio = FakeAudio(volume=50)
    slots = {"alvo": Unmatched("alvo", "150", None)}
    assert VolumeSkill(audio).execute("volume_diminuir", slots, CTX) == InvalidPercent("150")
    assert audio.volume == 50


def test_out_of_range_set_is_explained_and_changes_nothing() -> None:
    audio = FakeAudio(volume=50)
    slots = {"percent": Unmatched("percent", "150", None)}
    assert VolumeSkill(audio).execute("volume_definir", slots, CTX) == InvalidPercent("150")
    assert audio.volume == 50
```

with imports `from sazed.core.outcomes import InvalidPercent, Muted, Unmuted, VolumeChanged, VolumeSet` and `from sazed.core.types import SlotValue, Unmatched`.

Append to `tests/runtime/test_assistant_basic.py`:

```python
def test_out_of_range_step_is_explained_instead_of_using_the_default(make: Make) -> None:
    h = make({"aumenta o volume em 150": {"volume_aumentar": 0.97, "volume_definir": 0.70}})
    r = h.say("aumenta o volume em 150")
    assert r.outcome == InvalidPercent("150")
    assert h.audio.volume == 50
    assert "0 a 100" in r.text
```

adding `InvalidPercent` to the `sazed.core.outcomes` import.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/nlu/test_slot_percent.py tests/nlu/test_slot_target.py tests/skills/test_volume.py tests/runtime/test_assistant_basic.py -q`
Expected: FAIL — `ImportError: cannot import name 'InvalidPercent'` (collection error).

- [ ] **Step 3: Implement**

`src/sazed/core/outcomes.py` — add after `ActionFailed`:

```python
@dataclass(frozen=True)
class InvalidPercent:
    """A number outside 0-100 was given for a level or a step."""

    raw: str
```

and extend `Failure = AppNotFound | AppNotRunning | AmbiguousSlot | ActionFailed | InvalidPercent`.

`src/sazed/core/persona/definition.py` — add under "Outcomes: failures":

```python
    "InvalidPercent": (
        "Só consigo ajustar de 0 a 100%, {mestre}. '{raw}' fica fora disso.",
    ),
```

`src/sazed/nlu/slots/percent.py` — change `_value` and the signature:

```python
from sazed.core.types import SlotValue, Unmatched
...
def _value(n: int, raw: str) -> SlotValue | Unmatched:
    # Out of range is "named, but invalid": the skill explains the range instead of guessing.
    return SlotValue("percent", n, raw, 1.0) if 0 <= n <= 100 else Unmatched("percent", raw, None)


def extract_percent(normalized: str) -> SlotValue | Unmatched | None:
```

`src/sazed/nlu/slots/target.py` — handle `Unmatched`:

```python
from sazed.core.types import SlotValue, Unmatched
...
def extract_target(normalized: str) -> SlotValue | Unmatched | None:
    tokens = strip_accents(normalized).split()
    for i, token in enumerate(tokens):
        if token not in _TO:
            continue
        rest = tokens[i + 1 :]
        if rest and rest[0] in _ARTICLES:
            rest = rest[1:]
        found = extract_percent(" ".join(rest))
        # The number must come right after the preposition: "aumenta 10 pra mim" is no level.
        if found is None or not " ".join(rest).startswith(found.raw):
            continue
        if isinstance(found, Unmatched):
            return Unmatched("alvo", found.raw, None)
        return SlotValue("alvo", found.value, found.raw, 1.0)
    return None
```

Create `src/sazed/skills/pc/levels.py`:

```python
"""Level arithmetic shared by volume and brightness: steps, absolute levels, range checks."""

from __future__ import annotations

from collections.abc import Callable

from sazed.core.outcomes import InvalidPercent
from sazed.core.types import Slots, SlotValue, Unmatched

DEFAULT_STEP = 10


def int_slot(slots: Slots, name: str) -> int | None:
    value = slots.get(name)
    return int(value.value) if isinstance(value, SlotValue) else None


def invalid_level(slots: Slots) -> InvalidPercent | None:
    for name in ("percent", "alvo"):
        value = slots.get(name)
        if isinstance(value, Unmatched):
            return InvalidPercent(value.raw)
    return None


def clamp(n: int) -> int:
    return max(0, min(100, n))


def stepped(current: int, sign: int, slots: Slots) -> tuple[int, bool]:
    """The level after an up/down command, and whether it was named as an absolute level."""
    level = int_slot(slots, "alvo")
    if level is not None:
        return clamp(level), True
    step = int_slot(slots, "percent")
    # `is None`, not a truthy check: a step of 0 is a real (if odd) request.
    return clamp(current + sign * (DEFAULT_STEP if step is None else step)), False


def level_label(default: str, noun: str) -> Callable[[Slots], str]:
    def describe(slots: Slots) -> str:
        level = int_slot(slots, "alvo")
        return f"deixar {noun} em {level}%" if level is not None else default

    return describe
```

(`level_label` takes the noun — `"o volume"` or `"o brilho"` — so the confirmation stays correct for both.)

In `src/sazed/skills/pc/volume.py`: delete `DEFAULT_STEP`, `_int`, `_clamp`, `_level_label`, the `Callable` import; import `from sazed.skills.pc.levels import clamp, int_slot, invalid_level, level_label, stepped`; set `describe=level_label("aumentar o volume", "o volume")` / `level_label("diminuir o volume", "o volume")`; `_percent_label` uses `int_slot`; and replace `execute` with:

```python
    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id in ("volume_definir", "volume_aumentar", "volume_diminuir"):
            invalid = invalid_level(slots)
            if invalid is not None:
                return invalid
        if intent_id == "volume_definir":
            percent = int_slot(slots, "percent")
            if percent is None:
                raise ValueError("volume_definir called without its required slot 'percent'")
            self._audio.set_volume(clamp(percent))
            return VolumeSet(clamp(percent))
        if intent_id in ("volume_aumentar", "volume_diminuir"):
            sign = 1 if intent_id == "volume_aumentar" else -1
            level, absolute = stepped(self._audio.get_volume(), sign, slots)
            self._audio.set_volume(level)
            return VolumeSet(level) if absolute else VolumeChanged(level)
        if intent_id == "volume_mudo":
            mute = slots.get("mudo")
            muted = bool(mute.value) if isinstance(mute, SlotValue) else True
            self._audio.set_muted(muted)
            return Muted() if muted else Unmuted()
        raise ValueError(f"unknown intent {intent_id}")
```

In `src/sazed/nlu/CLAUDE.md`, replace the trap line "Numbers outside 0–100 are ignored, so the user is asked again instead of being clamped silently." with:

```markdown
- Numbers outside 0–100 are `Unmatched` (never clamped): the skill answers `InvalidPercent`
  with the valid range. `Unmatched` counts as given, so the policy does not ask again.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS (all; previous count + 7).

- [ ] **Step 5: Discrimination proof**

Mutate `stepped` to `step = int_slot(slots, "percent") or DEFAULT_STEP` (the original truthy bug) and run `uv run pytest tests/skills/test_volume.py -q`.
Expected: `test_an_explicit_step_of_zero_changes_nothing` FAILS (`VolumeChanged(60) != VolumeChanged(50)`). Revert. Create `docs/superpowers/proofs/2026-10-15-sub-project-2a.md` with a `# Discrimination proofs — sub-project 2a` title and a `## Step of zero` section holding the mutation and the failing output.

- [ ] **Step 6: Commit**

```bash
git add src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "fix(volume): keep a step of zero and explain out-of-range numbers"
```

---

### Task 2: Corrections mark the corrected command; a learning-write failure keeps the action's result (deferred minors #5, #6)

**Files:**
- Modify: `src/sazed/runtime/assistant.py`, `src/sazed/core/persona/definition.py`
- Test: `tests/runtime/test_assistant_learning.py`

**Interfaces:**
- Produces: `Prompt.LEARN_FAILED` (value `"learn_failed"`); `Assistant._command_episode: int | None` (episode id of the last executed or not-found command); `Assistant._react(reaction, episode=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/runtime/test_assistant_learning.py`:

```python
def test_correction_marks_the_corrected_command_not_a_later_reply(make: Make) -> None:
    h = make(
        {
            "fecha o chrome": {"abrir_app": 0.93, "fechar_app": 0.80},
            "fechar": {"fechar_app": 0.91, "abrir_app": 0.50},
        }
    )
    h.say("fecha o chrome")  # misfires: opens
    h.say("sim")  # nothing pending: not understood, not remembered
    h.say("não, era pra fechar")
    newest_first = h.store.episodes(3)
    assert newest_first[2].episode.utterance == "fecha o chrome"
    assert newest_first[2].episode.reaction is Reaction.CORRECTED
    assert newest_first[1].episode.reaction is Reaction.NONE


class FailingLearnStore(SqliteCoppermind):
    def learn(self, examples, aliases, now):  # type: ignore[no-untyped-def]
        raise OSError("disk full: secret internals")


def test_a_learning_failure_after_a_confirmed_action_keeps_the_action(make: Make) -> None:
    h = make(LOW_CHROME, store=FailingLearnStore(":memory:"))
    h.say("abre aí o chrome")
    r = h.say("sim")
    assert h.launcher.launched == ["Google Chrome"]
    assert r.outcome == AppOpened("Google Chrome")
    assert "não consegui guardar" in r.text
    assert "secret internals" not in r.text
```

with `from sazed.core.outcomes import AppOpened, ExampleLearned, Forgotten, NothingToForget`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/runtime/test_assistant_learning.py -q`
Expected: FAIL — the first test sees `Reaction.NONE` on the "fecha o chrome" episode (the reaction landed on the "sim" episode); the second sees `ActionFailed('atender a esse pedido')`.

- [ ] **Step 3: Implement**

In `src/sazed/core/persona/definition.py`, add `LEARN_FAILED = "learn_failed"` to `Prompt` and under "Prompts":

```python
    "learn_failed": (
        "Peço desculpas, {mestre}: não consegui guardar isso em minha mente de cobre.",
    ),
```

In `src/sazed/runtime/assistant.py`:

1. In `__init__`, after `self._last_episode: int | None = None`, add `self._command_episode: int | None = None`.
2. In `handle`, replace `self._last_episode = self._record(utterance, turn)` with:

```python
        self._last_episode = self._record(utterance, turn)
        last = self._ctx.last
        if last is not None and self._ctx.last_at == self._now and last.kind is not LastKind.NOT_UNDERSTOOD:
            # This turn ran (or tried to run) a command: a later correction refers to it.
            self._command_episode = self._last_episode
```

3. Replace `_react`:

```python
    def _react(self, reaction: Reaction, episode: int | None = None) -> None:
        target = episode if episode is not None else self._last_episode
        if target is None:
            return
        try:
            self._store.set_reaction(target, reaction)
        except Exception:
            log.exception("could not record the reaction")
```

4. In `_correct`, change all three `self._react(Reaction.CORRECTED)` calls to `self._react(Reaction.CORRECTED, self._command_episode)`.
5. In `_learn`, wrap the write:

```python
        if new_examples or new_aliases:
            try:
                self._store.learn(new_examples, new_aliases, self._now)
            except Exception:
                # The action (if any) already happened; only remembering it failed.
                log.exception("could not write learned items")
                texts.append(self._say(Prompt.LEARN_FAILED))
                return texts, outcome
            for ex in new_examples:
```

Run `uv run ruff format src` (the `handle` condition line is long).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Discrimination proof**

Mutation: in `_correct`, revert the first misfire-branch call to `self._react(Reaction.CORRECTED)`. Run `uv run pytest tests/runtime/test_assistant_learning.py -q -k corrected_command`. Expected FAIL. Revert; record under `## Correction episode` in the proofs file.

- [ ] **Step 6: Commit**

```bash
git add src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "fix(runtime): mark the corrected command and survive a failed learning write"
```

---

### Task 3: Learnable and repeatable intents (deferred minor #8)

`IntentSpec` gains `learnable` (default `True`) and `repeatable` (default `False`). `_learn` is the single gate for examples (confirmations, rephrase offers and corrections all pass through it). Repeat only reruns repeatable intents; otherwise it answers `NothingToRepeat` and is never ranked as a command.

**Files:**
- Modify: `src/sazed/core/skill.py`, `src/sazed/core/outcomes.py`, `src/sazed/core/persona/definition.py`, `src/sazed/runtime/assistant.py`, `src/sazed/skills/pc/volume.py`, `src/sazed/skills/CLAUDE.md`
- Test: `tests/runtime/test_assistant_dialogue.py`, `tests/runtime/test_assistant_learning.py`

**Interfaces:**
- Produces: `sazed.core.skill.always(slots) -> bool`; `IntentSpec.learnable: bool = True`; `IntentSpec.repeatable: bool = False`; outcome `NothingToRepeat()` (Success).

- [ ] **Step 1: Write the failing tests**

Append to `tests/runtime/test_assistant_dialogue.py`:

```python
def test_repeat_does_not_reopen_an_app(make: Make) -> None:
    h = make({"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60}})
    h.say("abre o chrome")
    r = h.say("mais")
    assert h.launcher.launched == ["Google Chrome"]
    assert r.outcome == NothingToRepeat()


def test_bare_more_with_nothing_to_repeat_is_never_ranked(make: Make) -> None:
    h = make({"mais": {"volume_aumentar": 0.99, "volume_diminuir": 0.5}})
    r = h.say("mais")
    assert r.outcome == NothingToRepeat()
    assert h.audio.volume == 50
```

with `from sazed.core.outcomes import AmbiguousSlot, AppOpened, Cancelled, NothingToRepeat, Outcome`.

Append to `tests/runtime/test_assistant_learning.py`:

```python
class GuardedSkill:
    """One unlearnable intent, as power actions will be."""

    id = "guarded"

    def __init__(self) -> None:
        self.ran = 0
        self.intents = (
            IntentSpec("proteger", ("protege tudo",), (), lambda s: "proteger", learnable=False),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        self.ran += 1
        return Cancelled()


def test_confirming_an_unlearnable_intent_learns_nothing(make: Make) -> None:
    guarded = GuardedSkill()
    h = make({"protege aí": {"proteger": 0.80}}, extra_skills=[guarded])
    assert isinstance(h.say("protege aí").decision, Confirm)
    h.say("sim")
    assert guarded.ran == 1
    assert h.store.learned() == []


def test_correcting_towards_an_unlearnable_intent_learns_nothing(make: Make) -> None:
    guarded = GuardedSkill()
    h = make(
        {
            "abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.60},
            "proteger": {"proteger": 0.95},
        },
        extra_skills=[guarded],
    )
    h.say("abre o chrome")
    h.say("não, era pra proteger")
    assert guarded.ran == 1
    assert h.store.learned() == []
```

with imports `from sazed.core.outcomes import AppOpened, Cancelled, ExampleLearned, Forgotten, NothingToForget, Outcome`, `from sazed.core.skill import IntentSpec, SkillContext`, `from sazed.core.types import Slots`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/runtime/test_assistant_dialogue.py tests/runtime/test_assistant_learning.py -q`
Expected: FAIL — `ImportError: cannot import name 'NothingToRepeat'` / `IntentSpec.__init__() got an unexpected keyword argument 'learnable'`.

- [ ] **Step 3: Implement**

`src/sazed/core/skill.py`:

```python
def never(slots: Slots) -> bool:
    return False


def always(slots: Slots) -> bool:
    return True
```

and in `IntentSpec`, after `requires_confirmation`:

```python
    learnable: bool = True
    """False: no phrase is ever learned for this intent (power actions)."""
    repeatable: bool = False
    """True: "de novo"/"mais" may rerun it (level steps, next track). Opt-in on purpose."""
```

`src/sazed/core/outcomes.py`: add

```python
@dataclass(frozen=True)
class NothingToRepeat:
    pass
```

and add `| NothingToRepeat` to `Success` (after `NothingToForget`).

`src/sazed/core/persona/definition.py`: `"NothingToRepeat": ("Não há nada recente para repetir, {mestre}.",),` after `NothingToForget`.

`src/sazed/runtime/assistant.py`:

1. In `_dispatch`, replace the REPEAT branch with:

```python
            if control.kind is ControlKind.REPEAT:
                # Never falls through to ranking: a bare "mais" is not a command by itself.
                if (
                    last is not None
                    and last.kind is LastKind.EXECUTED
                    and last.intent_id is not None
                    and self._specs[last.intent_id][1].repeatable
                ):
                    return self._proceed(last.intent_id, last.slots, u)
                nothing = NothingToRepeat()
                return _Turn([self._say(nothing)], outcome=nothing)
```

2. At the top of `_learn`, before the loop:

```python
        # The single gate for examples: confirmations, offers and corrections all pass here.
        examples = [e for e in examples if self._specs[e[1]][1].learnable]
```

3. Import `NothingToRepeat`.

`src/sazed/skills/pc/volume.py`: add `repeatable=True` to the `volume_aumentar` and `volume_diminuir` `IntentSpec`s.

`src/sazed/skills/CLAUDE.md`, under Traps:

```markdown
- `repeatable` is opt-in: only level steps and track skips set it. "de novo" after anything
  else answers `NothingToRepeat` (opening a second Chrome was a real bug).
- `learnable=False` is enforced in one place, `Assistant._learn`. Power intents use it so a
  learned phrase can never weaken their confirmation.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS (`test_repeat_reruns_the_last_command` still passes: `volume_aumentar` is repeatable).

- [ ] **Step 5: Discrimination proofs**

(a) Remove the `examples = [...]` gate line; run `uv run pytest tests/runtime/test_assistant_learning.py -q -k unlearnable`. Expected: both new tests FAIL. (b) Restore the old REPEAT condition (without `repeatable`); run `-k "reopen or bare_more"` in the dialogue file. Expected FAIL. Revert both; record under `## Learnable gate` and `## Opt-in repeat`.

- [ ] **Step 6: Commit**

```bash
git add src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "feat(core): add learnable and repeatable intent flags; repeat only steps"
```

---

### Task 4: `revisar --rotular` runs the learning safeguards (deferred minor #9)

**Files:**
- Modify: `src/sazed/runtime/admin.py`, `src/sazed/interfaces/cli/main.py`
- Test: `tests/runtime/test_admin.py`, `tests/interfaces/test_cli.py`

**Interfaces:**
- Consumes: `judge_example(scores, target, th, ignore)`, `Verdict`, `IntentSpec.learnable` (Task 3), `settings_from(config)` (wiring).
- Produces: `class LabelResult(Enum): LEARNED, UNKNOWN, ALREADY_KNOWN, CONFLICT, NOT_LEARNABLE`; `label_episode(app, episode_id, intent_id, *, force=False) -> LabelResult`; CLI flag `revisar --rotular EP PEDIDO [--forcar]`.

- [ ] **Step 1: Write the failing tests**

In `tests/runtime/test_admin.py`, change the two existing label tests to the enum (`is LabelResult.LEARNED` / `is LabelResult.UNKNOWN`), import `LabelResult`, and add:

```python
def test_labelling_a_known_phrase_again_is_reported_and_not_duplicated(tmp_path: Path) -> None:
    app = boot(tmp_path)
    first = app.store.record_episode(Episode("liga o navegador", T0, (), {}, "NotUnderstood", None, ""))
    second = app.store.record_episode(Episode("liga o navegador", T0, (), {}, "NotUnderstood", None, ""))
    assert label_episode(app, first, "abrir_app") is LabelResult.LEARNED
    app.index.add("abrir_app", "liga o navegador", app.index.vectorize("liga o navegador"))
    assert label_episode(app, second, "abrir_app") is LabelResult.ALREADY_KNOWN
    assert len(app.store.examples()) == 1


def test_labelling_a_phrase_that_belongs_to_another_intent_needs_force(tmp_path: Path) -> None:
    app = boot(tmp_path)
    episode_id = app.store.record_episode(Episode("abre o chrome", T0, (), {}, "Execute", None, ""))
    assert label_episode(app, episode_id, "fechar_app") is LabelResult.CONFLICT
    assert app.store.examples() == []
    assert label_episode(app, episode_id, "fechar_app", force=True) is LabelResult.LEARNED
    assert [e.intent_id for e in app.store.examples()] == ["fechar_app"]
```

("abre o chrome" is an `abrir_app` seed, so `HashingEmbedder` scores it 1.0 there: a conflict for `fechar_app`. Conversely, if `HashingEmbedder` happens to score "liga o navegador" ≥ `t_conflict` (0.92) against some seed of another intent, the duplicate test returns CONFLICT on its first label: then pick a phrase sharing no words with any seed, e.g. "quero o navegador já", and record it in the ledger.)

Note on the first test: `label_episode` writes to the store but the running index is only refreshed at startup, so the test adds the learned vector to `app.index` to model a restart. Better: make `label_episode` also add the learned example to `app.index`, and drop that line from the test. Do that (see Step 3).

So the first test is:

```python
def test_labelling_a_known_phrase_again_is_reported_and_not_duplicated(tmp_path: Path) -> None:
    app = boot(tmp_path)
    first = app.store.record_episode(Episode("liga o navegador", T0, (), {}, "NotUnderstood", None, ""))
    second = app.store.record_episode(Episode("liga o navegador", T0, (), {}, "NotUnderstood", None, ""))
    assert label_episode(app, first, "abrir_app") is LabelResult.LEARNED
    assert label_episode(app, second, "abrir_app") is LabelResult.ALREADY_KNOWN
    assert len(app.store.examples()) == 1
```

In `tests/interfaces/test_cli.py` add:

```python
def test_review_explains_a_conflict_and_accepts_force(
    boot: Boot, app: SazedApp, capsys: pytest.CaptureFixture[str]
) -> None:
    episode_id = app.store.record_episode(Episode("abre o chrome", T0, (), {}, "Execute", None, ""))
    assert run(boot, ["revisar", "--rotular", str(episode_id), "fechar_app"]) == 1
    assert "--forcar" in capsys.readouterr().out
    assert run(boot, ["revisar", "--rotular", str(episode_id), "fechar_app", "--forcar"]) == 0
    assert [e.intent_id for e in app.store.examples()] == ["fechar_app"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/runtime/test_admin.py tests/interfaces/test_cli.py -q`
Expected: FAIL — `ImportError: cannot import name 'LabelResult'`.

- [ ] **Step 3: Implement**

In `src/sazed/runtime/admin.py`:

```python
from enum import Enum

from sazed.core.learning import Verdict, judge_example
from sazed.runtime.wiring import SazedApp, settings_from


class LabelResult(Enum):
    LEARNED = "learned"
    UNKNOWN = "unknown"
    ALREADY_KNOWN = "already_known"
    CONFLICT = "conflict"
    NOT_LEARNABLE = "not_learnable"


def label_episode(
    app: SazedApp, episode_id: int, intent_id: str, *, force: bool = False
) -> LabelResult:
    specs = {spec.id: spec for skill in app.skills for spec in skill.intents}
    stored = app.store.episode(episode_id)
    if stored is None or intent_id not in specs:
        return LabelResult.UNKNOWN
    if not specs[intent_id].learnable:
        return LabelResult.NOT_LEARNABLE
    text = normalize(stored.episode.utterance)
    # The same safeguards as live learning (spec §5.2): validate before writing.
    verdict = judge_example(
        app.index.scores(text), intent_id, settings_from(app.config).learning
    )
    if verdict is Verdict.DUPLICATE:
        return LabelResult.ALREADY_KNOWN
    if verdict is Verdict.CONFLICT and not force:
        return LabelResult.CONFLICT
    vector = app.index.vectorize(text)
    app.store.learn([NewExample(text, intent_id, vector, "review")], [], app.clock())
    app.index.add(intent_id, text, vector)
    return LabelResult.LEARNED
```

In `src/sazed/interfaces/cli/main.py`: add `review.add_argument("--forcar", action="store_true", help="guarda mesmo se parecer outro pedido")`, import `LabelResult`, and replace the `--rotular` branch of `_review`:

```python
    if args.rotular:
        episode, intent = args.rotular
        result = (
            label_episode(app, int(episode), intent, force=args.forcar)
            if episode.isdigit()
            else LabelResult.UNKNOWN
        )
        if result is LabelResult.LEARNED:
            print("Guardado em minha mente de cobre.")
            return 0
        if result is LabelResult.ALREADY_KNOWN:
            print("Isso eu já sabia, Mestre.")
            return 0
        if result is LabelResult.CONFLICT:
            print("Essa frase se parece com outro pedido que conheço. Use --forcar para guardar mesmo assim.")
            return 1
        if result is LabelResult.NOT_LEARNABLE:
            print("Esse pedido nunca é aprendido: sempre pedirei confirmação antes.")
            return 1
        print("Não consegui rotular. Pedidos válidos:")
        for intent_id, description in intent_rows(app):
            print(f"  {intent_id:<16} {description}")
        return 1
```

Run `uv run ruff format src tests`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Discrimination proof**

Mutation: skip the `judge_example` call (treat every verdict as SAVE). Run `uv run pytest tests/runtime/test_admin.py -q`. Expected: the duplicate and conflict tests FAIL. Revert; record under `## Review safeguards`.

- [ ] **Step 6: Commit**

```bash
git add src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "fix(admin): run dedupe and conflict safeguards when labelling episodes"
```

---

### Task 5: Config — sites and search engines

**Files:**
- Modify: `src/sazed/runtime/config.py`
- Test: `tests/runtime/test_config.py`

**Interfaces:**
- Produces: `BUILTIN_SITES: dict[str, str]`, `BUILTIN_ENGINES: dict[str, str]`, `merge_named(builtin, user) -> dict[str, str]`, `SearchConfig(default: str, engines: dict[str, str])` with `effective_engines()`, `Config.sites: dict[str, str]`, `Config.search: SearchConfig`, `Config.effective_sites()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/runtime/test_config.py` (it already has `write(tmp_path, text)`-style helpers; if not, use this one):

```python
from sazed.runtime.config import BUILTIN_ENGINES, BUILTIN_SITES, Config, ConfigError, load_config


def _load(tmp_path: Path, text: str) -> Config:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return load_config(path)


def test_builtin_sites_and_engines_are_there_by_default() -> None:
    config = Config()
    assert config.effective_sites()["YouTube"] == "https://www.youtube.com"
    assert set(config.search.effective_engines()) == set(BUILTIN_ENGINES)
    assert config.search.default == "Google"


def test_a_user_site_overrides_a_builtin_ignoring_case_and_accents(tmp_path: Path) -> None:
    config = _load(tmp_path, '[sites]\nyoutube = "https://m.youtube.com"\nmeu blog = "https://exemplo.com"\n')
    sites = config.effective_sites()
    assert sites["youtube"] == "https://m.youtube.com"
    assert "YouTube" not in sites
    assert sites["meu blog"] == "https://exemplo.com"
    assert len(sites) == len(BUILTIN_SITES) + 1


@pytest.mark.parametrize(
    ("text", "where", "message"),
    [
        ('[sites]\nnotas = "file:///C:/notas.txt"\n', "sites.notas", "http"),
        ('[sites]\nnotas = "C:/notas.exe"\n', "sites.notas", "http"),
        ('[search.engines]\nbing = "https://bing.com/search"\n', "search.engines.bing", "{q}"),
        ('[search.engines]\nbing = "https://bing.com/?q={q}&r={q}"\n', "search.engines.bing", "{q}"),
        ('[search]\ndefault = "altavista"\n', "search", "altavista"),
        ('[sites]\n"  " = "https://exemplo.com"\n', "sites", "vazio"),
    ],
)
def test_invalid_sites_and_engines_stop_startup_in_pt_br(
    tmp_path: Path, text: str, where: str, message: str
) -> None:
    with pytest.raises(ConfigError) as err:
        _load(tmp_path, text)
    assert f"- {where}:" in str(err.value)
    assert message in str(err.value)


def test_default_engine_matches_ignoring_case_and_accents(tmp_path: Path) -> None:
    assert _load(tmp_path, '[search]\ndefault = "wikipedia"\n').search.default == "wikipedia"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/runtime/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'BUILTIN_ENGINES'`.

- [ ] **Step 3: Implement**

In `src/sazed/runtime/config.py` add imports `from typing import Annotated, Any` and `from pydantic import AfterValidator, field_validator`, `from sazed.nlu.normalize import normalize, strip_accents`, then:

```python
BUILTIN_SITES: dict[str, str] = {
    "YouTube": "https://www.youtube.com",
    "Gmail": "https://mail.google.com",
    "GitHub": "https://github.com",
    "WhatsApp Web": "https://web.whatsapp.com",
    "Netflix": "https://www.netflix.com",
    "Google Drive": "https://drive.google.com",
    "Google Maps": "https://www.google.com/maps",
    "Wikipédia": "https://pt.wikipedia.org",
}
BUILTIN_ENGINES: dict[str, str] = {
    "Google": "https://www.google.com/search?q={q}",
    "YouTube": "https://www.youtube.com/results?search_query={q}",
    "Wikipédia": "https://pt.wikipedia.org/w/index.php?search={q}",
}


def name_key(name: str) -> str:
    return strip_accents(normalize(name))


def _http_url(value: str) -> str:
    # A typo here must never make Sazed run a local file: only web addresses are allowed.
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError("deve começar com http:// ou https://")
    return value


def _search_template(value: str) -> str:
    _http_url(value)
    if value.count("{q}") != 1:
        raise ValueError("deve conter {q} exatamente uma vez (o lugar da pesquisa)")
    return value


HttpUrl = Annotated[str, AfterValidator(_http_url)]
SearchTemplate = Annotated[str, AfterValidator(_search_template)]


def merge_named(builtin: dict[str, str], user: dict[str, str]) -> dict[str, str]:
    """User entries replace built-ins with the same name, ignoring case and accents."""
    merged = {name_key(k): (k, v) for k, v in builtin.items()}
    for k, v in user.items():
        merged[name_key(k)] = (k, v)
    return dict(merged.values())


def _names_not_blank(value: dict[str, str]) -> dict[str, str]:
    if any(not name_key(k) for k in value):
        raise ValueError("nomes não podem ficar vazios")
    return value


class SearchConfig(_Section):
    default: str = Field("Google", min_length=1)
    engines: dict[str, SearchTemplate] = Field(default_factory=dict)

    _check_names = field_validator("engines")(classmethod(lambda cls, v: _names_not_blank(v)))

    def effective_engines(self) -> dict[str, str]:
        return merge_named(BUILTIN_ENGINES, self.engines)

    @model_validator(mode="after")
    def _default_is_known(self) -> SearchConfig:
        if name_key(self.default) not in {name_key(k) for k in self.effective_engines()}:
            raise ValueError(f"'{self.default}' não é um buscador conhecido")
        return self
```

and in `Config`, after `aliases`:

```python
    sites: dict[str, HttpUrl] = Field(default_factory=dict)
    search: SearchConfig = Field(default_factory=SearchConfig)

    @field_validator("sites")
    @classmethod
    def _site_names(cls, value: dict[str, str]) -> dict[str, str]:
        return _names_not_blank(value)

    def effective_sites(self) -> dict[str, str]:
        return merge_named(BUILTIN_SITES, self.sites)
```

If the lambda-based validator on `SearchConfig` does not type-check under mypy, write it as a normal `@field_validator("engines") @classmethod def _engine_names(cls, value): return _names_not_blank(value)` like `Config._site_names`. (`config.py` is outside mypy's strict scope, but keep it clean.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS. If the "sites" blank-name case reports its location as `sites` with a different suffix, adjust only the `where` value in the test after reading the actual message — the message must stay pt-BR.

- [ ] **Step 5: Discrimination proof**

Mutation: make `_http_url` return `value` without the check. Run `uv run pytest tests/runtime/test_config.py -q -k invalid`. Expected: both `sites.notas` cases FAIL. Revert; record under `## Site URL scheme`.

- [ ] **Step 6: Commit**

```bash
git add src/sazed/runtime/config.py tests/runtime/test_config.py docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "feat(config): add validated sites and search engines"
```

---

### Task 6: App catalog kinds, sites, merging and the exact-name rule

**Files:**
- Modify: `src/sazed/skills/pc/apps.py`, `src/sazed/core/outcomes.py`, `src/sazed/core/persona/definition.py`, `src/sazed/nlu/slots/app.py`, `src/sazed/adapters/windows/catalog.py`, `tests/fakes/ports.py`
- Test: `tests/skills/test_apps.py`, `tests/nlu/test_slot_app.py`, `tests/adapters/test_windows_pure.py`

**Interfaces:**
- Produces: `AppKind = Literal["lnk", "store", "site"]`; `AppEntry(name, target, shortcut, kind: AppKind = "lnk")`; `merge_entries(*groups: Sequence[AppEntry]) -> list[AppEntry]` (lnk beats store beats site by case-folded name); `CombinedCatalog(parts: Sequence[AppCatalog])`; `StaticCatalog(entries: Sequence[AppEntry])`; `site_entries(sites: Mapping[str, str]) -> list[AppEntry]`; `DEFAULT_APP_ALIASES: dict[str, str]`; outcome `CannotCloseSite(app: str)` (Failure); `catalog.is_excluded(name) -> bool`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/nlu/test_slot_app.py`:

```python
def test_an_exact_name_wins_over_a_longer_name_containing_it() -> None:
    names = ["WhatsApp", "WhatsApp Web"]
    assert extract_app("abre o whatsapp", names, {}) == SlotValue(
        "app", "WhatsApp", "whatsapp", 1.0, exact=True
    )
    assert extract_app("abre o whatsapp web", names, {}) == SlotValue(
        "app", "WhatsApp Web", "whatsapp web", 1.0, exact=True
    )
```

Append to `tests/skills/test_apps.py`:

```python
from sazed.core.outcomes import CannotCloseSite
from sazed.skills.pc.apps import AppEntry, CombinedCatalog, StaticCatalog, merge_entries, site_entries


def app(name: str) -> dict[str, SlotValue]:
    return {"app": SlotValue("app", name, name.lower(), 1.0, exact=True)}


def test_merge_prefers_installed_over_store_over_site() -> None:
    lnk = [AppEntry("WhatsApp", "C:/w.exe", "C:/w.lnk")]
    store = [AppEntry("whatsapp", "C:/WindowsApps/W", "shell:AppsFolder\\W!App", "store")]
    sites = site_entries({"WhatsApp": "https://web.whatsapp.com", "YouTube": "https://youtube.com"})
    merged = merge_entries(sites, store, lnk)
    assert [(e.name, e.kind) for e in merged] == [("WhatsApp", "lnk"), ("YouTube", "site")]


def test_opening_a_site_launches_its_entry() -> None:
    launcher = FakeLauncher()
    catalog = CombinedCatalog([StaticCatalog(site_entries({"YouTube": "https://youtube.com"}))])
    skill = AppsSkill(catalog, launcher)
    assert skill.execute("abrir_app", app("YouTube"), CTX) == AppOpened("YouTube")
    assert launcher.launched == ["YouTube"]


def test_closing_a_site_is_honestly_refused() -> None:
    launcher = FakeLauncher(running={"YouTube": 1})
    catalog = StaticCatalog(site_entries({"YouTube": "https://youtube.com"}))
    skill = AppsSkill(catalog, launcher)
    assert skill.execute("fechar_app", app("YouTube"), CTX) == CannotCloseSite("YouTube")
    assert launcher.closed == []
```

(`test_apps.py` already defines `CTX` and imports `SlotValue`, `AppOpened` and `FakeLauncher`; the `app(name)` helper above is new.)

Append to `tests/adapters/test_windows_pure.py`:

```python
from sazed.adapters.windows.catalog import is_excluded


@pytest.mark.parametrize(
    "name",
    ["Desinstalação do Foo", "Desinstalar Bar", "Uninstall Baz", "Leia-me", "Ajuda do Qux"],
)
def test_uninstallers_and_docs_are_excluded(name: str) -> None:
    assert is_excluded(name)


def test_a_normal_app_is_not_excluded() -> None:
    assert not is_excluded("Visual Studio Code")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/nlu/test_slot_app.py tests/skills/test_apps.py tests/adapters/test_windows_pure.py -q`
Expected: FAIL — exact-name test gets `Ambiguous`; imports of `CannotCloseSite`, `merge_entries`, `is_excluded` fail.

- [ ] **Step 3: Implement**

`src/sazed/nlu/slots/app.py` — after the alias check in `extract_app`:

```python
    # token_set_ratio scores a contained name 100 ("whatsapp" in "whatsapp web"), so an
    # exact name must be decided before fuzzy scoring or it ties with every longer name.
    exact = [n for n in names if _key(n) == query]
    if len(exact) == 1:
        return SlotValue("app", exact[0], query, 1.0, exact=True)
```

`src/sazed/core/outcomes.py`: add

```python
@dataclass(frozen=True)
class CannotCloseSite:
    app: str
```

and include it in `Failure`. Persona: `"CannotCloseSite": ("Não consigo fechar abas do navegador, {mestre}. {app} fica por sua conta.",),`.

`src/sazed/skills/pc/apps.py`:

```python
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

AppKind = Literal["lnk", "store", "site"]
_KIND_RANK: dict[str, int] = {"lnk": 0, "store": 1, "site": 2}


@dataclass(frozen=True)
class AppEntry:
    name: str
    target: str
    """lnk: the executable; store: the package install folder ("" if unknown); site: the URL."""
    shortcut: str
    """What is opened to launch it: a .lnk path, `shell:AppsFolder\\<AUMID>`, or the URL."""
    kind: AppKind = "lnk"


def merge_entries(*groups: Sequence[AppEntry]) -> list[AppEntry]:
    """One entry per name (case-insensitive): an installed app beats a Store app beats a site."""
    best: dict[str, AppEntry] = {}
    for entry in (e for group in groups for e in group):
        key = entry.name.strip().casefold()
        current = best.get(key)
        if current is None or _KIND_RANK[entry.kind] < _KIND_RANK[current.kind]:
            best[key] = entry
    return sorted(best.values(), key=lambda e: e.name.casefold())


class StaticCatalog:
    def __init__(self, entries: Sequence[AppEntry]) -> None:
        self._entries = list(entries)

    def entries(self) -> Sequence[AppEntry]:
        return list(self._entries)


class CombinedCatalog:
    def __init__(self, parts: Sequence[AppCatalog]) -> None:
        self._parts = list(parts)

    def entries(self) -> Sequence[AppEntry]:
        return merge_entries(*(part.entries() for part in self._parts))


def site_entries(sites: Mapping[str, str]) -> list[AppEntry]:
    return [AppEntry(name, url, url, "site") for name, url in sites.items()]


# Store apps can show English names ("Calculator") on a pt-BR desktop. Wiring adds each alias
# only when its target exists in the catalog; config aliases still override them.
DEFAULT_APP_ALIASES: dict[str, str] = {
    "calculadora": "Calculator",
    "bloco de notas": "Notepad",
    "fotos": "Photos",
    "camera": "Camera",
    "relogio": "Clock",
    "loja": "Microsoft Store",
    "ferramenta de captura": "Snipping Tool",
}
```

Add `"abre o youtube"`, `"abre o gmail"`, `"abre o site do github"` to `OPEN_EXAMPLES` (sites go through `abrir_app`).

In `AppsSkill`: `_close_needs_confirmation` returns `False` when `entry.kind == "site"`; in `execute`, at the start of the `fechar_app` branch:

```python
        if intent_id == "fechar_app":
            if entry.kind == "site":
                return CannotCloseSite(entry.name)
```

`src/sazed/adapters/windows/catalog.py`:

```python
from sazed.nlu.normalize import strip_accents

EXCLUDED_WORDS = ("uninstall", "desinstal", "remover", "readme", "leia-me", "help", "ajuda")


def is_excluded(name: str) -> bool:
    key = strip_accents(name.strip().lower())
    return any(word in key for word in EXCLUDED_WORDS)
```

and in `build_entries` use `if is_excluded(name): continue`. Update the module docstring to "Installed apps from Start Menu shortcuts (.lnk). Store apps: see store.py."

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Discrimination proof**

Mutation: delete the exact-name block in `extract_app`. Run `uv run pytest tests/nlu/test_slot_app.py -q`. Expected: the exact-name test FAILS with `Ambiguous(...)`. Revert; record under `## Exact app name`.

- [ ] **Step 6: Commit**

```bash
git add src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "feat(apps): open sites through the app catalog; exact names beat longer ones"
```

---

### Task 7: Store apps — catalog, launching and closing

**Files:**
- Create: `src/sazed/adapters/windows/store.py`
- Modify: `src/sazed/adapters/windows/launcher.py`, `pyproject.toml`, `uv.lock`, `src/sazed/adapters/CLAUDE.md`
- Test: `tests/adapters/test_windows_pure.py`, `tests/adapters/test_windows_integration.py`

**Interfaces:**
- Consumes: `AppEntry(kind=...)`, `is_excluded` (Task 6).
- Produces: `build_store_entries(items: Iterable[tuple[str, str]], folder_of: Callable[[str], str | None]) -> list[AppEntry]`; `StoreCatalog()` (`entries()`); `entry_matcher(entry) -> Callable[[str | None], bool]`; `root_pids(processes, matches: Callable[[str | None], bool]) -> list[int]` (signature change); `WindowInfo(hwnd: int, pid: int, child_pids: frozenset[int])`; `windows_to_close(windows: Sequence[WindowInfo], pids: set[int]) -> list[int]`.

- [ ] **Step 1: Add the dependencies**

Run:

```bash
uv add "winrt-runtime; sys_platform == 'win32'" "winrt-Windows.Foundation; sys_platform == 'win32'" "winrt-Windows.Foundation.Collections; sys_platform == 'win32'" "winrt-Windows.Management.Deployment; sys_platform == 'win32'" "winrt-Windows.ApplicationModel; sys_platform == 'win32'" "winrt-Windows.Storage; sys_platform == 'win32'"
uv run python -c "from winrt.windows.management.deployment import PackageManager; print('ok')"
```

Expected: `ok`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/adapters/test_windows_pure.py`:

```python
from sazed.adapters.windows.launcher import WindowInfo, entry_matcher, root_pids, windows_to_close
from sazed.adapters.windows.store import build_store_entries
from sazed.skills.pc.apps import AppEntry

CALC_FOLDER = r"C:\Program Files\WindowsApps\Microsoft.WindowsCalculator_11.2607.0.0_x64__8wekyb3d8bbwe"


def test_store_entries_come_from_package_app_ids_only() -> None:
    items = [
        ("Calculator", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
        ("Google Chrome", "Chrome"),
        ("Configurar Java", r"{6D809377-6AF0-444B-8957-A3773F02200E}\Java\bin\javacpl.exe"),
        ("Desinstalar Foo", "Foo.Bar_1234567890abc!App"),
    ]
    folders = {"Microsoft.WindowsCalculator_8wekyb3d8bbwe": CALC_FOLDER}
    assert build_store_entries(items, folders.get) == [
        AppEntry(
            "Calculator",
            CALC_FOLDER,
            "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
            "store",
        )
    ]


def test_a_store_app_without_a_known_folder_can_still_be_opened() -> None:
    (entry,) = build_store_entries([("WhatsApp", "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App")], lambda f: None)
    assert entry.target == ""
    assert entry.shortcut.endswith("!App")


def test_a_store_entry_matches_executables_inside_its_folder_only() -> None:
    entry = AppEntry("Calculator", CALC_FOLDER, "shell:AppsFolder\\X!App", "store")
    matches = entry_matcher(entry)
    assert matches(CALC_FOLDER + r"\CalculatorApp.exe")
    assert not matches(CALC_FOLDER + "0" + r"\CalculatorApp.exe")  # a sibling folder
    assert not matches(r"C:\Windows\System32\ApplicationFrameHost.exe")
    assert not matches(None)


def test_a_store_entry_without_folder_matches_nothing() -> None:
    assert not entry_matcher(AppEntry("W", "", "shell:AppsFolder\\W!App", "store"))(r"C:\x.exe")


def test_a_site_matches_no_process() -> None:
    site = AppEntry("YouTube", "https://youtube.com", "https://youtube.com", "site")
    assert not entry_matcher(site)(r"C:\Program Files\Vivaldi\vivaldi.exe")


def test_root_pids_takes_a_matcher() -> None:
    entry = AppEntry("Calculator", CALC_FOLDER, "shell:AppsFolder\\X!App", "store")
    procs = [(10, 1, CALC_FOLDER + r"\CalculatorApp.exe"), (11, 10, CALC_FOLDER + r"\Helper.exe")]
    assert root_pids(procs, entry_matcher(entry)) == [10]


def test_a_frame_window_hosting_the_app_is_closed() -> None:
    windows = [
        WindowInfo(hwnd=1, pid=900, child_pids=frozenset({900, 4376})),  # ApplicationFrameHost
        WindowInfo(hwnd=2, pid=900, child_pids=frozenset({900, 5000})),  # another UWP app
        WindowInfo(hwnd=3, pid=4376, child_pids=frozenset()),  # the app's own window
        WindowInfo(hwnd=4, pid=7, child_pids=frozenset()),
    ]
    assert windows_to_close(windows, {4376}) == [1, 3]
```

Update the existing `root_pids` tests in this file to pass `entry_matcher(AppEntry("X", target, "x.lnk"))` instead of the bare target string (same expected values).

Append to `tests/adapters/test_windows_integration.py`:

```python
def test_store_calculator_opens_and_closes() -> None:
    from sazed.adapters.windows.store import StoreCatalog

    entry = next(e for e in StoreCatalog().entries() if e.name == "Calculator")
    launcher = WindowsLauncher()
    launcher.launch(entry)
    try:
        assert wait_until(lambda: launcher.instances(entry) >= 1)
        assert launcher.close(entry) >= 1
        assert wait_until(lambda: launcher.instances(entry) == 0)
    finally:
        if launcher.instances(entry):
            launcher.close(entry)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/adapters/test_windows_pure.py -q`
Expected: FAIL — `ImportError: cannot import name 'WindowInfo'` / `No module named 'sazed.adapters.windows.store'`.

- [ ] **Step 4: Implement**

Create `src/sazed/adapters/windows/store.py`:

```python
"""Store (UWP/MSIX) apps from shell:AppsFolder, with their package install folders."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Iterator, Sequence

from sazed.adapters.windows.catalog import is_excluded
from sazed.skills.pc.apps import AppEntry

log = logging.getLogger(__name__)

# "<PackageFamilyName>!<AppId>"; the family name ends in a 13-char publisher id.
_AUMID = re.compile(r"^(?P<family>[^\\/!]+_[a-z0-9]{13})![^\\/!]+$", re.IGNORECASE)


def build_store_entries(
    items: Iterable[tuple[str, str]], folder_of: Callable[[str], str | None]
) -> list[AppEntry]:
    """(display name, AppsFolder path) → Store entries. Desktop apps in the folder are skipped:
    their .lnk entries come from StartMenuCatalog."""
    entries = []
    for name, path in items:
        match = _AUMID.match(path)
        if match is None or is_excluded(name):
            continue
        folder = folder_of(match["family"]) or ""
        entries.append(AppEntry(name.strip(), folder, f"shell:AppsFolder\\{path}", "store"))
    return sorted(entries, key=lambda e: e.name.casefold())


def _package_folder(family: str) -> str | None:
    try:
        from winrt.windows.management.deployment import PackageManager

        for package in PackageManager().find_packages_by_user_security_id_package_family_name(
            "", family
        ):
            return str(package.installed_location.path)
    except Exception:
        log.warning("could not resolve the install folder of %s", family, exc_info=True)
    return None


class StoreCatalog:
    def __init__(self) -> None:
        self._entries: list[AppEntry] | None = None

    def entries(self) -> Sequence[AppEntry]:
        if self._entries is None:
            self._entries = build_store_entries(self._scan(), _package_folder)
        return list(self._entries)

    def _scan(self) -> Iterator[tuple[str, str]]:
        import win32com.client

        folder = win32com.client.Dispatch("Shell.Application").NameSpace("shell:AppsFolder")
        for item in folder.Items():
            yield str(item.Name), str(item.Path)
```

In `src/sazed/adapters/windows/launcher.py`:

```python
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _under(exe: str | None, folder: str) -> bool:
    return exe is not None and bool(folder) and _norm(exe).startswith(_norm(folder) + os.sep)


def entry_matcher(entry: AppEntry) -> Callable[[str | None], bool]:
    """Which running executables belong to `entry`."""
    if entry.kind == "site":
        return lambda exe: False
    if entry.kind == "store":
        return lambda exe: _under(exe, entry.target)
    return lambda exe: _matches(exe, entry.target)


def root_pids(
    processes: Iterable[tuple[int, int, str | None]], matches: Callable[[str | None], bool]
) -> list[int]:
    """PIDs of matching processes whose parent does not also match (one per app instance)."""
    matching = {pid: ppid for pid, ppid, exe in processes if matches(exe)}
    return sorted(pid for pid, ppid in matching.items() if ppid not in matching)


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    child_pids: frozenset[int]


def windows_to_close(windows: Sequence[WindowInfo], pids: set[int]) -> list[int]:
    """Top-level windows owned by the app, or hosting it: Store apps draw inside an
    ApplicationFrameHost.exe frame whose child window belongs to the app's process."""
    return [w.hwnd for w in windows if w.pid in pids or w.child_pids & pids]
```

Rewrite `_matches` to use `_norm`/`_under` (behaviour unchanged):

```python
def _matches(exe: str | None, target: str) -> bool:
    if exe is not None and _norm(exe) == _norm(target):
        return True
    if os.path.basename(target).lower() not in _LAUNCHER_NAMES:
        return False
    return _under(exe, os.path.dirname(target))
```

and replace `_same_path` usages accordingly (delete `_same_path`). Then `WindowsLauncher`:

```python
class WindowsLauncher:
    def launch(self, entry: AppEntry) -> None:
        os.startfile(entry.shortcut)  # type: ignore[attr-defined]  # Windows only

    def instances(self, entry: AppEntry) -> int:
        return len(root_pids(_snapshot(), entry_matcher(entry)))

    def close(self, entry: AppEntry) -> int:
        import win32con
        import win32gui
        import win32process

        matches = entry_matcher(entry)
        pids = {pid for pid, _, exe in _snapshot() if matches(exe)}
        if not pids:
            return 0
        windows: list[WindowInfo] = []

        def pid_of(hwnd: int) -> int:
            return int(win32process.GetWindowThreadProcessId(hwnd)[1])

        def on_window(hwnd: int, _: object) -> bool:
            if win32gui.IsWindowVisible(hwnd):
                children: set[int] = set()

                def on_child(child: int, __: object) -> bool:
                    children.add(pid_of(child))
                    return True

                try:
                    win32gui.EnumChildWindows(hwnd, on_child, None)
                except win32gui.error:
                    pass  # no children
                windows.append(WindowInfo(hwnd, pid_of(hwnd), frozenset(children)))
            return True

        win32gui.EnumWindows(on_window, None)
        targets = windows_to_close(windows, pids)
        for hwnd in targets:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return len(targets)
```

`src/sazed/adapters/CLAUDE.md`: replace the Store trap with:

```markdown
- Store apps come from `shell:AppsFolder` (`store.py`); their names may be English
  ("Calculator"), so `DEFAULT_APP_ALIASES` maps pt-BR names. Their visible window is owned by
  `ApplicationFrameHost.exe`, not the app: `windows_to_close` also closes frames hosting a
  child window of the app's process.
- WinRT calls are async: adapters run them to completion with `asyncio.run` inside the method.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -q` then `uv run pytest -m windows -q -k "calculator or charmap"`
Expected: PASS; the Calculator test opens and closes Calculator.

- [ ] **Step 6: Discrimination proof**

Mutation: `windows_to_close` returns `[w.hwnd for w in windows if w.pid in pids]` (the old behaviour). Run the pure test (FAIL: `[3] != [1, 3]`) and `uv run pytest -m windows -q -k calculator` (FAIL: Calculator stays open — close it by hand if needed). Revert; record under `## Store app frame windows`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "feat(apps): catalog, open and close Store apps"
```

---
### Task 8: Web search (`pesquisar`) and the URI opener

**Files:**
- Create: `src/sazed/skills/pc/web.py`, `src/sazed/nlu/slots/search.py`, `src/sazed/adapters/windows/opener.py`
- Modify: `src/sazed/core/outcomes.py`, `src/sazed/core/persona/definition.py`, `src/sazed/runtime/extractors.py`, `tests/support/harness.py`, `tests/fakes/ports.py`
- Test: `tests/skills/test_web.py`, `tests/nlu/test_slot_search.py`, `tests/adapters/test_windows_pure.py`, `tests/fakes/test_ports.py`, `tests/runtime/test_assistant_dialogue.py`

**Interfaces:**
- Consumes: `BUILTIN_ENGINES` (Task 5).
- Produces: `UriOpener` protocol (`open(uri: str) -> None`); `search_url(template: str, query: str) -> str`; `WebSkill(opener, engines: Mapping[str, str], default: str)` with intent `pesquisar` (slots `consulta` required, `site` optional); outcome `SearchOpened(query: str, engine: str)`; `extract_query(normalized, engines: Sequence[str]) -> SlotValue | None` (slot `consulta`); `extract_engine(normalized, engines) -> SlotValue | None` (slot `site`); `build_extractors(app_names, engine_names=(), page_names=())`; `FakeOpener` (`opened: list[str]`); `ShellOpener`; `is_allowed_uri(uri) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/nlu/test_slot_search.py`:

```python
import pytest

from sazed.core.types import SlotValue
from sazed.nlu.slots.search import extract_engine, extract_query

ENGINES = ["Google", "YouTube", "Wikipédia"]


@pytest.mark.parametrize(
    ("text", "query"),
    [
        ("pesquisa receitas de bolo", "receitas de bolo"),
        ("pesquisa lofi no youtube", "lofi"),
        ("procura sobre buracos negros na wikipedia", "buracos negros"),
        ("sazed busca por preço do dólar", "preço do dólar"),
        ("pesquisa pra mim horário do jogo", "horário do jogo"),
        ("lofi", "lofi"),  # a bare answer to "O que devo pesquisar?"
    ],
)
def test_query_is_the_text_after_the_trigger_without_the_engine(text: str, query: str) -> None:
    assert extract_query(text, ENGINES) == SlotValue("consulta", query, query, 1.0)


@pytest.mark.parametrize("text", ["pesquisa", "pesquisa no youtube", "busca por", ""])
def test_no_query_gives_none_so_sazed_asks(text: str) -> None:
    assert extract_query(text, ENGINES) is None


def test_engine_is_the_trailing_place() -> None:
    assert extract_engine("pesquisa lofi no youtube", ENGINES) == SlotValue(
        "site", "YouTube", "youtube", 1.0
    )
    assert extract_engine("procura gatos na wikipedia", ENGINES) == SlotValue(
        "site", "Wikipédia", "wikipedia", 1.0
    )


def test_a_place_in_the_middle_is_part_of_the_query() -> None:
    assert extract_engine("pesquisa vídeos no youtube de gatos", ENGINES) is None
```

Create `tests/skills/test_web.py`:

```python
from datetime import datetime

import pytest

from fakes.ports import FakeOpener
from sazed.core.outcomes import SearchOpened
from sazed.core.skill import SkillContext
from sazed.core.types import SlotValue
from sazed.runtime.config import BUILTIN_ENGINES
from sazed.skills.pc.web import WebSkill, search_url

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("receitas de bolo", "https://x/?q=receitas+de+bolo"),
        ("pão & café", "https://x/?q=p%C3%A3o+%26+caf%C3%A9"),
        ("c# #1", "https://x/?q=c%23+%231"),
        ("a/b?c=d", "https://x/?q=a%2Fb%3Fc%3Dd"),
    ],
)
def test_search_url_encodes_the_whole_query(query: str, expected: str) -> None:
    assert search_url("https://x/?q={q}", query) == expected


def slots(query: str, site: str | None = None) -> dict[str, SlotValue]:
    found = {"consulta": SlotValue("consulta", query, query, 1.0)}
    if site is not None:
        found["site"] = SlotValue("site", site, site.lower(), 1.0)
    return found


def test_default_engine_is_used_without_a_place() -> None:
    opener = FakeOpener()
    skill = WebSkill(opener, BUILTIN_ENGINES, "google")
    assert skill.execute("pesquisar", slots("lofi"), CTX) == SearchOpened("lofi", "Google")
    assert opener.opened == ["https://www.google.com/search?q=lofi"]


def test_named_engine_is_used() -> None:
    opener = FakeOpener()
    WebSkill(opener, BUILTIN_ENGINES, "Google").execute("pesquisar", slots("lofi", "YouTube"), CTX)
    assert opener.opened == ["https://www.youtube.com/results?search_query=lofi"]
```

Append to `tests/runtime/test_assistant_dialogue.py`:

```python
def test_search_without_a_query_asks_and_takes_a_bare_answer(make: Make) -> None:
    h = make({"pesquisa no youtube": {"pesquisar": 0.97, "abrir_app": 0.5}})
    r = h.say("pesquisa no youtube")
    assert isinstance(r.decision, AskSlot)
    assert "O que devo pesquisar?" in r.text
    h.say("lofi")
    assert h.opener.opened == ["https://www.youtube.com/results?search_query=lofi"]
```

Append to `tests/adapters/test_windows_pure.py`:

```python
from sazed.adapters.windows.opener import is_allowed_uri


@pytest.mark.parametrize(
    "uri",
    [
        "https://www.youtube.com",
        "http://exemplo.com",
        "ms-settings:bluetooth",
        "ms-screenclip:",
        "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
    ],
)
def test_allowed_uris(uri: str) -> None:
    assert is_allowed_uri(uri)


@pytest.mark.parametrize(
    "uri", ["C:\\Windows\\System32\\cmd.exe", "file:///C:/x.bat", "calc", "javascript:alert(1)"]
)
def test_anything_else_is_refused(uri: str) -> None:
    assert not is_allowed_uri(uri)
```

Append to `tests/fakes/test_ports.py`:

```python
from fakes.ports import FakeOpener


def test_fake_opener_records_what_was_opened() -> None:
    opener = FakeOpener()
    opener.open("https://a")
    opener.open("ms-settings:sound")
    assert opener.opened == ["https://a", "ms-settings:sound"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/nlu/test_slot_search.py tests/skills/test_web.py tests/adapters/test_windows_pure.py tests/fakes/test_ports.py -q`
Expected: FAIL — missing modules `sazed.nlu.slots.search`, `sazed.skills.pc.web`, `sazed.adapters.windows.opener`; `FakeOpener` undefined.

- [ ] **Step 3: Implement**

`src/sazed/nlu/slots/search.py`:

```python
"""Read a web search: the query after the trigger verb, and an optional trailing engine. Pure.

The query comes from normalised text, so punctuation is already gone ("c++" → "c").
"""

from collections.abc import Sequence

from sazed.core.types import SlotValue
from sazed.nlu.normalize import normalize, strip_accents

_TRIGGERS = frozenset(
    {
        "pesquisa", "pesquise", "pesquisar", "procura", "procure", "procurar",
        "busca", "busque", "buscar", "googla", "googlar",
    }
)
_LEADING = (("pra", "mim"), ("para", "mim"), ("por",), ("sobre",))
_PLACES = ("no", "na", "pelo", "pela")


def _engine_suffix(stripped: list[str], engines: Sequence[str]) -> tuple[str, int] | None:
    """(engine name, tokens to drop) when the text ends in "no/na <engine>"."""
    for name in sorted(engines, key=len, reverse=True):
        key = strip_accents(normalize(name)).split()
        n = len(key) + 1
        if len(stripped) >= n and stripped[-n] in _PLACES and stripped[-n + 1 :] == key:
            return name, n
    return None


def extract_engine(normalized: str, engines: Sequence[str]) -> SlotValue | None:
    stripped = strip_accents(normalized).split()
    found = _engine_suffix(stripped, engines)
    if found is None:
        return None
    name, n = found
    return SlotValue("site", name, " ".join(stripped[-n + 1 :]), 1.0)


def extract_query(normalized: str, engines: Sequence[str]) -> SlotValue | None:
    tokens = normalized.split()
    stripped = strip_accents(normalized).split()
    suffix = _engine_suffix(stripped, engines)
    if suffix is not None:
        tokens, stripped = tokens[: -suffix[1]], stripped[: -suffix[1]]
    start = next((i + 1 for i, t in enumerate(stripped) if t in _TRIGGERS), 0)
    # No trigger: the whole text is the query (a bare answer to "O que devo pesquisar?").
    tokens, stripped = tokens[start:], stripped[start:]
    for lead in _LEADING:
        if tuple(stripped[: len(lead)]) == lead:
            tokens, stripped = tokens[len(lead) :], stripped[len(lead) :]
            break
    query = " ".join(tokens)
    return SlotValue("consulta", query, query, 1.0) if query else None
```

(Check by hand: "pesquisa no youtube" → the suffix drops "no youtube" → ["pesquisa"] → start=1 → empty → None. "busca por" → start=1 → ["por"] → the leading filler is dropped → None.)

`src/sazed/skills/pc/web.py`:

```python
"""Web search in the default browser. Opening sites goes through the app catalog instead."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import Protocol
from urllib.parse import quote_plus

from sazed.core.outcomes import Outcome, SearchOpened
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue


class UriOpener(Protocol):
    def open(self, uri: str) -> None: ...


SEARCH_EXAMPLES = (
    "pesquisa receitas de bolo",
    "pesquisa no google como fazer pão",
    "procura vídeos de gatos no youtube",
    "busca o preço do dólar",
    "pesquise sobre buracos negros",
    "procura na internet horário do jogo",
    "pesquisa lofi no youtube",
    "busca na wikipédia a revolução francesa",
    "faz uma pesquisa sobre python",
    "pesquisar notícias de hoje",
)


def search_url(template: str, query: str) -> str:
    # quote_plus encodes everything but letters, digits and _.-~: no query can escape {q}.
    return template.replace("{q}", quote_plus(query))


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()


def _query_label(slots: Slots) -> str:
    query = slots.get("consulta")
    return f"'{query.value}'" if isinstance(query, SlotValue) else "algo"


class WebSkill:
    id = "web"

    def __init__(self, opener: UriOpener, engines: Mapping[str, str], default: str) -> None:
        self._opener = opener
        self._engines = dict(engines)
        self._default = default
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "pesquisar",
                SEARCH_EXAMPLES,
                (
                    SlotSpec("consulta", True, "O que devo pesquisar?"),
                    SlotSpec("site", False, "Onde devo pesquisar?"),
                ),
                describe=lambda s: f"pesquisar {_query_label(s)}",
            ),
        )

    def _engine(self, name: str) -> tuple[str, str]:
        for key, template in self._engines.items():
            if _fold(key) == _fold(name):
                return key, template
        raise ValueError(f"unknown search engine {name!r}")  # config validation prevents it

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id != "pesquisar":
            raise ValueError(f"unknown intent {intent_id}")
        query = slots.get("consulta")
        if not isinstance(query, SlotValue):
            raise ValueError("pesquisar called without its required slot 'consulta'")
        site = slots.get("site")
        wanted = str(site.value) if isinstance(site, SlotValue) else self._default
        name, template = self._engine(wanted)
        self._opener.open(search_url(template, str(query.value)))
        return SearchOpened(str(query.value), name)
```

`src/sazed/core/outcomes.py`: `SearchOpened(query: str, engine: str)` in `Success`. Persona:

```python
    "SearchOpened": (
        "Abrindo a busca por '{query}' em {engine}, {mestre}.",
        "Pesquisando '{query}' em {engine}, {mestre}.",
    ),
```

`src/sazed/adapters/windows/opener.py`:

```python
"""Open web addresses, Settings pages and app ids with the Windows shell."""

from __future__ import annotations

import os

_ALLOWED_PREFIXES = (
    "http://", "https://", "ms-settings:", "ms-screenclip:", "shell:appsfolder\\",
)


def is_allowed_uri(uri: str) -> bool:
    """Only the kinds of address Sazed builds itself: never a local file or program path."""
    return uri.lower().startswith(_ALLOWED_PREFIXES)


class ShellOpener:
    def open(self, uri: str) -> None:
        if not is_allowed_uri(uri):
            raise ValueError("refusing to open an address of an unexpected kind")
        os.startfile(uri)  # type: ignore[attr-defined]  # Windows only
```

`src/sazed/runtime/extractors.py` — new signature and two extractors:

```python
from sazed.nlu.slots.search import extract_engine, extract_query


def build_extractors(
    app_names: Sequence[str],
    engine_names: Sequence[str] = (),
    page_names: Sequence[str] = (),
) -> dict[str, SlotExtractor]:
    names, engines = list(app_names), list(engine_names)

    # ... existing app / percent / target / mute closures unchanged ...

    def query(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_query(text, engines)

    def engine(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_engine(text, engines)

    return {
        "app": app, "percent": percent, "alvo": target, "mudo": mute,
        "consulta": query, "site": engine,
    }
```

(`page_names` is used in Task 11; it is added now so the signature stays stable.)

`tests/fakes/ports.py`:

```python
class FakeOpener:
    def __init__(self) -> None:
        self.opened: list[str] = []

    def open(self, uri: str) -> None:
        self.opened.append(uri)
```

`tests/support/harness.py`: add `opener: FakeOpener` to `Harness`; in `build_harness` create `opener = FakeOpener()`, add `WebSkill(opener, BUILTIN_ENGINES, "Google")` to `skills`, and build the extractors with `build_extractors(APPS, engine_names=list(BUILTIN_ENGINES))`. Task 14 replaces this with `build_skills`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Discrimination proofs**

(a) Replace `quote_plus(query)` with `query.replace(" ", "+")`: `test_search_url_encodes_the_whole_query` FAILS for `&`, `#` and `/`. (b) Make `extract_query` return `None` when no trigger is found: the bare-answer dialogue test FAILS. (c) Make `is_allowed_uri` return `True`: the refusal tests FAIL. Revert all three; record under `## Search encoding`, `## Bare search answer`, `## URI allowlist`.

- [ ] **Step 6: Commit**

```bash
git add src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "feat(web): search the web with encoded queries in the default browser"
```

---

### Task 9: Media playback

**Files:**
- Create: `src/sazed/skills/pc/media.py`, `src/sazed/adapters/windows/media.py`
- Modify: `src/sazed/core/outcomes.py`, `src/sazed/core/persona/definition.py`, `src/sazed/core/persona/render.py`, `pyproject.toml`, `uv.lock`, `tests/fakes/ports.py`
- Test: `tests/skills/test_media.py`, `tests/core/persona/test_persona.py`, `tests/fakes/test_ports.py`, `tests/adapters/test_windows_integration.py`

**Interfaces:**
- Produces: `NowPlayingInfo(title: str, artist: str)`; `MediaControl` protocol (`toggle() -> bool`, `next() -> bool`, `previous() -> bool`, `now_playing() -> NowPlayingInfo | None`; `False`/`None` = no media session); `MediaSkill(media)` with intents `midia_tocar_pausar`, `midia_proxima` (repeatable), `midia_anterior` (repeatable), `midia_tocando`; outcomes `MediaToggled()`, `MediaNext()`, `MediaPrevious()`, `NowPlaying(title: str, artist: str)` (Success; template variant `NowPlaying.no_artist`), `NoMediaSession()` (Failure); `FakeMedia(session: bool = True, info: NowPlayingInfo | None = None)` with `calls: list[str]`; `WinRtMedia`.

- [ ] **Step 1: Add the dependency**

Run: `uv add "winrt-Windows.Media.Control; sys_platform == 'win32'"`
Expected: resolves and installs.

- [ ] **Step 2: Write the failing tests**

Create `tests/skills/test_media.py`:

```python
from datetime import datetime

import pytest

from fakes.ports import FakeMedia
from sazed.core.outcomes import MediaNext, MediaPrevious, MediaToggled, NoMediaSession, NowPlaying
from sazed.core.skill import SkillContext
from sazed.skills.pc.media import MediaSkill, NowPlayingInfo

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))


@pytest.mark.parametrize(
    ("intent", "call", "outcome"),
    [
        ("midia_tocar_pausar", "toggle", MediaToggled()),
        ("midia_proxima", "next", MediaNext()),
        ("midia_anterior", "previous", MediaPrevious()),
    ],
)
def test_controls_reach_the_session(intent: str, call: str, outcome: object) -> None:
    media = FakeMedia()
    assert MediaSkill(media).execute(intent, {}, CTX) == outcome
    assert media.calls == [call]


@pytest.mark.parametrize(
    "intent", ["midia_tocar_pausar", "midia_proxima", "midia_anterior", "midia_tocando"]
)
def test_without_a_session_sazed_says_so(intent: str) -> None:
    assert MediaSkill(FakeMedia(session=False)).execute(intent, {}, CTX) == NoMediaSession()


def test_now_playing_reports_title_and_artist() -> None:
    media = FakeMedia(info=NowPlayingInfo("Bohemian Rhapsody", "Queen"))
    outcome = MediaSkill(media).execute("midia_tocando", {}, CTX)
    assert outcome == NowPlaying("Bohemian Rhapsody", "Queen")


def test_only_track_skips_are_repeatable() -> None:
    repeatable = {s.id for s in MediaSkill(FakeMedia()).intents if s.repeatable}
    assert repeatable == {"midia_proxima", "midia_anterior"}
```

Append to `tests/core/persona/test_persona.py`:

```python
from sazed.core.outcomes import NowPlaying


def test_now_playing_without_artist_omits_it() -> None:
    text = render(NowPlaying("Lofi Radio", ""), nome="Artur", rng=Random(0))
    assert "Lofi Radio" in text
    assert ", de" not in text
```

Append to `tests/fakes/test_ports.py`:

```python
from fakes.ports import FakeMedia
from sazed.skills.pc.media import NowPlayingInfo


def test_fake_media_records_calls_and_reports_no_session() -> None:
    media = FakeMedia(info=NowPlayingInfo("t", "a"))
    assert media.toggle() and media.next() and media.previous()
    assert media.calls == ["toggle", "next", "previous"]
    assert media.now_playing() == NowPlayingInfo("t", "a")
    silent = FakeMedia(session=False)
    assert not silent.toggle() and silent.now_playing() is None
```

Append to `tests/adapters/test_windows_integration.py`:

```python
def test_media_session_is_readable_and_toggling_twice_restores_it() -> None:
    from sazed.adapters.windows.media import WinRtMedia

    media = WinRtMedia()
    media.now_playing()  # must not raise, session or not
    if not media.toggle():
        pytest.skip("no media session open")
    time.sleep(1.0)
    assert media.toggle()  # back to how it was
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/skills/test_media.py tests/core/persona tests/fakes/test_ports.py -q`
Expected: FAIL — `ImportError` for the new outcomes / `sazed.skills.pc.media`.

- [ ] **Step 4: Implement**

`src/sazed/core/outcomes.py` — add to `Success`: `MediaToggled`, `MediaNext`, `MediaPrevious` (no fields), `NowPlaying(title: str, artist: str)`; add `NoMediaSession` (no fields) to `Failure`.

`src/sazed/core/persona/definition.py` — import `NowPlaying` and:

```python
VARIANT_KEYS: dict[type, tuple[str, ...]] = {
    AppNotFound: ("AppNotFound", "AppNotFound.suggestion"),
    Confirm: ("Confirm", "ConfirmDestructive"),
    AskSlot: ("AskSlot", "AskSlotChoice"),
    NowPlaying: ("NowPlaying", "NowPlaying.no_artist"),
}
```

and templates:

```python
    "MediaToggled": ("Feito, {mestre}.", "Pronto, {mestre}."),
    "MediaNext": ("Próxima faixa, {mestre}.", "Pulando para a próxima, {mestre}."),
    "MediaPrevious": ("Voltando para a anterior, {mestre}.",),
    "NowPlaying": ("Está tocando '{title}', de {artist}, {mestre}.",),
    "NowPlaying.no_artist": ("Está tocando '{title}', {mestre}.",),
    "NoMediaSession": ("Não há nada tocando no momento, {mestre}.",),
```

`src/sazed/core/persona/render.py` — in `template_key`, before the final return:

```python
    if isinstance(item, NowPlaying) and not item.artist:
        return "NowPlaying.no_artist"
```

`src/sazed/skills/pc/media.py`:

```python
"""Play/pause, skip and "what's playing" through the system media session."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sazed.core.outcomes import (
    MediaNext,
    MediaPrevious,
    MediaToggled,
    NoMediaSession,
    NowPlaying,
    Outcome,
)
from sazed.core.skill import IntentSpec, SkillContext
from sazed.core.types import Slots


@dataclass(frozen=True)
class NowPlayingInfo:
    title: str
    artist: str


class MediaControl(Protocol):
    """False / None: there is no media session (nothing playing or paused anywhere)."""

    def toggle(self) -> bool: ...
    def next(self) -> bool: ...
    def previous(self) -> bool: ...
    def now_playing(self) -> NowPlayingInfo | None: ...


TOGGLE_EXAMPLES = (
    "pausa a música",
    "pausa o vídeo",
    "pausa",
    "continua a música",
    "despausa",
    "dá play",
    "play na música",
    "volta a tocar",
    "para a música",
    "retoma o vídeo",
)
NEXT_EXAMPLES = (
    "próxima música",
    "pula a música",
    "passa a música",
    "próxima faixa",
    "pula essa",
    "avança a música",
    "próximo vídeo",
    "pula pra próxima",
    "troca de música",
    "música seguinte",
)
PREVIOUS_EXAMPLES = (
    "música anterior",
    "volta a música",
    "faixa anterior",
    "volta uma música",
    "vídeo anterior",
    "toca a anterior",
    "volta pra música de antes",
    "põe a música anterior",
    "anterior",
    "retrocede a música",
)
NOW_EXAMPLES = (
    "o que está tocando",
    "que música é essa",
    "qual música está tocando",
    "que música está tocando",
    "qual é essa música",
    "o que tá tocando",
    "nome dessa música",
    "quem canta essa música",
    "que vídeo é esse",
    "qual o nome da música",
)


class MediaSkill:
    id = "media"

    def __init__(self, media: MediaControl) -> None:
        self._media = media
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "midia_tocar_pausar", TOGGLE_EXAMPLES, (), lambda s: "pausar ou continuar a mídia"
            ),
            IntentSpec(
                "midia_proxima",
                NEXT_EXAMPLES,
                (),
                lambda s: "passar para a próxima faixa",
                repeatable=True,
            ),
            IntentSpec(
                "midia_anterior",
                PREVIOUS_EXAMPLES,
                (),
                lambda s: "voltar para a faixa anterior",
                repeatable=True,
            ),
            IntentSpec("midia_tocando", NOW_EXAMPLES, (), lambda s: "dizer o que está tocando"),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id == "midia_tocando":
            info = self._media.now_playing()
            return NoMediaSession() if info is None else NowPlaying(info.title, info.artist)
        if intent_id == "midia_tocar_pausar":
            return MediaToggled() if self._media.toggle() else NoMediaSession()
        if intent_id == "midia_proxima":
            return MediaNext() if self._media.next() else NoMediaSession()
        if intent_id == "midia_anterior":
            return MediaPrevious() if self._media.previous() else NoMediaSession()
        raise ValueError(f"unknown intent {intent_id}")
```

`src/sazed/adapters/windows/media.py`:

```python
"""System media session (Spotify, browsers, …) through WinRT. Async calls run to completion here."""

from __future__ import annotations

import asyncio
from typing import Any

from sazed.skills.pc.media import NowPlayingInfo


async def _session() -> Any:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )

    return (await Manager.request_async()).get_current_session()


async def _toggle() -> bool:
    session = await _session()
    return session is not None and bool(await session.try_toggle_play_pause_async())


async def _next() -> bool:
    session = await _session()
    return session is not None and bool(await session.try_skip_next_async())


async def _previous() -> bool:
    session = await _session()
    return session is not None and bool(await session.try_skip_previous_async())


async def _now_playing() -> NowPlayingInfo | None:
    session = await _session()
    if session is None:
        return None
    props = await session.try_get_media_properties_async()
    title = str(props.title or "").strip()
    return NowPlayingInfo(title, str(props.artist or "").strip()) if title else None


class WinRtMedia:
    def toggle(self) -> bool:
        return asyncio.run(_toggle())

    def next(self) -> bool:
        return asyncio.run(_next())

    def previous(self) -> bool:
        return asyncio.run(_previous())

    def now_playing(self) -> NowPlayingInfo | None:
        return asyncio.run(_now_playing())
```

`tests/fakes/ports.py`:

```python
from sazed.skills.pc.media import NowPlayingInfo


class FakeMedia:
    def __init__(self, session: bool = True, info: NowPlayingInfo | None = None) -> None:
        self.session = session
        self.info = info
        self.calls: list[str] = []

    def _call(self, name: str) -> bool:
        if self.session:
            self.calls.append(name)
        return self.session

    def toggle(self) -> bool:
        return self._call("toggle")

    def next(self) -> bool:
        return self._call("next")

    def previous(self) -> bool:
        return self._call("previous")

    def now_playing(self) -> NowPlayingInfo | None:
        return self.info if self.session else None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -q` then `uv run pytest -m windows -q -k media`
Expected: PASS (the Windows test toggles twice, or skips when nothing is open).

- [ ] **Step 6: Discrimination proof**

Mutation: in `MediaSkill.execute`, return `MediaNext()` without checking `self._media.next()`'s result. Run `uv run pytest tests/skills/test_media.py -q`. Expected: `test_without_a_session_sazed_says_so[midia_proxima]` FAILS. Revert; record under `## No media session`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "feat(media): play, pause, skip and report what is playing"
```

---

### Task 10: Lock and power actions (always confirmed, never learned)

**Files:**
- Create: `src/sazed/skills/pc/power.py`, `src/sazed/adapters/windows/power.py`
- Modify: `src/sazed/core/outcomes.py`, `src/sazed/core/persona/definition.py`, `tests/fakes/ports.py`, `tests/support/harness.py`, `src/sazed/skills/CLAUDE.md`
- Test: `tests/skills/test_power.py`, `tests/runtime/test_power_safety.py`, `tests/adapters/test_windows_pure.py`, `tests/fakes/test_ports.py`, `tests/runtime/test_admin.py`

**Interfaces:**
- Consumes: `always`, `IntentSpec.learnable` (Task 3); `LabelResult.NOT_LEARNABLE` (Task 4).
- Produces: `Power` protocol (`lock()`, `shutdown()`, `restart()`, `sleep()`, `sign_out()`, all `-> None`); `PowerSkill(power)` with `pc_bloquear`, `pc_desligar`, `pc_reiniciar`, `pc_suspender`, `pc_sair_conta`; `POWER_INTENTS: frozenset[str]` (the four confirmed ones); outcomes `Locked`, `ShuttingDown`, `Restarting`, `Suspending`, `SigningOut` (no fields, Success); `FakePower` (`calls: list[str]`); `power_command(kind: str) -> list[str]`; `DELAY_SECONDS`; `WindowsPower`; `Harness.power`.

- [ ] **Step 1: Write the failing tests**

Create `tests/skills/test_power.py`:

```python
from datetime import datetime

import pytest

from fakes.ports import FakePower
from sazed.core.outcomes import Locked, Restarting, ShuttingDown, SigningOut, Suspending
from sazed.core.skill import SkillContext
from sazed.skills.pc.power import POWER_INTENTS, PowerSkill

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))


@pytest.mark.parametrize(
    ("intent", "call", "outcome"),
    [
        ("pc_bloquear", "lock", Locked()),
        ("pc_desligar", "shutdown", ShuttingDown()),
        ("pc_reiniciar", "restart", Restarting()),
        ("pc_suspender", "sleep", Suspending()),
        ("pc_sair_conta", "sign_out", SigningOut()),
    ],
)
def test_each_action_calls_its_port_method(intent: str, call: str, outcome: object) -> None:
    power = FakePower()
    assert PowerSkill(power).execute(intent, {}, CTX) == outcome
    assert power.calls == [call]


def test_power_intents_always_confirm_and_are_never_learned() -> None:
    specs = {s.id: s for s in PowerSkill(FakePower()).intents}
    assert POWER_INTENTS == {"pc_desligar", "pc_reiniciar", "pc_suspender", "pc_sair_conta"}
    for intent in POWER_INTENTS:
        assert specs[intent].requires_confirmation({}) is True
        assert specs[intent].learnable is False


def test_locking_runs_directly_and_may_be_learned() -> None:
    lock = next(s for s in PowerSkill(FakePower()).intents if s.id == "pc_bloquear")
    assert lock.requires_confirmation({}) is False
    assert lock.learnable is True
```

Create `tests/runtime/test_power_safety.py`. Its cases come from the skill's own specs, so a future power intent is covered automatically:

```python
import pytest

from fakes.ports import FakePower
from sazed.core.decisions import Confirm, ConfirmReason
from sazed.skills.pc.power import PowerSkill
from support.harness import Make

UNLEARNABLE = sorted(s.id for s in PowerSkill(FakePower()).intents if not s.learnable)


def test_there_are_power_intents_to_check() -> None:
    assert UNLEARNABLE  # an empty parametrisation would pass every test below vacuously


@pytest.mark.parametrize("intent", UNLEARNABLE)
def test_a_certain_power_command_still_confirms(make: Make, intent: str) -> None:
    h = make({"faz isso": {intent: 1.0}})
    r = h.say("faz isso")
    assert r.decision == Confirm(intent, {}, ConfirmReason.DESTRUCTIVE)
    assert h.power.calls == []


@pytest.mark.parametrize("intent", UNLEARNABLE)
def test_confirming_a_low_score_power_command_learns_nothing(make: Make, intent: str) -> None:
    # A LOW_SCORE confirm (unlike DESTRUCTIVE) normally learns the phrase: only the gate stops it.
    h = make({"faz isso aí": {intent: 0.80}})
    assert isinstance(h.say("faz isso aí").decision, Confirm)
    h.say("sim")
    assert len(h.power.calls) == 1
    assert h.store.learned() == []


@pytest.mark.parametrize("intent", UNLEARNABLE)
def test_a_correction_towards_a_power_command_confirms_and_learns_nothing(
    make: Make, intent: str
) -> None:
    h = make(
        {"abre o chrome": {"abrir_app": 0.95, "fechar_app": 0.6}, "desligar": {intent: 0.95}}
    )
    h.say("abre o chrome")
    r = h.say("não, era pra desligar")
    assert isinstance(r.decision, Confirm)
    assert h.power.calls == []
    h.say("sim")
    assert h.store.learned() == []
```

Append to `tests/runtime/test_admin.py`, skipped until Task 14 adds `PowerSkill` to `build_app`:

```python
@pytest.mark.skip(reason="enabled in Task 14, when build_app includes PowerSkill")
def test_a_power_command_cannot_be_labelled(tmp_path: Path) -> None:
    app = boot(tmp_path)
    episode_id = app.store.record_episode(
        Episode("apaga tudo", T0, (), {}, "NotUnderstood", None, "")
    )
    assert label_episode(app, episode_id, "pc_desligar") is LabelResult.NOT_LEARNABLE
    assert app.store.examples() == []
```

(add `import pytest` to that file if missing).

Append to `tests/adapters/test_windows_pure.py`:

```python
from sazed.adapters.windows.power import DELAY_SECONDS, power_command


def test_shutdown_and_restart_wait_so_the_reply_is_seen_and_can_be_cancelled() -> None:
    assert power_command("shutdown") == ["shutdown", "/s", "/t", str(DELAY_SECONDS)]
    assert power_command("restart") == ["shutdown", "/r", "/t", str(DELAY_SECONDS)]
    assert DELAY_SECONDS >= 5


def test_sign_out_command() -> None:
    assert power_command("sign_out") == ["shutdown", "/l"]


def test_unknown_power_kind_is_refused() -> None:
    with pytest.raises(ValueError):
        power_command("format_c")
```

Append to `tests/fakes/test_ports.py`:

```python
from fakes.ports import FakePower


def test_fake_power_records_calls() -> None:
    power = FakePower()
    power.lock()
    power.shutdown()
    assert power.calls == ["lock", "shutdown"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/skills/test_power.py tests/runtime/test_power_safety.py tests/adapters/test_windows_pure.py tests/fakes/test_ports.py -q`
Expected: FAIL — `No module named 'sazed.skills.pc.power'`.

- [ ] **Step 3: Implement**

Outcomes (`Success`): `Locked`, `ShuttingDown`, `Restarting`, `Suspending`, `SigningOut`. Persona:

```python
    "Locked": ("Computador bloqueado, {mestre}.",),
    "ShuttingDown": ("Desligando em alguns segundos. Até logo, {mestre}.",),
    "Restarting": ("Reiniciando em alguns segundos, {mestre}. Já volto.",),
    "Suspending": ("Suspendendo o computador, {mestre}.",),
    "SigningOut": ("Saindo da sua conta, {mestre}. Até logo.",),
```

`src/sazed/skills/pc/power.py`:

```python
"""Lock, shut down, restart, suspend, sign out. Every power action confirms and is never learned."""

from __future__ import annotations

from typing import Protocol

from sazed.core.outcomes import Locked, Outcome, Restarting, ShuttingDown, SigningOut, Suspending
from sazed.core.skill import IntentSpec, SkillContext, always
from sazed.core.types import Slots


class Power(Protocol):
    def lock(self) -> None: ...
    def shutdown(self) -> None: ...
    def restart(self) -> None: ...
    def sleep(self) -> None: ...
    def sign_out(self) -> None: ...


LOCK_EXAMPLES = (
    "bloqueia o computador",
    "bloqueia o pc",
    "trava o computador",
    "trava a tela",
    "bloqueia a tela",
    "tranca o computador",
    "bloquear o pc",
    "trava o pc",
    "bloqueia tudo",
    "tranca a tela",
)
SHUTDOWN_EXAMPLES = (
    "desliga o computador",
    "desliga o pc",
    "desligar o computador",
    "pode desligar o pc",
    "encerra o windows",
    "desliga a máquina",
    "apaga o computador",
    "desligar tudo",
    "desliga o computador agora",
    "quero desligar o pc",
)
RESTART_EXAMPLES = (
    "reinicia o computador",
    "reinicia o pc",
    "reiniciar o computador",
    "reinicializa o pc",
    "reinicia a máquina",
    "reboot no pc",
    "pode reiniciar o computador",
    "reiniciar o pc",
    "reinicia o windows",
    "quero reiniciar o computador",
)
SLEEP_EXAMPLES = (
    "suspende o computador",
    "suspende o pc",
    "coloca o pc pra dormir",
    "modo suspensão",
    "hiberna o computador",
    "põe o computador pra dormir",
    "suspender o pc",
    "deixa o pc em suspensão",
    "computador vai dormir",
    "coloca o computador em repouso",
)
SIGN_OUT_EXAMPLES = (
    "sai da minha conta",
    "faz logoff",
    "desloga do windows",
    "sair da conta",
    "faz logout",
    "encerra a sessão",
    "sair do usuário",
    "desconecta minha conta",
    "troca de usuário",
    "fecha a sessão",
)

POWER_INTENTS = frozenset({"pc_desligar", "pc_reiniciar", "pc_suspender", "pc_sair_conta"})


def _power(intent_id: str, examples: tuple[str, ...], describe: str) -> IntentSpec:
    # A learned phrase must never weaken a power confirmation (spec 2a §3.2).
    return IntentSpec(
        intent_id, examples, (), lambda s: describe, requires_confirmation=always, learnable=False
    )


class PowerSkill:
    id = "power"

    def __init__(self, power: Power) -> None:
        self._power = power
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec("pc_bloquear", LOCK_EXAMPLES, (), lambda s: "bloquear o computador"),
            _power("pc_desligar", SHUTDOWN_EXAMPLES, "desligar o computador"),
            _power("pc_reiniciar", RESTART_EXAMPLES, "reiniciar o computador"),
            _power("pc_suspender", SLEEP_EXAMPLES, "suspender o computador"),
            _power("pc_sair_conta", SIGN_OUT_EXAMPLES, "sair da sua conta"),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id == "pc_bloquear":
            self._power.lock()
            return Locked()
        if intent_id == "pc_desligar":
            self._power.shutdown()
            return ShuttingDown()
        if intent_id == "pc_reiniciar":
            self._power.restart()
            return Restarting()
        if intent_id == "pc_suspender":
            self._power.sleep()
            return Suspending()
        if intent_id == "pc_sair_conta":
            self._power.sign_out()
            return SigningOut()
        raise ValueError(f"unknown intent {intent_id}")
```

`src/sazed/adapters/windows/power.py`:

```python
"""Power actions. Each one is delayed a little so Sazed's reply is printed first.

Never called by tests: only `power_command` is tested.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable

DELAY_SECONDS = 5
"""shutdown.exe's own countdown; `shutdown /a` cancels it."""
_SHORT_DELAY = 2.0

_COMMANDS: dict[str, list[str]] = {
    "shutdown": ["shutdown", "/s", "/t", str(DELAY_SECONDS)],
    "restart": ["shutdown", "/r", "/t", str(DELAY_SECONDS)],
    "sign_out": ["shutdown", "/l"],  # /l takes no countdown
}


def power_command(kind: str) -> list[str]:
    if kind not in _COMMANDS:
        raise ValueError(f"unknown power action {kind!r}")
    return list(_COMMANDS[kind])


def _later(action: Callable[[], object]) -> None:
    threading.Timer(_SHORT_DELAY, action).start()


class WindowsPower:
    def lock(self) -> None:
        import ctypes

        if not ctypes.windll.user32.LockWorkStation():  # type: ignore[attr-defined]
            raise OSError("LockWorkStation failed")

    def shutdown(self) -> None:
        subprocess.run(power_command("shutdown"), check=True)

    def restart(self) -> None:
        subprocess.run(power_command("restart"), check=True)

    def sign_out(self) -> None:
        _later(lambda: subprocess.run(power_command("sign_out"), check=False))

    def sleep(self) -> None:
        import ctypes

        # SetSuspendState(hibernate=False, force=False, disable_wake_events=False)
        _later(lambda: ctypes.windll.powrprof.SetSuspendState(0, 0, 0))  # type: ignore[attr-defined]
```

`tests/fakes/ports.py`:

```python
class FakePower:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def lock(self) -> None:
        self.calls.append("lock")

    def shutdown(self) -> None:
        self.calls.append("shutdown")

    def restart(self) -> None:
        self.calls.append("restart")

    def sleep(self) -> None:
        self.calls.append("sleep")

    def sign_out(self) -> None:
        self.calls.append("sign_out")
```

`tests/support/harness.py`: add `power: FakePower` to `Harness`, create `FakePower()` and add `PowerSkill(power)` to `skills`.

`src/sazed/skills/CLAUDE.md`, under Traps:

```markdown
- Power intents (`POWER_INTENTS`) use `requires_confirmation=always` and `learnable=False`;
  `tests/runtime/test_power_safety.py` derives its cases from the specs. The Windows adapter
  delays each action so the reply prints first. No test may call the real adapter.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS (the admin test is skipped until Task 14).

- [ ] **Step 5: Discrimination proofs**

(a) In `_power`, drop `requires_confirmation=always`: `test_a_certain_power_command_still_confirms` FAILS (Execute, and `FakePower.calls == ["shutdown"]`). (b) Drop `learnable=False`: `test_confirming_a_low_score_power_command_learns_nothing` and the correction test FAIL. Revert; record under `## Power always confirms` and `## Power never learned`.

- [ ] **Step 6: Commit**

```bash
git add src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "feat(power): lock and confirmed power actions that are never learned"
```

---

### Task 11: Screenshots, snipping and Settings pages

**Files:**
- Create: `src/sazed/skills/pc/screen.py`, `src/sazed/skills/pc/settings.py`, `src/sazed/nlu/slots/page.py`, `src/sazed/adapters/windows/screen.py`
- Modify: `src/sazed/core/outcomes.py`, `src/sazed/core/persona/definition.py`, `src/sazed/runtime/extractors.py`, `src/sazed/nlu/slots/app.py`, `pyproject.toml`, `uv.lock`, `tests/fakes/ports.py`, `tests/support/harness.py`
- Test: `tests/skills/test_screen.py`, `tests/skills/test_settings.py`, `tests/nlu/test_slot_page.py`, `tests/adapters/test_windows_pure.py`, `tests/adapters/test_windows_integration.py`, `tests/fakes/test_ports.py`

**Interfaces:**
- Consumes: `UriOpener` (Task 8).
- Produces: `Screen` protocol (`capture(file_name: str) -> str` returning the name actually saved, `open_snip() -> None`); `screenshot_name(now: datetime) -> str`; `ScreenSkill(screen)` with `print_tela`, `recortar_tela`; outcomes `ScreenshotSaved(file_name: str)`, `SnipOpened()`, `SettingsOpened(page: str)` (Success), `UnknownSettingsPage(raw: str)` (Failure); `SettingsPage(label: str, names: tuple[str, ...], uri: str)`; `SETTINGS_PAGES`; `PAGE_NAMES: tuple[str, ...]`; `SettingsSkill(opener)` with `abrir_configuracao` (slot `pagina`, optional); `name_score(query, name_key) -> float` (renamed from `_score` in `nlu/slots/app.py`); `extract_page(normalized, names) -> SlotValue | Unmatched | None`; `unique_name(name: str, existing: set[str]) -> str`; `WindowsScreen(folder: Path | None = None)`; `FakeScreen(existing=None)` with `saved: list[str]`, `snips: int`.

- [ ] **Step 1: Add the dependency**

Run: `uv add Pillow`
Expected: resolves and installs.

- [ ] **Step 2: Write the failing tests**

`tests/skills/test_screen.py`:

```python
from datetime import datetime

from fakes.ports import FakeScreen
from sazed.core.outcomes import ScreenshotSaved, SnipOpened
from sazed.core.skill import SkillContext
from sazed.skills.pc.screen import ScreenSkill, screenshot_name

CTX = SkillContext(now=datetime(2026, 10, 15, 14, 3, 22))


def test_screenshot_name_comes_from_the_turn_time() -> None:
    assert screenshot_name(CTX.now) == "Captura 2026-10-15 14-03-22.png"


def test_screenshot_reports_the_name_actually_saved() -> None:
    screen = FakeScreen(existing={"Captura 2026-10-15 14-03-22.png"})
    outcome = ScreenSkill(screen).execute("print_tela", {}, CTX)
    assert outcome == ScreenshotSaved("Captura 2026-10-15 14-03-22 (2).png")
    assert screen.saved == ["Captura 2026-10-15 14-03-22 (2).png"]


def test_snip_opens_the_overlay() -> None:
    screen = FakeScreen()
    assert ScreenSkill(screen).execute("recortar_tela", {}, CTX) == SnipOpened()
    assert screen.snips == 1
```

`tests/skills/test_settings.py`:

```python
from datetime import datetime

from fakes.ports import FakeOpener
from sazed.core.outcomes import SettingsOpened, UnknownSettingsPage
from sazed.core.skill import SkillContext
from sazed.core.types import SlotValue, Unmatched
from sazed.skills.pc.settings import PAGE_NAMES, SETTINGS_PAGES, SettingsSkill

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))


def test_every_page_is_a_settings_uri_and_names_are_unique() -> None:
    assert all(p.uri.startswith("ms-settings:") for p in SETTINGS_PAGES)
    assert len(PAGE_NAMES) == len(set(PAGE_NAMES))


def test_a_named_page_opens_its_uri() -> None:
    opener = FakeOpener()
    slots = {"pagina": SlotValue("pagina", "dispositivos", "dispositivos", 1.0)}
    outcome = SettingsSkill(opener).execute("abrir_configuracao", slots, CTX)
    assert outcome == SettingsOpened("bluetooth")
    assert opener.opened == ["ms-settings:bluetooth"]


def test_no_page_opens_the_settings_home() -> None:
    opener = FakeOpener()
    outcome = SettingsSkill(opener).execute("abrir_configuracao", {}, CTX)
    assert outcome == SettingsOpened("início")
    assert opener.opened == ["ms-settings:"]


def test_an_unknown_page_is_explained_and_opens_nothing() -> None:
    opener = FakeOpener()
    slots = {"pagina": Unmatched("pagina", "teletransporte", None)}
    outcome = SettingsSkill(opener).execute("abrir_configuracao", slots, CTX)
    assert outcome == UnknownSettingsPage("teletransporte")
    assert opener.opened == []
```

`tests/nlu/test_slot_page.py` (nlu tests may import `sazed.skills` for fixture data; the architecture test checks `src/` only):

```python
import pytest

from sazed.core.types import SlotValue, Unmatched
from sazed.nlu.slots.page import extract_page
from sazed.skills.pc.settings import PAGE_NAMES


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("abre as configurações de bluetooth", "bluetooth"),
        ("abre as configurações de som", "som"),
        ("mostra as configurações de tela", "tela"),
        ("quero mudar o plano de fundo", "plano de fundo"),
        ("abre as configurações do wi fi", "wi-fi"),
        ("configurações de atualizações", "atualizações"),
    ],
)
def test_page_names_are_found(text: str, name: str) -> None:
    result = extract_page(text, PAGE_NAMES)
    assert isinstance(result, SlotValue) and result.value == name


def test_no_page_named_gives_none() -> None:
    assert extract_page("abre as configurações", PAGE_NAMES) is None


def test_an_unknown_page_is_unmatched() -> None:
    result = extract_page("abre as configurações de teletransporte", PAGE_NAMES)
    assert isinstance(result, Unmatched)
```

(normalisation turns "wi-fi" in an utterance into "wi fi"; the page key for "wi-fi" is normalised the same way, so they match exactly.)

Append to `tests/adapters/test_windows_pure.py`:

```python
from sazed.adapters.windows.screen import unique_name


def test_unique_name_never_overwrites() -> None:
    assert unique_name("a.png", set()) == "a.png"
    assert unique_name("a.png", {"a.png"}) == "a (2).png"
    assert unique_name("a.png", {"a.png", "a (2).png"}) == "a (3).png"
```

Append to `tests/adapters/test_windows_integration.py`:

```python
def test_screenshot_is_saved_to_the_given_folder(tmp_path: Path) -> None:
    from sazed.adapters.windows.screen import WindowsScreen

    name = WindowsScreen(tmp_path).capture("teste.png")
    assert name == "teste.png"
    assert (tmp_path / "teste.png").stat().st_size > 0


def test_settings_page_opens() -> None:
    from sazed.adapters.windows.opener import ShellOpener

    ShellOpener().open("ms-settings:sound")  # opens the Settings app; close it afterwards
```

Append to `tests/fakes/test_ports.py`:

```python
from fakes.ports import FakeScreen


def test_fake_screen_saves_unique_names_and_counts_snips() -> None:
    screen = FakeScreen(existing={"x.png"})
    assert screen.capture("x.png") == "x (2).png"
    screen.open_snip()
    assert screen.saved == ["x (2).png"] and screen.snips == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/skills/test_screen.py tests/skills/test_settings.py tests/nlu/test_slot_page.py tests/adapters/test_windows_pure.py tests/fakes/test_ports.py -q`
Expected: FAIL — missing modules.

- [ ] **Step 4: Implement**

Outcomes: `ScreenshotSaved(file_name: str)`, `SnipOpened`, `SettingsOpened(page: str)` in `Success`; `UnknownSettingsPage(raw: str)` in `Failure`. Persona:

```python
    "ScreenshotSaved": ("Capturei a tela, {mestre}: {file_name}.",),
    "SnipOpened": ("Selecione a área da tela, {mestre}.",),
    "SettingsOpened": ("Abrindo as configurações ({page}), {mestre}.",),
    "UnknownSettingsPage": ("Não conheço a página de configurações '{raw}', {mestre}.",),
```

`src/sazed/skills/pc/screen.py`:

```python
"""Full screenshots (all monitors) and the Windows snip overlay."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sazed.core.outcomes import Outcome, ScreenshotSaved, SnipOpened
from sazed.core.skill import IntentSpec, SkillContext
from sazed.core.types import Slots


class Screen(Protocol):
    def capture(self, file_name: str) -> str:
        """Save all monitors as `file_name` (or a free variant of it); return the name used."""
        ...

    def open_snip(self) -> None: ...


def screenshot_name(now: datetime) -> str:
    return f"Captura {now:%Y-%m-%d %H-%M-%S}.png"


PRINT_EXAMPLES = (
    "tira um print",
    "tira um print da tela",
    "captura a tela",
    "printa a tela",
    "faz uma captura de tela",
    "salva um print",
    "tira uma foto da tela",
    "print da tela",
    "captura de tela",
    "printa tudo",
)
SNIP_EXAMPLES = (
    "recorta a tela",
    "recortar a tela",
    "faz um recorte da tela",
    "seleciona uma parte da tela",
    "print de uma parte da tela",
    "captura um pedaço da tela",
    "recorte de tela",
    "abre o recorte",
    "quero recortar a tela",
    "print de uma área",
)


class ScreenSkill:
    id = "screen"

    def __init__(self, screen: Screen) -> None:
        self._screen = screen
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec("print_tela", PRINT_EXAMPLES, (), lambda s: "capturar a tela"),
            IntentSpec("recortar_tela", SNIP_EXAMPLES, (), lambda s: "abrir o recorte de tela"),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id == "print_tela":
            return ScreenshotSaved(self._screen.capture(screenshot_name(ctx.now)))
        if intent_id == "recortar_tela":
            self._screen.open_snip()
            return SnipOpened()
        raise ValueError(f"unknown intent {intent_id}")
```

`src/sazed/skills/pc/settings.py`:

```python
"""Open Windows Settings, optionally at a named page."""

from __future__ import annotations

from dataclasses import dataclass

from sazed.core.outcomes import Outcome, SettingsOpened, UnknownSettingsPage
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue, Unmatched
from sazed.skills.pc.web import UriOpener


@dataclass(frozen=True)
class SettingsPage:
    label: str
    names: tuple[str, ...]
    uri: str


SETTINGS_PAGES: tuple[SettingsPage, ...] = (
    SettingsPage("bluetooth", ("bluetooth", "dispositivos"), "ms-settings:bluetooth"),
    SettingsPage("rede", ("wi-fi", "wifi", "rede", "internet"), "ms-settings:network-wifi"),
    SettingsPage("som", ("som", "áudio"), "ms-settings:sound"),
    SettingsPage("tela", ("tela", "vídeo", "monitor", "resolução"), "ms-settings:display"),
    SettingsPage("atualizações", ("atualizações", "windows update"), "ms-settings:windowsupdate"),
    SettingsPage("aplicativos", ("aplicativos", "programas"), "ms-settings:appsfeatures"),
    SettingsPage("armazenamento", ("armazenamento", "disco"), "ms-settings:storagesense"),
    SettingsPage("energia", ("energia", "bateria", "suspensão"), "ms-settings:powersleep"),
    SettingsPage("notificações", ("notificações",), "ms-settings:notifications"),
    SettingsPage(
        "plano de fundo",
        ("plano de fundo", "papel de parede", "personalização"),
        "ms-settings:personalization-background",
    ),
    SettingsPage("privacidade", ("privacidade",), "ms-settings:privacy"),
    SettingsPage("mouse", ("mouse",), "ms-settings:mousetouchpad"),
    SettingsPage("teclado", ("teclado", "digitação"), "ms-settings:typing"),
    SettingsPage("impressoras", ("impressoras", "impressora"), "ms-settings:printers"),
    SettingsPage("data e hora", ("data e hora", "relógio"), "ms-settings:dateandtime"),
    SettingsPage("contas", ("contas", "minha conta"), "ms-settings:yourinfo"),
    SettingsPage("sobre", ("sobre", "sistema", "informações do sistema"), "ms-settings:about"),
)
PAGE_NAMES: tuple[str, ...] = tuple(n for p in SETTINGS_PAGES for n in p.names)
_BY_NAME = {n: p for p in SETTINGS_PAGES for n in p.names}
HOME_URI = "ms-settings:"

SETTINGS_EXAMPLES = (
    "abre as configurações",
    "abre as configurações de bluetooth",
    "abre as configurações de som",
    "configurações de rede",
    "abre o painel de configurações",
    "abre as configurações do windows",
    "mostra as configurações de tela",
    "quero mudar o plano de fundo",
    "abre as configurações de wifi",
    "abre as configurações de atualização",
)


def _describe(slots: Slots) -> str:
    page = slots.get("pagina")
    if isinstance(page, SlotValue):
        return f"abrir as configurações de {_BY_NAME[str(page.value)].label}"
    return "abrir as configurações"


class SettingsSkill:
    id = "settings"

    def __init__(self, opener: UriOpener) -> None:
        self._opener = opener
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "abrir_configuracao",
                SETTINGS_EXAMPLES,
                (SlotSpec("pagina", False, "Qual página das configurações devo abrir?"),),
                describe=_describe,
            ),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id != "abrir_configuracao":
            raise ValueError(f"unknown intent {intent_id}")
        page = slots.get("pagina")
        if isinstance(page, Unmatched):
            return UnknownSettingsPage(page.raw)
        if isinstance(page, SlotValue):
            found = _BY_NAME[str(page.value)]
            self._opener.open(found.uri)
            return SettingsOpened(found.label)
        self._opener.open(HOME_URI)
        return SettingsOpened("início")
```

`src/sazed/nlu/slots/app.py`: rename `_score` to `name_score` and update its one caller.

`src/sazed/nlu/slots/page.py`:

```python
"""Match a Settings page name. Pure; same scoring as app names."""

from collections.abc import Sequence

from sazed.core.types import SlotValue, Unmatched
from sazed.nlu.normalize import normalize, strip_accents
from sazed.nlu.slots.app import MIN_SCORE, name_score

_STOP = frozenset(
    {
        "abre", "abra", "abrir", "mostra", "mostre", "mostrar", "configuracoes",
        "configuracao", "config", "ajustes", "painel", "de", "do", "da", "das", "dos",
        "o", "a", "as", "os", "windows", "quero", "mudar", "muda", "me", "pra", "para",
        "sazed", "pode", "por", "favor", "e", "no", "na",
    }
)


def _key(text: str) -> str:
    return strip_accents(normalize(text))


def extract_page(normalized: str, names: Sequence[str]) -> SlotValue | Unmatched | None:
    query = " ".join(t for t in _key(normalized).split() if t not in _STOP)
    if not query:
        return None
    exact = [n for n in names if _key(n) == query]
    if exact:
        return SlotValue("pagina", exact[0], query, 1.0)
    scored = sorted(((name_score(query, _key(n)), n) for n in names), key=lambda sn: -sn[0])
    best_score, best = scored[0] if scored else (0.0, "")
    if best_score < MIN_SCORE:
        return Unmatched("pagina", query, None)
    return SlotValue("pagina", best, query, best_score / 100, exact=False)
```

(The page name keys keep their own stop words: "plano de fundo" against the query "plano fundo" gives `token_set_ratio` 100.)

`src/sazed/runtime/extractors.py`: import `extract_page`, keep `pages = list(page_names)`, add

```python
    def page(text: str, aliases: Mapping[str, str]) -> Extraction | None:
        return extract_page(text, pages)
```

and `"pagina": page` in the returned dict.

`src/sazed/adapters/windows/screen.py`:

```python
"""Screenshots with Pillow, and the snip overlay."""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)
FOLDERID_SCREENSHOTS = "{b7bede81-df94-4682-a7d8-57a52620b86f}"


def unique_name(name: str, existing: set[str]) -> str:
    if name not in existing:
        return name
    stem, dot, ext = name.rpartition(".")
    n = 2
    while f"{stem} ({n}){dot}{ext}" in existing:
        n += 1
    return f"{stem} ({n}){dot}{ext}"


def screenshots_dir() -> Path:
    try:
        import pywintypes
        from win32com.shell import shell  # type: ignore[import-untyped]

        return Path(shell.SHGetKnownFolderPath(pywintypes.IID(FOLDERID_SCREENSHOTS), 0, None))
    except Exception:
        log.warning("Screenshots known folder unavailable; using Pictures", exc_info=True)
        return Path.home() / "Pictures" / "Screenshots"


class WindowsScreen:
    def __init__(self, folder: Path | None = None) -> None:
        self._folder = folder

    def capture(self, file_name: str) -> str:
        from PIL import ImageGrab

        folder = self._folder or screenshots_dir()
        folder.mkdir(parents=True, exist_ok=True)
        name = unique_name(file_name, {p.name for p in folder.iterdir()})
        ImageGrab.grab(all_screens=True).save(folder / name)
        return name

    def open_snip(self) -> None:
        os.startfile("ms-screenclip:")  # type: ignore[attr-defined]  # Windows only
```

`tests/fakes/ports.py`:

```python
class FakeScreen:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = set(existing or ())
        self.saved: list[str] = []
        self.snips = 0

    def capture(self, file_name: str) -> str:
        from sazed.adapters.windows.screen import unique_name

        name = unique_name(file_name, self.existing)
        self.existing.add(name)
        self.saved.append(name)
        return name

    def open_snip(self) -> None:
        self.snips += 1
```

`tests/support/harness.py`: add `screen: FakeScreen` to `Harness`; add `ScreenSkill(screen)` and `SettingsSkill(opener)` to `skills`; pass `page_names=PAGE_NAMES` to `build_extractors`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -q` then `uv run pytest -m windows -q -k "screenshot or settings_page"`
Expected: PASS. Close the Settings window the second test opened.

- [ ] **Step 6: Discrimination proofs**

(a) `ScreenSkill` passes the fixed name `"Captura.png"` instead of `screenshot_name(ctx.now)`: `test_screenshot_reports_the_name_actually_saved` FAILS. (b) `unique_name` returns `name` unchanged: `test_unique_name_never_overwrites` FAILS. Revert; record under `## Screenshot names`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "feat(screen): screenshots, snip overlay and Settings pages"
```

---

### Task 12: Brightness

**Files:**
- Create: `src/sazed/skills/pc/brightness.py`, `src/sazed/adapters/windows/brightness.py`
- Modify: `src/sazed/core/outcomes.py`, `src/sazed/core/persona/definition.py`, `tests/fakes/ports.py`, `tests/support/harness.py`
- Test: `tests/skills/test_brightness.py`, `tests/fakes/test_ports.py`, `tests/adapters/test_windows_integration.py`

**Interfaces:**
- Consumes: `sazed.skills.pc.levels` (Task 1).
- Produces: `Brightness` protocol (`get() -> int | None`, `set(percent: int) -> bool`; `None`/`False` = unsupported); `BrightnessSkill(brightness)` with `brilho_definir` (`percent` required), `brilho_aumentar` / `brilho_diminuir` (`percent`, `alvo`; repeatable); outcomes `BrightnessSet(percent: int)`, `BrightnessChanged(percent: int)` (Success), `BrightnessUnsupported()` (Failure); `FakeBrightness(level: int | None = 50, accepts: bool = True)`; `WmiBrightness`.

- [ ] **Step 1: Write the failing tests**

`tests/skills/test_brightness.py`:

```python
from datetime import datetime

import pytest

from fakes.ports import FakeBrightness
from sazed.core.outcomes import (
    BrightnessChanged,
    BrightnessSet,
    BrightnessUnsupported,
    InvalidPercent,
)
from sazed.core.skill import SkillContext
from sazed.core.types import SlotValue, Unmatched
from sazed.skills.pc.brightness import BrightnessSkill

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))


def pct(n: int) -> dict[str, SlotValue]:
    return {"percent": SlotValue("percent", n, str(n), 1.0)}


def alvo(n: int) -> dict[str, SlotValue]:
    return {"alvo": SlotValue("alvo", n, str(n), 1.0)}


def test_set() -> None:
    b = FakeBrightness(50)
    assert BrightnessSkill(b).execute("brilho_definir", pct(30), CTX) == BrightnessSet(30)
    assert b.level == 30


def test_steps_and_levels_mirror_volume() -> None:
    b = FakeBrightness(50)
    skill = BrightnessSkill(b)
    assert skill.execute("brilho_aumentar", {}, CTX) == BrightnessChanged(60)
    assert skill.execute("brilho_diminuir", pct(0), CTX) == BrightnessChanged(60)
    assert skill.execute("brilho_diminuir", alvo(100), CTX) == BrightnessSet(100)
    assert b.level == 100


def test_out_of_range_is_explained() -> None:
    b = FakeBrightness(50)
    slots = {"percent": Unmatched("percent", "150", None)}
    assert BrightnessSkill(b).execute("brilho_aumentar", slots, CTX) == InvalidPercent("150")
    assert b.level == 50


@pytest.mark.parametrize("intent", ["brilho_definir", "brilho_aumentar", "brilho_diminuir"])
def test_unsupported_monitor_is_reported_honestly(intent: str) -> None:
    slots = pct(30) if intent == "brilho_definir" else {}
    outcome = BrightnessSkill(FakeBrightness(None)).execute(intent, slots, CTX)
    assert outcome == BrightnessUnsupported()


def test_a_refused_set_is_unsupported() -> None:
    b = FakeBrightness(50, accepts=False)
    assert BrightnessSkill(b).execute("brilho_definir", pct(30), CTX) == BrightnessUnsupported()
```

Append to `tests/fakes/test_ports.py`:

```python
from fakes.ports import FakeBrightness


def test_fake_brightness() -> None:
    b = FakeBrightness(40)
    assert b.get() == 40 and b.set(70) and b.level == 70
    assert FakeBrightness(None).get() is None
    refusing = FakeBrightness(40, accepts=False)
    assert not refusing.set(10) and refusing.level == 40
```

Append to `tests/adapters/test_windows_integration.py`:

```python
def test_brightness_reads_and_rewrites_the_same_level() -> None:
    from sazed.adapters.windows.brightness import WmiBrightness

    brightness = WmiBrightness()
    level = brightness.get()
    if level is None:
        pytest.skip("no monitor exposes WMI brightness")
    assert brightness.set(level)  # the same value: no visible change
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/skills/test_brightness.py tests/fakes/test_ports.py -q`
Expected: FAIL — missing module / names.

- [ ] **Step 3: Implement**

Outcomes `BrightnessSet(percent: int)`, `BrightnessChanged(percent: int)` (Success) and `BrightnessUnsupported` (Failure). Persona:

```python
    "BrightnessSet": ("Brilho em {percent}%, {mestre}.",),
    "BrightnessChanged": ("Pronto, {mestre}. Brilho em {percent}%.",),
    "BrightnessUnsupported": (
        "Este monitor não permite ajustar o brilho por software, {mestre}.",
    ),
```

`src/sazed/skills/pc/brightness.py`:

```python
"""Screen brightness, where the monitor allows it. Mirrors volume (steps and levels)."""

from __future__ import annotations

from typing import Protocol

from sazed.core.outcomes import BrightnessChanged, BrightnessSet, BrightnessUnsupported, Outcome
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots
from sazed.skills.pc.levels import clamp, int_slot, invalid_level, level_label, stepped


class Brightness(Protocol):
    def get(self) -> int | None: ...
    def set(self, percent: int) -> bool: ...


SET_EXAMPLES = (
    "brilho em 50",
    "coloca o brilho em 70",
    "deixa o brilho em 30",
    "ajusta o brilho pra 40",
    "brilho no máximo",
    "brilho no mínimo",
    "põe o brilho em 60",
    "define o brilho para 80",
    "brilho na metade",
    "muda o brilho para 20",
)
UP_EXAMPLES = (
    "aumenta o brilho",
    "sobe o brilho",
    "mais brilho",
    "aumenta o brilho da tela",
    "clareia a tela",
    "aumenta o brilho em 20",
    "sobe o brilho em 10",
    "tela mais clara",
    "deixa a tela mais clara",
    "aumenta mais o brilho",
)
DOWN_EXAMPLES = (
    "diminui o brilho",
    "abaixa o brilho",
    "menos brilho",
    "diminui o brilho da tela",
    "escurece a tela",
    "diminui o brilho em 20",
    "abaixa o brilho em 10",
    "tela mais escura",
    "deixa a tela mais escura",
    "baixa o brilho",
)
_LEVEL = SlotSpec("alvo", False, "Em quanto devo deixar o brilho?")


def _set_label(slots: Slots) -> str:
    n = int_slot(slots, "percent")
    return f"deixar o brilho em {n}%" if n is not None else "ajustar o brilho"


class BrightnessSkill:
    id = "brightness"

    def __init__(self, brightness: Brightness) -> None:
        self._brightness = brightness
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "brilho_definir",
                SET_EXAMPLES,
                (SlotSpec("percent", True, "Em quanto devo deixar o brilho?"),),
                describe=_set_label,
            ),
            IntentSpec(
                "brilho_aumentar",
                UP_EXAMPLES,
                (SlotSpec("percent", False, "Quanto devo aumentar?"), _LEVEL),
                describe=level_label("aumentar o brilho", "o brilho"),
                repeatable=True,
            ),
            IntentSpec(
                "brilho_diminuir",
                DOWN_EXAMPLES,
                (SlotSpec("percent", False, "Quanto devo diminuir?"), _LEVEL),
                describe=level_label("diminuir o brilho", "o brilho"),
                repeatable=True,
            ),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id not in ("brilho_definir", "brilho_aumentar", "brilho_diminuir"):
            raise ValueError(f"unknown intent {intent_id}")
        invalid = invalid_level(slots)
        if invalid is not None:
            return invalid
        current = self._brightness.get()
        if current is None:
            return BrightnessUnsupported()
        if intent_id == "brilho_definir":
            percent = int_slot(slots, "percent")
            if percent is None:
                raise ValueError("brilho_definir called without its required slot 'percent'")
            level, absolute = clamp(percent), True
        else:
            sign = 1 if intent_id == "brilho_aumentar" else -1
            level, absolute = stepped(current, sign, slots)
        if not self._brightness.set(level):
            return BrightnessUnsupported()
        return BrightnessSet(level) if absolute else BrightnessChanged(level)
```

`src/sazed/adapters/windows/brightness.py`:

```python
"""Monitor brightness through WMI. Only monitors that expose it respond; others are unsupported."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def _wmi() -> Any:
    import win32com.client

    return win32com.client.GetObject("winmgmts:\\\\.\\root\\WMI")


class WmiBrightness:
    def get(self) -> int | None:
        try:
            for monitor in _wmi().InstancesOf("WmiMonitorBrightness"):
                return int(monitor.CurrentBrightness)
        except Exception:
            log.warning("could not read brightness", exc_info=True)
        return None

    def set(self, percent: int) -> bool:
        try:
            methods = list(_wmi().InstancesOf("WmiMonitorBrightnessMethods"))
            for method in methods:
                method.WmiSetBrightness(0, percent)  # (timeout seconds, level)
            return bool(methods)
        except Exception:
            log.warning("could not set brightness", exc_info=True)
            return False
```

`tests/fakes/ports.py`:

```python
class FakeBrightness:
    def __init__(self, level: int | None = 50, accepts: bool = True) -> None:
        self.level = level
        self.accepts = accepts

    def get(self) -> int | None:
        return self.level

    def set(self, percent: int) -> bool:
        if not self.accepts or self.level is None:
            return False
        self.level = percent
        return True
```

`tests/support/harness.py`: add `brightness: FakeBrightness` and `BrightnessSkill(brightness)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q` then `uv run pytest -m windows -q -k brightness`
Expected: PASS, or the Windows test SKIPS. If it FAILS (WMI reports a monitor but refuses to set), that is the spec §11 risk: record a ruling, and leave the adapter returning `False`; the skill then says "não permite".

- [ ] **Step 5: Discrimination proof**

Mutation: drop the `if not self._brightness.set(level)` check, so success is always reported. `test_a_refused_set_is_unsupported` FAILS. Revert; record under `## Brightness refused`.

- [ ] **Step 6: Commit**

```bash
git add src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "feat(brightness): set and step screen brightness where supported"
```

---

### Task 13: System status (memory, CPU, disk)

**Files:**
- Create: `src/sazed/skills/pc/status.py`, `src/sazed/adapters/windows/status.py`
- Modify: `src/sazed/core/outcomes.py`, `src/sazed/core/persona/definition.py`, `tests/fakes/ports.py`, `tests/support/harness.py`
- Test: `tests/skills/test_status.py`, `tests/fakes/test_ports.py`, `tests/adapters/test_windows_integration.py`

**Interfaces:**
- Produces: `SystemStatus` protocol (`memory() -> tuple[int, int]` (free, total bytes), `cpu_percent() -> float`, `disks() -> list[tuple[str, int, int]]` (mount, free, total)); `pt_number(x: float, places: int) -> str`; `gigabytes(n: int) -> str`; `StatusSkill(status)` with `status_memoria`, `status_cpu`, `status_disco`; outcomes `MemoryStatus(free: str, total: str)`, `CpuStatus(percent: str)`, `DiskStatus(disks: tuple[str, ...])` (Success); `FakeStatus(memory=(0, 1), cpu=0.0, disks=None)`; `PsutilStatus`.

- [ ] **Step 1: Write the failing tests**

`tests/skills/test_status.py`:

```python
from datetime import datetime

import pytest

from fakes.ports import FakeStatus
from sazed.core.outcomes import CpuStatus, DiskStatus, MemoryStatus
from sazed.core.skill import SkillContext
from sazed.skills.pc.status import StatusSkill, gigabytes, pt_number

CTX = SkillContext(now=datetime(2026, 10, 15, 12, 0))
GB = 1024**3


@pytest.mark.parametrize(
    ("value", "places", "text"),
    [
        (5.24, 1, "5,2"),
        (1234.5, 1, "1.234,5"),
        (37.4, 0, "37"),
        (0.0, 1, "0,0"),
        (1000000, 0, "1.000.000"),
    ],
)
def test_numbers_use_pt_br_separators(value: float, places: int, text: str) -> None:
    assert pt_number(value, places) == text


def test_gigabytes() -> None:
    assert gigabytes(int(5.2 * GB)) == "5,2 GB"


def test_memory() -> None:
    status = FakeStatus(memory=(int(5.2 * GB), int(15.4 * GB)))
    outcome = StatusSkill(status).execute("status_memoria", {}, CTX)
    assert outcome == MemoryStatus("5,2 GB", "15,4 GB")


def test_cpu() -> None:
    assert StatusSkill(FakeStatus(cpu=37.4)).execute("status_cpu", {}, CTX) == CpuStatus("37%")


def test_disks() -> None:
    status = FakeStatus(disks=[("C:", 120 * GB, 476 * GB), ("D:", 1 * GB, 931 * GB)])
    assert StatusSkill(status).execute("status_disco", {}, CTX) == DiskStatus(
        ("C: 120,0 GB livres de 476,0 GB", "D: 1,0 GB livres de 931,0 GB")
    )
```

Append to `tests/fakes/test_ports.py`:

```python
from fakes.ports import FakeStatus


def test_fake_status_returns_what_it_was_given() -> None:
    status = FakeStatus(memory=(1, 2), cpu=3.0, disks=[("C:", 4, 5)])
    assert status.memory() == (1, 2) and status.cpu_percent() == 3.0
    assert status.disks() == [("C:", 4, 5)]
```

Append to `tests/adapters/test_windows_integration.py`:

```python
def test_status_reads_real_numbers() -> None:
    from sazed.adapters.windows.status import PsutilStatus

    status = PsutilStatus()
    free, total = status.memory()
    assert 0 < free < total
    assert 0.0 <= status.cpu_percent() <= 100.0
    assert any(mount.upper().startswith("C:") for mount, _, _ in status.disks())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/skills/test_status.py tests/fakes/test_ports.py -q`
Expected: FAIL — missing module.

- [ ] **Step 3: Implement**

Outcomes (`Success`): `MemoryStatus(free: str, total: str)`, `CpuStatus(percent: str)`, `DiskStatus(disks: tuple[str, ...])`. Persona:

```python
    "MemoryStatus": ("Há {free} livres de {total} de memória, {mestre}.",),
    "CpuStatus": ("O processador está com {percent} de uso, {mestre}.",),
    "DiskStatus": ("Espaço em disco, {mestre}: {disks}.",),
```

`src/sazed/skills/pc/status.py`:

```python
"""Read-only machine status in Sazed's voice. Numbers are formatted pt-BR here (pure)."""

from __future__ import annotations

from typing import Protocol

from sazed.core.outcomes import CpuStatus, DiskStatus, MemoryStatus, Outcome
from sazed.core.skill import IntentSpec, SkillContext
from sazed.core.types import Slots

_GB = 1024**3


class SystemStatus(Protocol):
    def memory(self) -> tuple[int, int]: ...
    def cpu_percent(self) -> float: ...
    def disks(self) -> list[tuple[str, int, int]]: ...


def pt_number(x: float, places: int) -> str:
    """1234.5 → "1.234,5": thousands with ".", decimals with ","."""
    return f"{x:,.{places}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


def gigabytes(n: int) -> str:
    return f"{pt_number(n / _GB, 1)} GB"


MEMORY_EXAMPLES = (
    "quanta memória está livre",
    "como está a memória",
    "quanta ram tem livre",
    "uso de memória",
    "memória disponível",
    "quanto de ram estou usando",
    "tem memória livre",
    "status da memória",
    "verifica a memória",
    "como está a ram",
)
CPU_EXAMPLES = (
    "como está a cpu",
    "uso do processador",
    "quanto a cpu está usando",
    "como está o processador",
    "status da cpu",
    "a cpu está pesada",
    "verifica o processador",
    "uso de cpu",
    "o processador está ocupado",
    "quanto de processamento está em uso",
)
DISK_EXAMPLES = (
    "quanto espaço tem no disco",
    "espaço livre no disco",
    "como está o armazenamento",
    "quanto de espaço sobrou",
    "status do disco",
    "verifica o espaço em disco",
    "o disco está cheio",
    "quanto espaço livre eu tenho",
    "armazenamento disponível",
    "espaço no hd",
)


class StatusSkill:
    id = "status"

    def __init__(self, status: SystemStatus) -> None:
        self._status = status
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec("status_memoria", MEMORY_EXAMPLES, (), lambda s: "verificar a memória"),
            IntentSpec("status_cpu", CPU_EXAMPLES, (), lambda s: "verificar o processador"),
            IntentSpec("status_disco", DISK_EXAMPLES, (), lambda s: "verificar o espaço em disco"),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id == "status_memoria":
            free, total = self._status.memory()
            return MemoryStatus(gigabytes(free), gigabytes(total))
        if intent_id == "status_cpu":
            return CpuStatus(f"{pt_number(self._status.cpu_percent(), 0)}%")
        if intent_id == "status_disco":
            return DiskStatus(
                tuple(
                    f"{mount} {gigabytes(free)} livres de {gigabytes(total)}"
                    for mount, free, total in self._status.disks()
                )
            )
        raise ValueError(f"unknown intent {intent_id}")
```

`src/sazed/adapters/windows/status.py`:

```python
"""Machine status from psutil."""

from __future__ import annotations

import psutil

CPU_SAMPLE_SECONDS = 0.3


class PsutilStatus:
    def memory(self) -> tuple[int, int]:
        vm = psutil.virtual_memory()
        return int(vm.available), int(vm.total)

    def cpu_percent(self) -> float:
        return float(psutil.cpu_percent(interval=CPU_SAMPLE_SECONDS))

    def disks(self) -> list[tuple[str, int, int]]:
        found = []
        for part in psutil.disk_partitions(all=False):
            if "fixed" not in part.opts:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            found.append((part.mountpoint.rstrip("\\"), int(usage.free), int(usage.total)))
        return found
```

`tests/fakes/ports.py`:

```python
class FakeStatus:
    def __init__(
        self,
        memory: tuple[int, int] = (0, 1),
        cpu: float = 0.0,
        disks: list[tuple[str, int, int]] | None = None,
    ) -> None:
        self._memory, self._cpu, self._disks = memory, cpu, list(disks or [])

    def memory(self) -> tuple[int, int]:
        return self._memory

    def cpu_percent(self) -> float:
        return self._cpu

    def disks(self) -> list[tuple[str, int, int]]:
        return list(self._disks)
```

`tests/support/harness.py`: add `status: FakeStatus` and `StatusSkill(status)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q` then `uv run pytest -m windows -q -k status`
Expected: PASS.

- [ ] **Step 5: Discrimination proof**

Mutation: `pt_number` returns `f"{x:,.{places}f}"` (English separators). `test_numbers_use_pt_br_separators` FAILS. Revert; record under `## pt-BR numbers`.

- [ ] **Step 6: Commit**

```bash
git add src/sazed tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "feat(status): report memory, CPU and disk in pt-BR"
```

---

### Task 14: Wiring — one `PcPorts` bundle builds every skill

Until now each new skill was reachable only through the test harness. This task wires all of them into the real app, the evaluation path, the scripts and the tests from one function.

**Files:**
- Create: `src/sazed/runtime/skills.py`
- Modify: `src/sazed/runtime/wiring.py`, `src/sazed/runtime/evaluation.py`, `scripts/tune_thresholds.py`, `scripts/measure_embedder.py`, `tests/nlu/test_fixture.py`, `tests/support/harness.py`, `tests/fakes/ports.py`, `tests/interfaces/test_cli.py`, `tests/runtime/test_wiring.py`, `tests/runtime/test_admin.py`, `tests/runtime/test_extractors.py`, `tests/skills/test_specs.py`, `src/sazed/runtime/CLAUDE.md` (create if missing, see Step 4)
- Test: `tests/runtime/test_skills.py`

**Interfaces:**
- Consumes: every skill and port from Tasks 6–13; `Config.effective_sites()`, `Config.search` (Task 5); `DEFAULT_APP_ALIASES` (Task 6); `PAGE_NAMES` (Task 11).
- Produces: `PcPorts(catalog, launcher, audio, media, power, screen, brightness, opener, status)`; `SkillSet(skills: list[Skill], app_names: list[str], engine_names: list[str], page_names: tuple[str, ...], app_aliases: dict[str, str])` with `extractors() -> dict[str, SlotExtractor]`; `build_skills(ports: PcPorts, config: Config) -> SkillSet`; `build_app(config, *, embedder, ports: PcPorts, clock=None, rng=None)` (signature change); `DryRunPorts` implements every port; `dry_run_skills(app_names: Sequence[str]) -> SkillSet`; test helper `fake_pc_ports(names, *, launcher=None, audio=None) -> PcPorts`.

- [ ] **Step 1: Write the failing tests**

Create `tests/runtime/test_skills.py`:

```python
from fakes.ports import fake_pc_ports
from sazed.runtime.config import BUILTIN_ENGINES, Config
from sazed.runtime.skills import build_skills
from sazed.skills.pc.settings import PAGE_NAMES


def test_every_skill_is_built_once() -> None:
    ids = [s.id for s in build_skills(fake_pc_ports([]), Config()).skills]
    assert sorted(ids) == sorted(
        ["apps", "volume", "media", "power", "screen", "settings", "brightness", "web", "status"]
    )


def test_sites_join_the_app_names_and_installed_apps_win() -> None:
    skill_set = build_skills(fake_pc_ports(["WhatsApp", "Spotify"]), Config())
    assert {"WhatsApp", "Spotify", "YouTube", "WhatsApp Web"} <= set(skill_set.app_names)
    assert skill_set.app_names.count("WhatsApp") == 1


def test_store_aliases_are_added_only_for_apps_that_exist() -> None:
    aliases = build_skills(fake_pc_ports(["Calculator"]), Config()).app_aliases
    assert aliases == {"calculadora": "Calculator"}


def test_configured_aliases_override_the_defaults() -> None:
    config = Config(aliases={"calculadora": "Spotify"})
    aliases = build_skills(fake_pc_ports(["Calculator", "Spotify"]), config).app_aliases
    assert aliases["calculadora"] == "Spotify"


def test_engines_and_pages_feed_the_extractors() -> None:
    skill_set = build_skills(fake_pc_ports([]), Config())
    assert skill_set.engine_names == list(BUILTIN_ENGINES)
    assert skill_set.page_names == PAGE_NAMES
    declared = {slot.name for s in skill_set.skills for spec in s.intents for slot in spec.slots}
    assert declared <= set(skill_set.extractors())
```

Replace the body of `tests/skills/test_specs.py`'s `SPECS` with the full set, and add the repeatable allowlist (this list *is* the spec's table, §3):

```python
from fakes.ports import fake_pc_ports
from sazed.runtime.config import Config
from sazed.runtime.skills import build_skills

SPECS: list[IntentSpec] = [
    spec for skill in build_skills(fake_pc_ports([]), Config()).skills for spec in skill.intents
]


def test_only_level_steps_and_track_skips_are_repeatable() -> None:
    assert {s.id for s in SPECS if s.repeatable} == {
        "volume_aumentar",
        "volume_diminuir",
        "brilho_aumentar",
        "brilho_diminuir",
        "midia_proxima",
        "midia_anterior",
    }
```

In `tests/runtime/test_extractors.py`, replace `test_every_declared_slot_has_an_extractor` with a call through `build_skills(fake_pc_ports([]), Config()).extractors()` (same assertion), so it covers every skill.

In `tests/runtime/test_admin.py`, remove the `@pytest.mark.skip` from `test_a_power_command_cannot_be_labelled`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/runtime/test_skills.py tests/skills/test_specs.py -q`
Expected: FAIL — `No module named 'sazed.runtime.skills'` / `cannot import name 'fake_pc_ports'`.

- [ ] **Step 3: Implement**

`src/sazed/runtime/skills.py`:

```python
"""Every skill, built from one bundle of ports. Used by wiring, evaluation and tests alike."""

from __future__ import annotations

from dataclasses import dataclass

from sazed.core.skill import Skill
from sazed.runtime.config import Config
from sazed.runtime.extractors import SlotExtractor, build_extractors
from sazed.skills.pc.apps import (
    DEFAULT_APP_ALIASES,
    AppCatalog,
    AppLauncher,
    AppsSkill,
    CombinedCatalog,
    StaticCatalog,
    site_entries,
)
from sazed.skills.pc.brightness import Brightness, BrightnessSkill
from sazed.skills.pc.media import MediaControl, MediaSkill
from sazed.skills.pc.power import Power, PowerSkill
from sazed.skills.pc.screen import Screen, ScreenSkill
from sazed.skills.pc.settings import PAGE_NAMES, SettingsSkill
from sazed.skills.pc.status import StatusSkill, SystemStatus
from sazed.skills.pc.volume import AudioControl, VolumeSkill
from sazed.skills.pc.web import UriOpener, WebSkill


@dataclass(frozen=True)
class PcPorts:
    catalog: AppCatalog
    launcher: AppLauncher
    audio: AudioControl
    media: MediaControl
    power: Power
    screen: Screen
    brightness: Brightness
    opener: UriOpener
    status: SystemStatus


@dataclass(frozen=True)
class SkillSet:
    skills: list[Skill]
    app_names: list[str]
    engine_names: list[str]
    page_names: tuple[str, ...]
    app_aliases: dict[str, str]

    def extractors(self) -> dict[str, SlotExtractor]:
        return build_extractors(self.app_names, self.engine_names, self.page_names)


def build_skills(ports: PcPorts, config: Config) -> SkillSet:
    catalog = CombinedCatalog(
        [ports.catalog, StaticCatalog(site_entries(config.effective_sites()))]
    )
    engines = config.search.effective_engines()
    skills: list[Skill] = [
        AppsSkill(catalog, ports.launcher),
        VolumeSkill(ports.audio),
        MediaSkill(ports.media),
        PowerSkill(ports.power),
        ScreenSkill(ports.screen),
        SettingsSkill(ports.opener),
        BrightnessSkill(ports.brightness),
        WebSkill(ports.opener, engines, config.search.default),
        StatusSkill(ports.status),
    ]
    names = [entry.name for entry in catalog.entries()]
    known = set(names)
    defaults = {alias: name for alias, name in DEFAULT_APP_ALIASES.items() if name in known}
    return SkillSet(skills, names, list(engines), PAGE_NAMES, {**defaults, **config.aliases})
```

`src/sazed/runtime/wiring.py` — `build_app` and `build_default_app`:

```python
from sazed.runtime.skills import PcPorts, build_skills


def build_app(
    config: Config,
    *,
    embedder: Embedder,
    ports: PcPorts,
    clock: Callable[[], datetime] | None = None,
    rng: Random | None = None,
) -> SazedApp:
    clock = clock or datetime.now
    rng = rng or Random()
    store = SqliteCoppermind(config.data.dir / "coppermind.db")
    skill_set = build_skills(ports, config)
    index = IntentMatcher(embedder)
    for skill in skill_set.skills:
        for spec in skill.intents:
            index.add_examples(spec.id, spec.examples)
    assistant = Assistant(
        skills=skill_set.skills,
        index=index,
        extractors=skill_set.extractors(),
        store=store,
        aliases={"app": skill_set.app_aliases},
        settings=settings_from(config),
        clock=clock,
        rng=rng,
    )
    return SazedApp(assistant, store, index, skill_set.skills, config, rng, clock)


def build_default_app(config: Config) -> SazedApp:
    from sazed.adapters.onnx.embedder import OnnxEmbedder
    from sazed.adapters.windows.audio import PycawAudio
    from sazed.adapters.windows.brightness import WmiBrightness
    from sazed.adapters.windows.catalog import StartMenuCatalog
    from sazed.adapters.windows.launcher import WindowsLauncher
    from sazed.adapters.windows.media import WinRtMedia
    from sazed.adapters.windows.opener import ShellOpener
    from sazed.adapters.windows.power import WindowsPower
    from sazed.adapters.windows.screen import WindowsScreen
    from sazed.adapters.windows.status import PsutilStatus
    from sazed.adapters.windows.store import StoreCatalog
    from sazed.skills.pc.apps import CombinedCatalog

    ports = PcPorts(
        catalog=CombinedCatalog([StartMenuCatalog(), StoreCatalog()]),
        launcher=WindowsLauncher(),
        audio=PycawAudio(),
        media=WinRtMedia(),
        power=WindowsPower(),
        screen=WindowsScreen(),
        brightness=WmiBrightness(),
        opener=ShellOpener(),
        status=PsutilStatus(),
    )
    return build_app(config, embedder=OnnxEmbedder(config.model.embedder_path), ports=ports)
```

Remove the now-unused imports (`AppCatalog`, `AppLauncher`, `AppsSkill`, `AudioControl`, `VolumeSkill`, `build_extractors`).

`src/sazed/runtime/evaluation.py` — `DryRunPorts` implements every port, and one helper builds the dry-run skill set:

```python
from sazed.runtime.config import Config
from sazed.runtime.skills import PcPorts, SkillSet, build_skills
from sazed.skills.pc.media import NowPlayingInfo


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


def dry_run_skills(app_names: Sequence[str]) -> SkillSet:
    ports = DryRunPorts(app_names)
    return build_skills(PcPorts(*([ports] * 9)), Config())
```

and in `evaluate`, build each assistant from it (built once, outside the loop):

```python
    skill_set = dry_run_skills(app_names)
    extractors = skill_set.extractors()
    ...
        assistant = Assistant(
            skills=skill_set.skills,
            index=index,
            extractors=extractors,
            store=SqliteCoppermind(":memory:"),
            aliases={"app": skill_set.app_aliases},
            ...
        )
```

`PcPorts(*([ports] * 9))` relies on field order; write it with keywords if mypy or a reader would trip on it (`PcPorts(catalog=ports, launcher=ports, …)`).

`tests/nlu/test_fixture.py`, `scripts/tune_thresholds.py`, `scripts/measure_embedder.py`: replace `for skill in (AppsSkill(ports, ports), VolumeSkill(ports))` with `for skill in dry_run_skills(app_names).skills` (`measure_embedder.py` passes `[]`), and drop the now-unused imports.

`tests/fakes/ports.py`:

```python
from sazed.runtime.skills import PcPorts


def fake_pc_ports(
    names: Sequence[str],
    *,
    launcher: FakeLauncher | None = None,
    audio: FakeAudio | None = None,
) -> PcPorts:
    return PcPorts(
        catalog=FakeCatalog(names),
        launcher=launcher or FakeLauncher(),
        audio=audio or FakeAudio(),
        media=FakeMedia(),
        power=FakePower(),
        screen=FakeScreen(),
        brightness=FakeBrightness(),
        opener=FakeOpener(),
        status=FakeStatus(),
    )
```

with a test in `tests/fakes/test_ports.py`:

```python
from fakes.ports import FakeAudio, fake_pc_ports


def test_fake_pc_ports_uses_the_given_fakes() -> None:
    audio = FakeAudio(volume=7)
    ports = fake_pc_ports(["Spotify"], audio=audio)
    assert ports.audio is audio
    assert [e.name for e in ports.catalog.entries()] == ["Spotify"]
```

`tests/support/harness.py` — build from `build_skills`, keeping every fake reachable:

```python
def build_harness(
    script=None, *, running=None, volume=50, aliases=None, launcher_error=None,
    store=None, extra_skills=(),
) -> Harness:
    index = ScriptedIndex(script)
    store = store or SqliteCoppermind(":memory:")
    launcher = FakeLauncher(running=running, fail_with=launcher_error)
    audio = FakeAudio(volume=volume)
    ports = fake_pc_ports(APPS, launcher=launcher, audio=audio)
    skill_set = build_skills(ports, Config())
    clock = ManualClock()
    assistant = Assistant(
        skills=[*skill_set.skills, *extra_skills],
        index=index,
        extractors=skill_set.extractors(),
        store=store,
        aliases={"app": {**skill_set.app_aliases, **dict(aliases or {})}},
        settings=SETTINGS,
        clock=clock,
        rng=Random(0),
    )
    return Harness(
        assistant, index, store, launcher, audio, clock,
        media=ports.media, power=ports.power, screen=ports.screen,
        brightness=ports.brightness, opener=ports.opener, status=ports.status,
    )
```

(keep the original type annotations on the parameters; the fields in `Harness` keep the concrete fake types, so cast with `assert isinstance(ports.media, FakeMedia)` or build the fakes first and pass them into `PcPorts` directly — prefer the latter: create each fake, then `PcPorts(...)` from them.)

`tests/interfaces/test_cli.py`, `tests/runtime/test_wiring.py`, `tests/runtime/test_admin.py` — every `build_app(...)` call changes from `catalog=…, launcher=…, audio=…` to `ports=fake_pc_ports([...], launcher=…, audio=…)` with the same names and fakes as before.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: PASS and clean. Existing harness tests must stay green with the sites in the catalog; if one now resolves an app differently (e.g. a test query fuzzily close to a site name), read the failure, then rename the site-colliding query in that test only if the new resolution is correct behaviour, recording a ruling.

Create `src/sazed/runtime/CLAUDE.md` if it does not exist (otherwise add the bullets):

```markdown
# sazed.runtime

Wires config, adapters, skills and the assistant together; the only place the clock is read.

## Conventions
- Every skill is built by `skills.build_skills(PcPorts, Config)`. Wiring, evaluation, scripts and
  the test harness all call it, so a new skill appears everywhere at once.
- `DryRunPorts` implements every port and never touches the machine; evaluation relies on it.

## Traps
- Sites are catalog entries (`CombinedCatalog`); an installed app with the same name wins.
- `DEFAULT_APP_ALIASES` are added only for apps present in the catalog; config aliases win.
```

- [ ] **Step 5: Discrimination proof**

Mutation: remove `SettingsSkill(ports.opener)` from `build_skills`. Run `uv run pytest tests/runtime/test_skills.py -q`. Expected: `test_every_skill_is_built_once` FAILS. Revert; record under `## Every skill wired`.

- [ ] **Step 6: Commit**

```bash
git add src/sazed scripts tests docs/superpowers/proofs/2026-10-15-sub-project-2a.md
git commit -m "feat(runtime): build every PC skill from one bundle of ports"
```

---

### Task 15: NLU fixture for the new intents; re-tune if needed

**Files:**
- Modify: `src/sazed/runtime/evaluation.py`, `tests/fixtures/nlu_cases.toml`, `tests/runtime/test_evaluation.py`, seed tuples in `src/sazed/skills/pc/*.py` (only if Step 5 needs it), `src/sazed/runtime/config.py` (only if thresholds are re-tuned), `CLAUDE.md`

**Interfaces:**
- Produces: `NluCase` gains `consulta: str | None`, `pagina: str | None`, `site: str | None`; `_is_false_execute` checks them.

- [ ] **Step 1: Write the failing test**

Append to `tests/runtime/test_evaluation.py`:

```python
def test_executing_with_the_wrong_query_is_a_false_execute() -> None:
    index = ScriptedIndex({"pesquisa gatos": {"pesquisar": 0.95}})
    right = NluCase("pesquisa gatos", "pesquisar", consulta="gatos")
    wrong = NluCase("pesquisa gatos", "pesquisar", consulta="cachorros")
    assert evaluate([right], index=index, app_names=APPS, thresholds=TH).false_execute_rate == 0
    assert evaluate([wrong], index=index, app_names=APPS, thresholds=TH).false_execute_rate == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/runtime/test_evaluation.py -q`
Expected: FAIL — `NluCase.__init__() got an unexpected keyword argument 'consulta'`.

- [ ] **Step 3: Implement**

In `src/sazed/runtime/evaluation.py`: add the three optional fields to `NluCase` (after `alvo`), read them in `load_cases` (`c.get("consulta")`, `c.get("pagina")`, `c.get("site")`), and check them in `_is_false_execute`:

```python
    expected_slots = (
        ("app", case.app), ("percent", case.percent), ("alvo", case.alvo),
        ("consulta", case.consulta), ("pagina", case.pagina), ("site", case.site),
    )
    for name, expected in expected_slots:
```

Run `uv run pytest -q` — PASS.

- [ ] **Step 4: Add the fixture cases**

In `tests/fixtures/nlu_cases.toml`:
- add `"WhatsApp"` and `"Notepad"` to `apps` (sites come from the built-in config through `dry_run_skills`);
- relabel `"desliga o computador"` to `intent = "pc_desligar"` and `"pesquisa receitas de bolo"` to `intent = "pesquisar"` with `consulta = "receitas de bolo"`;
- append these cases (none copies a seed; check with `tests/skills/test_specs.py` seeds before adding any of your own):

```toml
# --- sub-project 2a: media ------------------------------------------------------------------

[[case]]
text = "pausa a música aí"
intent = "midia_tocar_pausar"

[[case]]
text = "pode pausar"
intent = "midia_tocar_pausar"

[[case]]
text = "continua tocando"
intent = "midia_tocar_pausar"

[[case]]
text = "dá pause no vídeo"
intent = "midia_tocar_pausar"

[[case]]
text = "pula essa música"
intent = "midia_proxima"

[[case]]
text = "próxima por favor"
intent = "midia_proxima"

[[case]]
text = "passa pra próxima música"
intent = "midia_proxima"

[[case]]
text = "volta pra música anterior"
intent = "midia_anterior"

[[case]]
text = "toca a música de antes"
intent = "midia_anterior"

[[case]]
text = "que música tá tocando"
intent = "midia_tocando"

[[case]]
text = "qual o nome dessa música"
intent = "midia_tocando"

[[case]]
text = "o que está tocando agora"
intent = "midia_tocando"

# --- power and lock (power always confirms; a misranked power intent is still a false execute
# only if it executes, which the confirmation prevents) --------------------------------------

[[case]]
text = "bloqueia o computador agora"
intent = "pc_bloquear"

[[case]]
text = "trava a tela pra mim"
intent = "pc_bloquear"

[[case]]
text = "pode desligar a máquina"
intent = "pc_desligar"

[[case]]
text = "reinicia o pc por favor"
intent = "pc_reiniciar"

[[case]]
text = "reiniciar a máquina agora"
intent = "pc_reiniciar"

[[case]]
text = "coloca o computador pra dormir"
intent = "pc_suspender"

[[case]]
text = "deixa o computador em suspensão"
intent = "pc_suspender"

[[case]]
text = "faz logoff da minha conta"
intent = "pc_sair_conta"

[[case]]
text = "sai da conta do windows"
intent = "pc_sair_conta"

[[case]]
text = "desliga o spotify"
intent = "fechar_app"
app = "Spotify"

# --- screen ----------------------------------------------------------------------------------

[[case]]
text = "tira um print pra mim"
intent = "print_tela"

[[case]]
text = "captura a tela inteira"
intent = "print_tela"

[[case]]
text = "salva uma captura da tela"
intent = "print_tela"

[[case]]
text = "recorta um pedaço da tela"
intent = "recortar_tela"

[[case]]
text = "quero fazer um recorte"
intent = "recortar_tela"

[[case]]
text = "seleciona uma área da tela"
intent = "recortar_tela"

# --- settings --------------------------------------------------------------------------------

[[case]]
text = "abre as configurações do bluetooth"
intent = "abrir_configuracao"
pagina = "bluetooth"

[[case]]
text = "configurações de som"
intent = "abrir_configuracao"
pagina = "som"

[[case]]
text = "abre as configurações de rede"
intent = "abrir_configuracao"
pagina = "rede"

[[case]]
text = "me abre as configurações"
intent = "abrir_configuracao"

[[case]]
text = "quero trocar o papel de parede"
intent = "abrir_configuracao"
pagina = "papel de parede"

[[case]]
text = "abre as configurações de impressora"
intent = "abrir_configuracao"
pagina = "impressora"

# --- brightness (opposing near-ties with volume share the verb) ------------------------------

[[case]]
text = "deixa o brilho em 45"
intent = "brilho_definir"
percent = 45

[[case]]
text = "coloca o brilho no máximo"
intent = "brilho_definir"
percent = 100

[[case]]
text = "aumenta o brilho um pouco"
intent = "brilho_aumentar"

[[case]]
text = "abaixa o brilho da tela"
intent = "brilho_diminuir"

[[case]]
text = "aumenta o brilho pra 80"
intent = "brilho_aumentar"
alvo = 80

[[case]]
text = "diminui um pouco o brilho"
intent = "brilho_diminuir"

# --- web search ------------------------------------------------------------------------------

[[case]]
text = "pesquisa como trocar pneu"
intent = "pesquisar"
consulta = "como trocar pneu"

[[case]]
text = "procura músicas do queen no youtube"
intent = "pesquisar"
consulta = "músicas do queen"
site = "YouTube"

[[case]]
text = "busca a previsão do tempo"
intent = "pesquisar"
consulta = "a previsão do tempo"

[[case]]
text = "pesquisa sobre a segunda guerra na wikipédia"
intent = "pesquisar"
consulta = "a segunda guerra"
site = "Wikipédia"

[[case]]
text = "faz uma busca por notebooks baratos"
intent = "pesquisar"
consulta = "notebooks baratos"

# --- status ----------------------------------------------------------------------------------

[[case]]
text = "quanta memória tem livre"
intent = "status_memoria"

[[case]]
text = "como tá a memória ram"
intent = "status_memoria"

[[case]]
text = "o processador tá muito usado"
intent = "status_cpu"

[[case]]
text = "qual o uso da cpu agora"
intent = "status_cpu"

[[case]]
text = "quanto espaço livre tem no disco"
intent = "status_disco"

[[case]]
text = "meu hd está cheio"
intent = "status_disco"

# --- sites and Store apps through abrir_app / fechar_app -------------------------------------

[[case]]
text = "abre o youtube pra mim"
intent = "abrir_app"
app = "YouTube"

[[case]]
text = "abre o gmail aí"
intent = "abrir_app"
app = "Gmail"

[[case]]
text = "abre o whatsapp web"
intent = "abrir_app"
app = "WhatsApp Web"

[[case]]
text = "abre o whatsapp"
intent = "abrir_app"
app = "WhatsApp"

[[case]]
text = "abre o bloco de notas"
intent = "abrir_app"
app = "Notepad"

[[case]]
text = "fecha o whatsapp"
intent = "fechar_app"
app = "WhatsApp"

# --- out of domain, replacing the two phrases that became commands ---------------------------

[[case]]
text = "traduz bom dia para inglês"
intent = "none"

[[case]]
text = "liga a televisão"
intent = "none"

[[case]]
text = "agenda uma reunião amanhã"
intent = "none"

[[case]]
text = "me acorda às seis"
intent = "none"

[[case]]
text = "conta uma história"
intent = "none"

[[case]]
text = "desliga a luz do quarto"
intent = "none"
```

- [ ] **Step 5: Run the fixture against the real model**

Run: `uv run pytest -m model -q`
Expected: PASS (accuracy ≥ 0.90, false-execute ≤ 0.02). If it fails, read the assertion detail (it lists false executes and misranked cases), then in this order:
1. Seeds: add seeds that share objects across the confused pair (sub-project 1's rule), never copying a fixture phrase. Re-run.
2. Thresholds: `uv run python scripts/tune_thresholds.py`; adopt its result in `NluConfig` defaults only if it meets the bar.
3. Record every change as a ruling with the before/after numbers.

Never relabel a case to make it pass unless the label was wrong by the spec — that is also a ruling.

- [ ] **Step 6: Record the numbers**

Compute the report (the same script used for `CLAUDE.md` in sub-project 1: build the index from `dry_run_skills`, `evaluate`, print accuracy / false-execute / executed / asked / not understood). Update the fixture line in the root `CLAUDE.md` with the new case count and numbers.

- [ ] **Step 7: Commit**

```bash
git add src/sazed tests CLAUDE.md
git commit -m "test(nlu): label sub-project 2a phrases and keep the fixture bar"
```

---

### Task 16: Measurement, by-hand verification and docs

**Files:**
- Create: `scripts/measure_app.py`
- Modify: `CLAUDE.md`, `src/sazed/adapters/CLAUDE.md`, `src/sazed/skills/CLAUDE.md`, `src/sazed/nlu/CLAUDE.md`

- [ ] **Step 1: Measure idle memory with every adapter loaded**

Create `scripts/measure_app.py`:

```python
"""Load the full app (real model and adapters) and report startup time and memory."""

import time

import psutil

from sazed.runtime.config import Config
from sazed.runtime.wiring import build_default_app


def main() -> None:
    process = psutil.Process()
    before = process.memory_info().rss
    start = time.perf_counter()
    app = build_default_app(Config())
    loaded = time.perf_counter() - start
    rss = process.memory_info().rss
    names = len(app.skills)
    print(f"skills {names}; startup {loaded:.2f} s; RSS +{(rss - before) / 2**20:.0f} MB "
          f"(process {rss / 2**20:.0f} MB)")
    app.close()


if __name__ == "__main__":
    main()
```

Run: `uv run python scripts/measure_app.py` (the default `Config()` data dir is the real one; the script only opens the store, writing nothing). Record the line under "Measurements" in `CLAUDE.md`, next to sub-project 1's numbers.

- [ ] **Step 2: By-hand session (spec §9.1)**

Use a temporary config/data dir (as in sub-project 1: `[data] dir = "<temp>"`) and pipe commands with `PYTHONIOENCODING=utf-8 uv run sazed --config <temp>/config.toml`. Check, reading each reply:

1. With something playing (Spotify or YouTube): `pausa a música`, `continua a música`, `próxima música`, `de novo`, `o que está tocando`.
2. `tira um print` → a file appears in the Screenshots folder; `recorta a tela` → the overlay opens (press Esc).
3. `abre as configurações de bluetooth` → the Bluetooth page.
4. `brilho em 50` → record what happened (works, or "não permite"); restore the brightness.
5. `abre o youtube`, `pesquisa lofi no youtube`.
6. `abre o whatsapp` then `fecha o whatsapp`; `abre a calculadora` then `fecha a calculadora`.
7. `quanta memória está livre`, `como está a cpu`, `quanto espaço tem no disco`.
8. `desliga o computador` → confirmation shown → `não` → nothing happens.
9. `bloqueia o computador` → the PC locks; the user unlocks it. (Ask the user before this one.)

Record the results under "Verified by hand" in `CLAUDE.md`, and anything that failed as a finding to fix (TDD) before Step 4.

- [ ] **Step 3: Docs**

Update `CLAUDE.md` Status (2a implemented, branch, proofs file link) and "Unverified" (whatever Step 2 could not check). Make sure each local `CLAUDE.md` touched by earlier tasks still matches the code.

- [ ] **Step 4: Full verification**

Run: `uv run pytest -q`, `uv run pytest -m model -q`, `uv run pytest -m windows -q`, `uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: all green. Paste the summary lines into the ledger.

- [ ] **Step 5: Commit**

```bash
git add scripts/measure_app.py CLAUDE.md src/sazed
git commit -m "docs: record sub-project 2a measurements and by-hand verification"
```
