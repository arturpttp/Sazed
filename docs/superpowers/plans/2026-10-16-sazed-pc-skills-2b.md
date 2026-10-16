# Sazed 2b (windows, folders, files) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** typed pt-BR commands that minimise/maximise/restore/focus/snap/move windows, show the
desktop, open known folders, find and open files through the Windows Search index, and open or
list recent files.

**Architecture:** two new skills (`WindowsSkill`, `FilesSkill`) with ports next to them and
pure decision functions; thin pywin32/COM adapters in `adapters/windows`; five new slot
extractors in `nlu/slots`; learning masks folder and file names like apps. Everything is
built by `runtime/skills.build_skills`, so wiring, evaluation and the test harness get it at
once.

**Tech Stack:** Python 3.12 (uv), pywin32 (`win32gui`, `win32con`, `win32api`,
`win32process`, `win32com.client`), ctypes (`dwmapi`, `shell32`), psutil, rapidfuzz, pytest.

**Spec:** `docs/superpowers/specs/2026-10-16-sazed-pc-skills-2b-design.md`

## Global Constraints

- TDD for every behaviour; each pinned property gets a discrimination proof appended to
  `docs/superpowers/proofs/2026-10-16-sub-project-2b.md`.
- Conventional Commits in English, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- User-facing text in pt-BR, persona addresses "Mestre Artur" via `{mestre}`; code and docs in English.
- `core` and `nlu` stay pure (no clock, env, I/O) — enforced by `tests/test_architecture.py`.
  Skills never import adapters; adapters may import skills.
- Windows-only imports (`win32*`, `pythoncom`, `win32com`) inside methods.
- New intents are `learnable=True`; `repeatable=True` only for `janela_minimizar`,
  `janela_encaixar`, `janela_mover_monitor`.
- No file content is read; episodes record a file's name only.
- A file found by search whose extension is in `PROGRAM_EXTENSIONS` is never opened (§6).
- Fixture bar: accuracy ≥ 0.90, false-execute 0.000; thresholds (t_exec 0.94, t_confirm
  0.88, g_min 0.01) unchanged unless a re-tune is measured and recorded.
- Seeds: opposing intents share objects so the verb decides (CLAUDE.md rule).
- Don't run `-m windows` tests that toggle media while the user watches something; the 2b
  windows tests only touch Character Map, a temp file and the Downloads folder window.

## Deviations from the spec

- **The "Encontrei 12" count is not shown.** File ambiguity goes through the existing
  `AmbiguousSlot` → `AskSlot` path, whose question is per slot; the `arquivo` question says
  "Qual deles devo abrir? (os mais recentes primeiro)". Showing the total needs a new decision
  field for one sentence — cost if wrong: one template and one field later.
- **Choice labels map back to paths inside `FilesSkill`** (`_shown: dict[label, path]`, replaced
  on every search). The candidate the user picks arrives as the label; the skill opens the
  remembered path. A label not in `_shown` is searched again as a name.

## Review Focus

1. A phrase naming no app ("minimiza essa janela") must never act on Sazed's own console —
   pure test with the console's pid among the ancestors (Task 4).
2. A file name containing `'`, `%`, `_` or `[` must not change the SQL — builder tests (Task 6).
3. A program-type hit (`.lnk`, `.bat`…) chosen from a list must be revealed, not opened — both
   in the skill and in the adapter (Tasks 7, 8).
4. "mostra o spotify" (focus) vs "abre o spotify" (open) vs "abre a pasta downloads" vs "abre o
   arquivo downloads" — fixture near-ties (Task 10).
5. A monitor to the left of the primary (negative x) when moving a window — geometry test
   (Task 2).

---

### Task 1: Outcomes and pt-BR templates

**Files:**
- Modify: `src/sazed/core/outcomes.py`, `src/sazed/core/persona/definition.py`,
  `src/sazed/core/persona/render.py`
- Test: `tests/core/persona/test_persona.py`, `tests/core/test_outcomes.py`

**Interfaces — Produces** (all `@dataclass(frozen=True)`):
- Success: `WindowMinimized(app: str)`, `WindowMaximized(app: str)`, `WindowRestored(app: str)`,
  `WindowFocused(app: str)`, `WindowSnapped(app: str, side: str)`, `WindowMoved(app: str, monitor: int)`,
  `DesktopShown()`, `DesktopRestored()`, `FolderOpened(folder: str)`, `FileOpened(name: str)`,
  `ProgramRevealed(name: str)`, `RecentFiles(count: int, names: tuple[str, ...])`.
- Failure: `WindowNotFound(app: str, offer_open: bool = False)`, `NoWindow()`,
  `FocusRefused(app: str)`, `NoSuchMonitor(number: int, count: int)`, `SingleMonitor()`,
  `SearchUnavailable()`, `FileNotFound(query: str, kind: str)` (`kind` is the whole phrase,
  e.g. "nenhuma planilha chamada", built by the skill from `KIND_PHRASES`), `FolderNotFound(folder: str)`,
  `FileGone(name: str)`, `NothingRecent()`.
- Template key variant `WindowNotFound.offer_open` (in `VARIANT_KEYS` and `template_key`).

- [ ] **Step 1: failing tests.** The persona tests already derive the set of keys from the
  `Outcome` union (`test_template_keys_are_exactly_the_reachable_ones`), so adding the types to
  the unions without templates fails them. Add explicit value tests:

```python
def test_window_not_found_offers_to_open_only_when_asked() -> None:
    rng = Random(0)
    plain = render(WindowNotFound("Spotify"), nome="Artur", rng=rng)
    offer = render(WindowNotFound("Spotify", offer_open=True), nome="Artur", rng=rng)
    assert plain == "Spotify não está aberto, Mestre Artur."
    assert offer == "Spotify não está aberto, Mestre Artur. Devo abrir?"


def test_recent_files_lists_names_numbered() -> None:
    text = render(RecentFiles(2, ("a.pdf", "b.zip")), nome="Artur", rng=Random(0))
    assert text == "Hoje você baixou 2 arquivos, Mestre Artur: 1) a.pdf, 2) b.zip."


def test_file_not_found_names_the_kind() -> None:
    text = render(FileNotFound("gastos", "nenhuma planilha chamada"), nome="Artur", rng=Random(0))
    assert text == "Não encontrei nenhuma planilha chamada 'gastos', Mestre Artur."
```

- [ ] **Step 2:** `uv run pytest tests/core -q` → FAIL (ImportError / missing templates).
- [ ] **Step 3: implement.** Add the dataclasses to `outcomes.py` and to the `Success` /
  `Failure` unions. Templates in `definition.py` (exact strings; one variant each unless noted):

```python
    "WindowMinimized": ("{app} minimizado, {mestre}.",),
    "WindowMaximized": ("{app} maximizado, {mestre}.",),
    "WindowRestored": ("{app} restaurado, {mestre}.",),
    "WindowFocused": ("Aqui está {app}, {mestre}.",),
    "WindowSnapped": ("{app} foi para a {side}, {mestre}.",),
    "WindowMoved": ("{app} está no monitor {monitor}, {mestre}.",),
    "DesktopShown": ("Aqui está a área de trabalho, {mestre}.",),
    "DesktopRestored": ("As janelas estão de volta, {mestre}.",),
    "FolderOpened": ("Abrindo {folder}, {mestre}.",),
    "FileOpened": ("Abrindo {name}, {mestre}.",),
    "ProgramRevealed": (
        "Por segurança, não executo programas encontrados na busca, {mestre}; "
        "abri a pasta de {name}.",
    ),
    "RecentFiles": ("Hoje você baixou {count} arquivos, {mestre}: {names}.",),
    "WindowNotFound": ("{app} não está aberto, {mestre}.",),
    "WindowNotFound.offer_open": ("{app} não está aberto, {mestre}. Devo abrir?",),
    "NoWindow": ("Não há janela para isso, {mestre}.",),
    "FocusRefused": (
        "Não consegui trazer {app} para frente, {mestre}; ele está piscando na barra de tarefas.",
    ),
    "NoSuchMonitor": ("Só há {count} monitores, {mestre}.",),
    "SingleMonitor": ("Só há um monitor ligado, {mestre}.",),
    "SearchUnavailable": ("A pesquisa do Windows não está disponível agora, {mestre}.",),
    "FileNotFound": ("Não encontrei {kind} '{query}', {mestre}.",),
    "FolderNotFound": ("A pasta '{folder}' não existe, {mestre}.",),
    "FileGone": ("Esse arquivo não existe mais, {mestre}: {name}.",),
    "NothingRecent": ("Você não baixou nada hoje, {mestre}.",),
```

  `render.template_key`: `if isinstance(item, WindowNotFound) and item.offer_open: return
  "WindowNotFound.offer_open"`; `VARIANT_KEYS[WindowNotFound] = ("WindowNotFound",
  "WindowNotFound.offer_open")`.
- [ ] **Step 4:** `uv run pytest tests/core -q` → PASS.
- [ ] **Step 5: commit** `feat(core): outcomes and pt-BR answers for windows and files`.

---

### Task 2: Window geometry and monitor choice (pure)

**Files:**
- Create: `src/sazed/skills/pc/windows.py` (types + pure functions only in this task)
- Test: `tests/skills/test_window_geometry.py`

**Interfaces — Produces:**
```python
@dataclass(frozen=True)
class Rect:
    left: int; top: int; right: int; bottom: int
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...

@dataclass(frozen=True)
class Monitor:
    number: int          # 1-based, left-to-right then top-to-bottom
    work: Rect           # work area (taskbar excluded)
    primary: bool

def half(work: Rect, side: Literal["esquerda", "direita"]) -> Rect
def move_between(rect: Rect, src: Rect, dst: Rect) -> Rect
def target_monitor(monitors: Sequence[Monitor], current: int, wanted: str | int) -> Monitor | NoSuchMonitor | SingleMonitor
```

- [ ] **Step 1: failing tests.**

```python
from sazed.core.outcomes import NoSuchMonitor, SingleMonitor
from sazed.skills.pc.windows import Monitor, Rect, half, move_between, target_monitor

MAIN = Rect(0, 0, 1920, 1040)
LEFT = Rect(-1280, 0, 0, 984)  # a monitor left of the primary


def test_halves_split_the_work_area() -> None:
    assert half(MAIN, "esquerda") == Rect(0, 0, 960, 1040)
    assert half(MAIN, "direita") == Rect(960, 0, 1920, 1040)


def test_odd_widths_leave_no_gap() -> None:
    work = Rect(0, 0, 1366, 728)
    assert half(work, "esquerda").right == half(work, "direita").left


def test_moving_keeps_relative_position_and_size() -> None:
    rect = Rect(480, 260, 1440, 780)  # centred, half the size
    assert move_between(rect, MAIN, LEFT) == Rect(-960, 246, -320, 738)


def test_moving_clamps_inside_the_destination() -> None:
    rect = Rect(1800, 900, 2400, 1300)  # partly off the main screen
    moved = move_between(rect, MAIN, LEFT)
    assert LEFT.left <= moved.left and moved.right <= LEFT.right
    assert LEFT.top <= moved.top and moved.bottom <= LEFT.bottom


def test_other_cycles_to_the_next_monitor() -> None:
    mons = [Monitor(1, LEFT, False), Monitor(2, MAIN, True)]
    assert target_monitor(mons, current=2, wanted="outro") == mons[0]
    assert target_monitor(mons, current=1, wanted="outro") == mons[1]


def test_a_number_picks_that_monitor_or_explains() -> None:
    mons = [Monitor(1, LEFT, False), Monitor(2, MAIN, True)]
    assert target_monitor(mons, current=2, wanted=1) == mons[0]
    assert target_monitor(mons, current=2, wanted=3) == NoSuchMonitor(3, 2)


def test_one_monitor_on_means_nowhere_to_go() -> None:
    assert target_monitor([Monitor(1, MAIN, True)], current=1, wanted="outro") == SingleMonitor()
```

  Expected values: `move_between` maps proportionally — left = dst.left + (rect.left -
  src.left) * dst.width / src.width, rounded; same for the other edges; then shifted (not
  shrunk) to fit, and shrunk only if larger than the destination. For the first move test:
  -1280 + 480*1280/1920 = -960; 260*984/1040 = 246.0; -1280 + 1440*1280/1920 = -320;
  780*984/1040 = 738.
- [ ] **Step 2:** `uv run pytest tests/skills/test_window_geometry.py -q` → FAIL (module missing).
- [ ] **Step 3: implement** in `windows.py` (pure; `round()` on each edge; clamp by shifting
  into range, then cutting to the destination size). `target_monitor`: `len(monitors) == 1` →
  `SingleMonitor()` when wanted is `"outro"` or a number ≠ 1; a number out of range →
  `NoSuchMonitor(n, len)`; `"outro"` → next by number, wrapping.
- [ ] **Step 4:** PASS. **Step 5: commit** `feat(skills): window geometry and monitor choice`.

---

### Task 3: Slot extractors — lado, monitor, pasta, arquivo, tipo; masking

**Files:**
- Create: `src/sazed/nlu/slots/window.py` (lado, monitor), `src/sazed/nlu/slots/files.py`
  (pasta, arquivo, tipo), `src/sazed/nlu/slots/mask.py`
- Modify: `src/sazed/runtime/extractors.py`, `src/sazed/runtime/assistant.py`
  (`learnable_text`), `src/sazed/nlu/CLAUDE.md`
- Test: `tests/nlu/test_slot_window.py`, `tests/nlu/test_slot_files.py`,
  `tests/nlu/test_slot_mask.py`, `tests/runtime/test_extractors.py`,
  `tests/runtime/test_assistant_learning.py`

**Interfaces — Produces:**
- `extract_side(normalized) -> SlotValue | None` (slot `lado`, values `"esquerda"`/`"direita"`)
- `extract_monitor(normalized) -> SlotValue | None` (slot `monitor`, value `"outro"` or `int`)
- `extract_folder(normalized, names: Sequence[str], synonyms: Mapping[str, str]) -> SlotValue | Unmatched | None` (slot `pasta`; value a canonical name)
- `extract_kind(normalized) -> SlotValue | None` (slot `tipo`; values `planilha documento pdf apresentacao foto video musica texto`)
- `extract_file(normalized) -> SlotValue | None` (slot `arquivo`; value = remaining words joined)
- `mask_words(normalized, words: Collection[str], placeholder: str) -> str`
- `build_extractors(..., folder_names: Sequence[str] = (), folder_synonyms: Mapping[str, str] = {})` adds keys `lado monitor pasta tipo arquivo`.

- [ ] **Step 1: failing tests** (representative; write all):

```python
# tests/nlu/test_slot_window.py
@pytest.mark.parametrize(("text", "side"), [
    ("joga o chrome pra esquerda", "esquerda"), ("encaixa na direita", "direita"),
    ("manda pro lado esquerdo", "esquerda"), ("coloca à direita", "direita"),
])
def test_side(text: str, side: str) -> None:
    assert extract_side(normalize(text)) == SlotValue("lado", side, side, 1.0)

def test_no_side() -> None:
    assert extract_side("minimiza o chrome") is None

@pytest.mark.parametrize(("text", "value"), [
    ("manda pro outro monitor", "outro"), ("joga pra outra tela", "outro"),
    ("manda pro monitor 2", 2), ("pro segundo monitor", 2), ("pra tela 1", 1),
])
def test_monitor(text: str, value: object) -> None:
    found = extract_monitor(normalize(text))
    assert found is not None and found.value == value

# tests/nlu/test_slot_files.py
NAMES = ["Downloads", "Documentos", "Área de Trabalho", "Imagens", "Vídeos", "Músicas",
         "Capturas de Tela", "Projetos"]
SYN = {"baixados": "Downloads", "meus documentos": "Documentos", "desktop": "Área de Trabalho",
       "fotos": "Imagens", "prints": "Capturas de Tela", "print": "Capturas de Tela",
       "download": "Downloads", "musicas": "Músicas"}

@pytest.mark.parametrize(("text", "name"), [
    ("abre a pasta downloads", "Downloads"), ("abre meus documentos", "Documentos"),
    ("abre a área de trabalho", "Área de Trabalho"), ("abre o último print", "Capturas de Tela"),
    ("abre o último download", "Downloads"), ("abre a pasta projetos", "Projetos"),
])
def test_folder(text: str, name: str) -> None:
    found = extract_folder(normalize(text), NAMES, SYN)
    assert isinstance(found, SlotValue) and found.value == name

def test_unknown_folder_is_unmatched() -> None:
    assert isinstance(extract_folder("abre a pasta xyzzy", NAMES, SYN), Unmatched)

@pytest.mark.parametrize(("text", "words", "kind"), [
    ("abre o arquivo relatório", "relatório", None),
    ("acha a planilha de gastos", "gastos", "planilha"),
    ("abre o pdf do contrato", "contrato", "pdf"),
    ("abre a foto da praia", "praia", "foto"),
])
def test_file_and_kind(text: str, words: str, kind: str | None) -> None:
    n = normalize(text)
    assert extract_file(n) == SlotValue("arquivo", words, words, 1.0)
    found = extract_kind(n)
    assert (found.value if found else None) == kind

def test_only_command_words_is_no_file() -> None:
    assert extract_file(normalize("abre o arquivo")) is None

# tests/nlu/test_slot_mask.py
def test_mask_words_collapses_and_keeps_command_words() -> None:
    assert mask_words("acha a planilha de gastos do mes", {"gastos", "do", "mes"}, "arquivo") \
        == "acha a planilha de arquivo"
```

  In `test_assistant_learning.py` add (with `ScriptedIndex` scripts for both texts): confirmed
  `"abre a pasta projetos agora"` (`abrir_pasta` 0.90) → learned `"abre a pasta agora"` (only
  the folder name is masked; the placeholder collapses into the literal "pasta" before it).
  Confirmed `"acha o arquivo gastos de outubro"` (`abrir_arquivo`) → learned
  `"acha o arquivo"` (same collapse).
- [ ] **Step 2:** run the four test files → FAIL.
- [ ] **Step 3: implement.**
  - `window.py`: tokens after `strip_accents`; `esquerda`/`esquerdo` → esquerda,
    `direita`/`direito` → direita. Monitor: `outro`/`outra` followed within 2 tokens by
    `monitor`/`tela` → `"outro"`; `monitor|tela <digit>` or ordinal word (`primeiro`,
    `segundo`, `terceiro`) before `monitor|tela` → int.
  - `files.py`: `_FILE_STOP` = verbs (`abre abra abrir acha ache achar encontra encontre
    encontrar localiza localize localizar procura procure procurar mostra mostre mostrar`),
    fillers (`o a os as um uma de do da dos das meu minha meus minhas pra para mim por favor
    ai aquele aquela chamado chamada sazed`), `arquivo arquivos`, and every `_KIND_WORDS` key.
    `_KIND_WORDS = {"planilha": "planilha", "planilhas": "planilha", "excel": "planilha",
    "pdf": "pdf", "documento": "documento", "doc": "documento", "word": "documento",
    "apresentacao": "apresentacao", "slides": "apresentacao", "powerpoint": "apresentacao",
    "foto": "foto", "fotos": "foto", "imagem": "foto", "video": "video", "videos": "video",
    "musica": "musica", "audio": "musica", "texto": "texto", "txt": "texto"}`.
    `extract_file` keeps the remaining **original** tokens (accents kept, for display) in order.
    `extract_folder`: like `extract_page` (`_FOLDER_STOP` = verbs above + `pasta pastas
    ultimo ultima ultimos recente recentes` + fillers), synonyms checked first (exact key),
    then exact name, then `name_score` ≥ `MIN_SCORE`, else `Unmatched`.
  - `mask.py`: `mask_words` — tokens whose `strip_accents` form is in `words` (also
    accent-stripped) and not in `COMMAND_WORDS` become the placeholder; consecutive
    placeholders, and a placeholder right after the same literal word, collapse.
  - `Assistant.learnable_text`: table `{"app": ..., "pasta": "pasta", "arquivo": "arquivo"}`;
    for `pasta`/`arquivo`, run that slot's extractor on the text and mask its `raw` words.
  - `build_extractors`: register the five extractors.
- [ ] **Step 4:** PASS + `uv run pytest -q` green.
- [ ] **Step 5: commit** `feat(nlu): side, monitor, folder, file and kind slots; mask folder and file names when learning`.

---

### Task 4: WindowControl port, fake, and the window-choice function (pure)

**Files:**
- Modify: `src/sazed/skills/pc/windows.py` (port + `WindowRef`)
- Create: `src/sazed/adapters/windows/windows.py` (pure `choose_windows` only in this task)
- Modify: `tests/fakes/ports.py`, `tests/fakes/test_ports.py`
- Test: `tests/adapters/test_window_choice.py`

**Interfaces — Produces:**
```python
WindowState = Literal["normal", "minimized", "maximized"]

@dataclass(frozen=True)
class WindowRef:
    hwnd: int
    title: str
    state: WindowState
    rect: Rect
    monitor: int     # Monitor.number it is on

class WindowControl(Protocol):
    def windows(self, entry: AppEntry | None) -> list[WindowRef]: ...   # frontmost first
    def monitors(self) -> list[Monitor]: ...
    def minimize(self, hwnd: int) -> None: ...
    def maximize(self, hwnd: int) -> None: ...
    def restore(self, hwnd: int) -> None: ...
    def focus(self, hwnd: int) -> bool: ...
    def place(self, hwnd: int, rect: Rect) -> None: ...
    def show_desktop(self) -> None: ...
    def undo_show_desktop(self) -> None: ...

# adapters/windows/windows.py
@dataclass(frozen=True)
class RawWindow:
    hwnd: int; pid: int; child_pids: frozenset[int]; class_name: str; title: str
    visible: bool; cloaked: bool; tool_window: bool; owned: bool

SHELL_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})

def choose_windows(raw: Sequence[RawWindow], own_pids: set[int], app_pids: set[int] | None) -> list[int]
```
`FakeWindows(windows: dict[str | None, list[WindowRef]], monitors: list[Monitor], focus_ok=True)`
records calls in `self.calls: list[tuple[str, int]]` and updates `state`/`rect` like Windows.

- [ ] **Step 1: failing tests** (`test_window_choice.py`):

```python
def w(hwnd, pid, **kw):  # type: ignore[no-untyped-def]
    base = dict(child_pids=frozenset(), class_name="Chrome_WidgetWin_1", title="t",
                visible=True, cloaked=False, tool_window=False, owned=False)
    return RawWindow(hwnd, pid, **{**base, **kw})

CONSOLE_PID, CHROME_PID, FRAME_PID, CALC_PID = 10, 20, 30, 40

def test_without_an_app_the_frontmost_window_that_is_not_sazeds_console() -> None:
    raw = [w(1, CONSOLE_PID, class_name="CASCADIA_HOSTING_WINDOW_CLASS"), w(2, CHROME_PID)]
    assert choose_windows(raw, own_pids={CONSOLE_PID}, app_pids=None) == [2]

@pytest.mark.parametrize("bad", [
    {"visible": False}, {"cloaked": True}, {"tool_window": True}, {"owned": True},
    {"title": ""}, {"class_name": "Progman"}, {"class_name": "Windows.UI.Core.CoreWindow"},
])
def test_hidden_tool_owned_shell_and_core_windows_are_skipped(bad: dict[str, object]) -> None:
    assert choose_windows([w(1, CHROME_PID, **bad), w(2, CHROME_PID)], set(), None) == [2]

def test_an_apps_windows_include_store_frames_hosting_it_in_z_order() -> None:
    raw = [w(1, CHROME_PID), w(2, FRAME_PID, child_pids=frozenset({FRAME_PID, CALC_PID})),
           w(3, CALC_PID)]
    assert choose_windows(raw, set(), app_pids={CALC_PID}) == [2, 3]

def test_sazeds_console_is_excluded_even_when_it_matches_the_app() -> None:
    raw = [w(1, CONSOLE_PID), w(2, CONSOLE_PID)]
    assert choose_windows(raw, own_pids={CONSOLE_PID}, app_pids={CONSOLE_PID}) == []
```

  `tests/fakes/test_ports.py`: `FakeWindows` minimise/maximise/restore change `state`;
  `place` sets `rect` and state normal; `focus` returns `focus_ok`; `windows(None)` returns
  the `None` key list; `windows(entry)` the list under `entry.name`.
- [ ] **Step 2:** FAIL. **Step 3:** implement (pure filter keeps input order = z-order).
- [ ] **Step 4:** PASS. **Step 5: commit** `feat(windows): window port, fake and pure window choice`.

---

### Task 5: WindowsSkill

**Files:**
- Modify: `src/sazed/skills/pc/windows.py`, `src/sazed/skills/CLAUDE.md`
- Test: `tests/skills/test_windows_skill.py`

**Interfaces — Consumes:** Task 1 outcomes, Task 2 geometry, Task 4 port/fake, `AppCatalog`.
**Produces:** `WindowsSkill(catalog: AppCatalog, control: WindowControl)`, intents as in
spec §2 with slots: app `SlotSpec("app", False, "Qual janela?")` (required for `janela_focar`:
`"Para qual programa devo ir?"`), `lado` required (`"Para qual lado?"`), `monitor` optional.

Behaviour:
- Resolve: app slot `SlotValue` → catalog entry by name (`Unmatched` → `AppNotFound(raw,
  suggestion)`); entry `None` when no app slot. `windows = control.windows(entry)`; empty →
  `WindowNotFound(name, offer_open=intent == "janela_focar")` with an app, else `NoWindow()`.
- Target = `windows[0]`; label = entry name, or the window title cut to 60 chars.
- minimise/maximise/restore → port call → outcome.
- focus → `control.focus(hwnd)` → `WindowFocused` or `FocusRefused`.
- snap → monitor of the window → `place(hwnd, half(monitor.work, side))` → `WindowSnapped(label, side)`.
- move → `target_monitor(monitors, window.monitor, wanted or "outro")`; failure outcomes
  returned as-is; else `place(hwnd, move_between(window.rect, src.work, dst.work))` →
  `WindowMoved(label, dst.number)`. A maximised window: restore, place, maximise again.
- desktop show/undo → port → outcome.
- Seeds (≥ 10 per intent), sharing objects across minimise/maximise/restore and with
  `abrir_app`/`fechar_app` (chrome, spotify, discord, programa, janela). Focus seeds: "vai pro
  chrome", "mostra o spotify", "troca pro discord", "traz o chrome pra frente", "muda pra
  janela do spotify", "alterna pro discord", "foca no chrome", "me mostra o programa", "vai
  pra janela do chrome", "volta pro spotify".

- [ ] **Step 1: failing tests** — one per behaviour above plus every failure row; e.g.:

```python
def test_focus_on_a_closed_app_offers_to_open_it() -> None:
    skill = WindowsSkill(FakeCatalog(["Spotify"]), FakeWindows({}, [Monitor(1, MAIN, True)]))
    assert skill.execute("janela_focar", app("Spotify"), CTX) == WindowNotFound("Spotify", True)

def test_minimise_without_app_acts_on_the_frontmost_window() -> None:
    fake = FakeWindows({None: [ref(5, "Documento - Word"), ref(6, "x")]}, MONS)
    assert WindowsSkill(FakeCatalog([]), fake).execute("janela_minimizar", {}, CTX) \
        == WindowMinimized("Documento - Word")
    assert fake.calls == [("minimize", 5)]

def test_moving_a_maximised_window_keeps_it_maximised() -> None: ...
def test_snap_uses_the_windows_own_monitor() -> None: ...
def test_minimise_snap_and_move_are_repeatable_and_the_rest_are_not() -> None:
    reps = {s.id for s in WindowsSkill(FakeCatalog([]), FakeWindows({}, MONS)).intents if s.repeatable}
    assert reps == {"janela_minimizar", "janela_encaixar", "janela_mover_monitor"}
```
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5: commit** `feat(skills): window commands`.

---

### Task 6: Files — pure search builder, program rule, kinds, labels

**Files:**
- Create: `src/sazed/skills/pc/files.py` (pure part)
- Test: `tests/skills/test_files_pure.py`

**Interfaces — Produces:**
```python
@dataclass(frozen=True)
class FileHit:
    path: str; name: str; folder: str; modified: datetime

PROGRAM_EXTENSIONS: frozenset[str]   # spec §6 list, lower-case with dot
KIND_EXTENSIONS: dict[str, tuple[str, ...]]  # spec §5.2
KIND_PHRASES: dict[str | None, str]  # None → "nenhum arquivo chamado", "planilha" → "nenhuma planilha chamada", ...
KNOWN_FOLDERS: tuple[str, ...]   # canonical pt-BR names (Task 3 NAMES minus "Projetos")
FOLDER_SYNONYMS: dict[str, str]
def is_program(path: str) -> bool
def escape_sql_like(word: str) -> str
def search_sql(words: Sequence[str], extensions: Sequence[str], scopes: Sequence[str], limit: int) -> str
def newest_sql(folder: str, since: datetime | None, limit: int) -> str
def file_label(hit: FileHit, now: datetime) -> str
def is_exact(hit: FileHit, query: str) -> bool
```

- [ ] **Step 1: failing tests.**

```python
@pytest.mark.parametrize("ext", sorted(PROGRAM_EXTENSIONS))
def test_every_program_extension_is_a_program_in_any_case(ext: str) -> None:
    assert is_program(f"C:/x/setup{ext}") and is_program(f"C:/x/SETUP{ext.upper()}")

@pytest.mark.parametrize("path", ["C:/x/a.pdf", "C:/x/a.xlsx", "C:/x/a", "C:/x/a.exe.txt"])
def test_documents_are_not_programs(path: str) -> None:
    assert not is_program(path)

@pytest.mark.parametrize(("word", "escaped"), [
    ("gastos", "gastos"), ("d'água", "d''água"), ("100%", "100[%]"), ("a_b", "a[_]b"),
    ("[x]", "[[]x]"),
])
def test_like_escaping(word: str, escaped: str) -> None:
    assert escape_sql_like(word) == escaped

def test_search_sql_scopes_words_kinds_and_excludes_folders() -> None:
    sql = search_sql(["gastos", "d'água"], [".xlsx", ".csv"], ["C:/Users/A"], 6)
    assert sql == (
        "SELECT TOP 6 System.ItemPathDisplay, System.DateModified FROM SYSTEMINDEX "
        "WHERE (SCOPE='file:C:/Users/A') AND System.Kind <> 'folder' "
        "AND System.FileName LIKE '%gastos%' AND System.FileName LIKE '%d''água%' "
        "AND (System.FileExtension = '.xlsx' OR System.FileExtension = '.csv') "
        "ORDER BY System.DateModified DESC"
    )

def test_an_injection_attempt_stays_inside_the_string() -> None:
    sql = search_sql(["x' OR 1=1 --"], [], ["C:/Users/A"], 6)
    assert "LIKE '%x'' OR 1=1 --%'" in sql and sql.count("'") % 2 == 0

def test_labels_use_folder_and_when() -> None:
    now = datetime(2026, 10, 16, 15, 0)
    hit = FileHit("C:/U/Documents/r.docx", "r.docx", "Documents", datetime(2026, 10, 16, 14, 2))
    assert file_label(hit, now) == "r.docx (Documents, hoje 14:02)"
    assert file_label(replace(hit, modified=datetime(2026, 10, 15, 9, 0)), now) == "r.docx (Documents, ontem)"
    assert file_label(replace(hit, modified=datetime(2026, 10, 12, 9, 0)), now) == "r.docx (Documents, 12/10)"

def test_exact_ignores_extension_accents_and_case() -> None:
    hit = FileHit("C:/a/Relatório.docx", "Relatório.docx", "a", datetime(2026, 1, 1))
    assert is_exact(hit, "relatorio") and not is_exact(hit, "relat")
```
- [ ] **Step 2:** FAIL. **Step 3:** implement (accented and accent-stripped forms of a word
  that differ become `(LIKE a OR LIKE b)`; add a test for that). `KIND_EXTENSIONS` from spec
  §5.2 exactly.
- [ ] **Step 4:** PASS. **Step 5: commit** `feat(skills): file search query, program rule and labels`.

---

### Task 7: FilesSkill

**Files:**
- Modify: `src/sazed/skills/pc/files.py`, `tests/fakes/ports.py`, `tests/fakes/test_ports.py`,
  `src/sazed/skills/CLAUDE.md`
- Test: `tests/skills/test_files_skill.py`

**Interfaces — Produces:**
```python
class KnownFolders(Protocol):
    def names(self) -> Sequence[str]: ...
    def resolve(self, name: str) -> str | None: ...       # None: configured but missing
class SearchError(Exception): ...
class FileSearch(Protocol):
    def search(self, words: Sequence[str], extensions: Sequence[str], limit: int) -> list[FileHit]: ...  # raises SearchError
    def newest(self, folder: str, since: datetime | None, limit: int) -> list[FileHit]: ...      # raises SearchError
class FileOpener(Protocol):
    def open(self, path: str) -> None: ...
    def reveal(self, path: str) -> None: ...
    def exists(self, path: str) -> bool: ...
class FilesSkill:
    def __init__(self, folders: KnownFolders, search: FileSearch, opener: FileOpener) -> None
```
Fakes: `FakeFolders(dict[name, path|None])`, `FakeSearch(hits, fail=False)` (records
calls; filters `hits` by words/extensions like the real index would — test that),
`FakeFileOpener(existing: set[str])` (records `opened`, `revealed`).

Behaviour (spec §2, §6–§8):
- `abrir_pasta`: `Unmatched` → `FolderNotFound(raw)`; resolve → `None` → `FolderNotFound`; else
  `opener.open(path)` → `FolderOpened(name)`.
- `abrir_arquivo`: value in `self._shown` → that path; else `search(words, KIND_EXTENSIONS
  [tipo] or (), 6)`; `SearchError` → `SearchUnavailable()`; `[]` → `FileNotFound(query,
  KIND_PHRASES[tipo])`; one hit, or exactly one `is_exact` hit → open it; more → remember
  labels (first 5) and return `AmbiguousSlot("arquivo", labels)`.
- Opening a hit: `not exists` → `FileGone(name)`; `is_program` → `reveal` + `ProgramRevealed`;
  else `open` → `FileOpened(name)`.
- `abrir_recente`: folder (default `"Downloads"`) → `newest(path, None, 1)` → open as above;
  empty → `NothingRecent()`.
- `listar_recentes`: `newest(downloads, start_of(ctx.now), 10)` → `RecentFiles(n, names)` or
  `NothingRecent()`.
- `arquivo` slot question: `"Qual deles devo abrir? (os mais recentes primeiro)"` when asked
  after ambiguity; when missing: `"Qual arquivo devo abrir?"` — the `SlotSpec` question is the
  second; the ambiguity text is rendered by `AskSlotChoice` with `{pergunta}` = the spec
  question, so set the `SlotSpec` question to `"Qual arquivo devo abrir?"` and accept that.
  (Deviation noted at the top.)

- [ ] **Step 1: failing tests** — every row of spec §8 for files, plus:

```python
def test_a_program_chosen_from_a_list_is_revealed_not_run() -> None:
    hits = [hit("C:/U/Downloads/setup.lnk"), hit("C:/U/Downloads/setup.pdf")]
    opener = FakeFileOpener({h.path for h in hits})
    skill = FilesSkill(FOLDERS, FakeSearch(hits), opener)
    amb = skill.execute("abrir_arquivo", file_slot("setup"), CTX)
    assert isinstance(amb, AmbiguousSlot)
    chosen = file_slot(amb.candidates[0])  # what the assistant sends back after "o primeiro"
    assert skill.execute("abrir_arquivo", chosen, CTX) == ProgramRevealed("setup.lnk")
    assert opener.opened == [] and opener.revealed == ["C:/U/Downloads/setup.lnk"]

def test_one_exact_name_opens_even_with_partial_matches() -> None: ...
def test_listing_shows_the_five_newest_first() -> None: ...
def test_search_failure_is_explained() -> None: ...
def test_nothing_downloaded_today() -> None: ...
```
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5: commit** `feat(skills): folders, file search and recent files`.

---

### Task 8: Files adapters and config `[folders]`

**Files:**
- Create: `src/sazed/adapters/windows/files.py`
- Modify: `src/sazed/runtime/config.py`, `src/sazed/adapters/CLAUDE.md`,
  `src/sazed/runtime/CLAUDE.md`, `config.example.toml` (if present; else the config doc block in
  `runtime/CLAUDE.md`)
- Test: `tests/runtime/test_config.py`, `tests/adapters/test_files_adapter.py` (pure parts),
  `tests/adapters/test_windows_files.py` (`@pytest.mark.windows`)

**Interfaces — Produces:**
- `Config.folders: dict[str, Path]` with validator: names not blank (`_names_not_blank`);
  `effective_folders() -> dict[str, Path]` drops non-directories (logged by wiring, not in the
  pure config).
- `WindowsKnownFolders(configured: Mapping[str, Path])` — `SHGetKnownFolderPath` via
  `ctypes.windll.shell32` for FOLDERID_Downloads `{374DE290-123F-4565-9164-39C4925E467B}`,
  Documents `{FDD39AD0-238F-46AF-ADB4-6C85480369C7}`, Desktop
  `{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}`, Pictures `{33E28130-4E1E-4676-835A-98395C3BC3BB}`,
  Videos `{18989B1D-99B5-455B-841C-AB7C74E4DDFC}`, Music `{4BD8D571-6D19-48D3-BE97-422220080E43}`,
  Screenshots `{B7BEDE81-DF94-4682-A7D8-57A52620B86F}`; configured names override.
- `WindowsFileSearch(scopes: Sequence[str])` — `pythoncom.CoInitialize()` per call (the REPL and
  dashboard threads differ); `win32com.client.Dispatch("ADODB.Connection")`;
  `Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")`;
  `rs, _ = conn.Execute(sql)`; rows → `FileHit` (`modified` converted to naive local time);
  any `pywintypes.com_error` → `SearchError`. `newest`: when `newest_sql` returns nothing and
  the folder is not under an indexed scope, list it with `os.scandir` (files only) sorted by
  `st_mtime` — a pure `newest_from_listing(entries, since, limit)` is unit-tested.
- `WindowsFileOpener` — `open`: re-check `is_program` (raises `ValueError` — the load-bearing
  guard) then `os.startfile`; `reveal`: `subprocess.Popen(["explorer.exe", f"/select,{path}"])`;
  `exists`: `os.path.exists`.

- [ ] **Step 1: failing tests.**
  - config: `[folders] projetos = "<tmp>"` loads; blank name rejected with a pt-BR message;
    `effective_folders` drops a missing path.
  - `test_opener_refuses_a_program_even_if_the_skill_did_not`:
    `pytest.raises(ValueError): WindowsFileOpener().open("C:/x/evil.bat")` (pure: raises
    before `os.startfile`).
  - `newest_from_listing` ordering/since/limit.
  - windows (marked): known folders resolve to existing dirs and Downloads ends with
    `Downloads`; create `Documents/sazed-2b-<uuid>.txt`, poll `search([uuid], [], 6)` up to 30 s
    (skip with reason if never indexed), assert the hit; delete the file; `SearchError` is not
    raised for a normal query.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS (fast + `-m windows
  tests/adapters/test_windows_files.py`).
- [ ] **Step 5: commit** `feat(adapters): known folders, Windows Search and safe file opening`.

---

### Task 9: WindowControl adapter

**Files:**
- Modify: `src/sazed/adapters/windows/windows.py`, `src/sazed/adapters/CLAUDE.md`
- Test: `tests/adapters/test_window_choice.py` (pure additions),
  `tests/adapters/test_windows_windows.py` (`@pytest.mark.windows`)

**Interfaces — Produces:** `WindowsWindowControl()` implementing `WindowControl`.
- `own_pids` computed once in `__init__`: `psutil.Process()` and all `.parents()`.
- `windows(entry)`: `EnumWindows` → `RawWindow` (visible `IsWindowVisible`; cloaked
  `DwmGetWindowAttribute(hwnd, 14)`; tool `GWL_EXSTYLE & WS_EX_TOOLWINDOW`; owned
  `GetWindow(hwnd, GW_OWNER) != 0`; child pids as in `launcher.py`); `app_pids` from
  `entry_matcher(entry)` over `psutil` (None when `entry is None`); `choose_windows`; then
  `WindowRef` with state from `GetWindowPlacement().showCmd` (2 min, 3 max), visible rect from
  `DWMWA_EXTENDED_FRAME_BOUNDS` (9), monitor number via `MonitorFromWindow` matched to
  `monitors()`.
- `monitors()`: `win32api.EnumDisplayMonitors()` + `GetMonitorInfo` → sort by (left, top) →
  number = index + 1. Pure `number_monitors(list[(Rect work, bool primary)])` unit-tested.
- `focus`: restore if minimised; `SetForegroundWindow`; if `GetForegroundWindow() != hwnd`:
  `keybd_event(VK_MENU, 0, 0, 0)` / `keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)` and retry;
  still not → `FlashWindowEx(hwnd, FLASHW_ALL | FLASHW_TIMERNOFG, 3, 0)`, return False.
- `place(hwnd, rect)`: restore if min/max; frame offsets = `GetWindowRect` − extended frame
  bounds; `SetWindowPos(hwnd, 0, l - dl, t - dt, w + dl + dr, h + dt + db, SWP_NOZORDER |
  SWP_NOACTIVATE)`. Pure `outer_rect(visible: Rect, window: Rect, frame: Rect) -> Rect`
  unit-tested.
- `show_desktop` / `undo_show_desktop`: `win32com.client.Dispatch("Shell.Application")
  .MinimizeAll()` / `.UndoMinimizeALL()` (with `CoInitialize`).

- [ ] **Step 1: failing tests.** Pure: `number_monitors` puts a negative-x monitor first;
  `outer_rect` adds the invisible borders. Windows (marked), on Character Map launched by the
  test and closed at the end: `windows(entry)` finds it and not the console;
  minimise → `GetWindowPlacement` shows 2; restore → 1; maximise → 3; snap left via
  `place(hwnd, half(work, "esquerda"))` → visible rect within 8 px of the half; `focus` →
  foreground is it (skip-with-reason if Windows refuses in the test environment); show desktop
  / undo leaves it restored.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5: commit** `feat(adapters): window control through Win32`.

---

### Task 10: Wiring, the focus-offers-open flow, fixture, evaluation

**Files:**
- Modify: `src/sazed/runtime/skills.py` (`PcPorts.windows`, `.folders`, `.files`,
  `.file_opener`; `build_skills` adds both skills; `SkillSet.folder_names`),
  `src/sazed/runtime/wiring.py` (real adapters; log dropped folders),
  `src/sazed/runtime/evaluation.py` (`DryRunPorts` implements the new ports; `NluCase` gains
  `lado`, `pasta`, `arquivo` and `_is_false_execute` checks them),
  `src/sazed/runtime/assistant.py` (focus offer), `tests/support/harness.py`,
  `tests/fixtures/nlu_cases.toml`, `scripts/measure_app.py` (if it builds ports by hand)
- Test: `tests/runtime/test_skills.py`, `tests/runtime/test_assistant_dialogue.py`,
  `tests/nlu/test_fixture.py` (model), `tests/runtime/test_learning_with_model.py` (model)

- [ ] **Step 1: failing tests.**
  - `test_every_skill_is_built_once` lists `windows` and `files`.
  - Dialogue: `"vai pro spotify"` with no Spotify window → text ends "Devo abrir?"; `"sim"` →
    `launcher.launched == ["Spotify"]` and `learned(h) == []`; `"não"` → nothing launched.
  - Dialogue: ambiguous file → `"o segundo"` opens the second hit's path.
  - Model: after teaching `"minimiza aí o spotify"` (confirm + sim), `"maximiza o spotify"`
    ranks `janela_maximizar`.
  - Fixture: ~50 new cases (spec §9), including `intent = "none"` cases and near-ties:
    "mostra o spotify" (focar) / "abre o spotify" (abrir_app); "abre a pasta downloads"
    (abrir_pasta) / "abre o último download" (abrir_recente) / "abre o arquivo downloads"
    (abrir_arquivo); minimise/maximise/restore of the same app; "joga o chrome pra esquerda"
    vs "manda o chrome pro outro monitor"; "minimiza tudo" vs "minimiza o chrome". None copy
    a seed (`test_fixture_rules.py`).
- [ ] **Step 2:** FAIL. **Step 3: implement.** Focus offer in `Assistant._execute`:

```python
        if isinstance(outcome, WindowNotFound) and outcome.offer_open:
            app = slots.get("app")
            if isinstance(app, SlotValue):
                # "vai pro X" meant focus: opening it is offered, never learned as "open".
                offer = AwaitConfirm("abrir_app", {"app": app}, u.normalized, learn_example=False)
                self._ctx = self._ctx.with_pending(offer, self._now)
```
  Seeds: tune only if the fixture shows a confusion; record each seed change and its
  before/after numbers in the proofs file.
- [ ] **Step 4:** fast suite, `-m model` PASS; fixture numbers recorded (accuracy ≥ 0.90,
  false-execute 0.000).
- [ ] **Step 5: commit** `feat(runtime): wire window and file skills; focus offers to open`.

---

### Task 11: By hand, measurements, docs

**Files:**
- Create: `scripts/measure_search.py`, `docs/superpowers/proofs/2026-10-16-sub-project-2b.md`
  (if not created earlier)
- Modify: `CLAUDE.md` (status, measurements, verified by hand, unverified, next step)

- [ ] **Step 1:** `scripts/measure_search.py`: 20 queries of common words through
  `WindowsFileSearch` → median / p95 ms. Run; record.
- [ ] **Step 2:** `uv run python scripts/measure_app.py` → startup and RSS; record.
- [ ] **Step 3: by hand** through the real `Assistant` with a temp data dir (scratchpad
  script): open Character Map; "minimiza o character map", "restaura o character map",
  "maximiza o character map", "joga o character map pra esquerda", "vai pro character map",
  "minimiza tudo", "volta as janelas", "fecha o character map"; "abre a pasta downloads" (then
  close that Explorer window by hand-script: `WM_CLOSE` to the window titled Downloads);
  "acha o arquivo sazed-2b-<uuid>" on a temp file; "abre o último print"; "quais arquivos
  baixei hoje". **Ask the user to switch the second monitor on** for "manda o character map
  pro outro monitor"; if not possible, record as unverified.
- [ ] **Step 4:** full verification: `uv run pytest`, `uv run pytest -m model`,
  `uv run pytest -m windows -k "not media"`, ruff check, ruff format --check, mypy.
- [ ] **Step 5: commit** `docs: sub-project 2b by-hand results, measurements and proofs`.
