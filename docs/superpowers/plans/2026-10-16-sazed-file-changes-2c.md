# Sazed 2c (move, copy, rename, delete, new folder, undo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** typed pt-BR commands that move, copy, rename and delete files and folders and create
folders inside the user's own folders — each confirmed with its exact effect, logged, and
undoable with "desfaz isso".

**Architecture:** a pure `FileOpsSkill` resolves the item, builds a `ChangePlan` and returns
`FileChangeProposed`; the runtime holds it as a pending plan and applies it only on "sim",
after re-checking the disk. A `FileChanger` port (Windows adapter: os/shutil + the Recycle Bin
through the shell) does the work; a `ChangeLog` port (coppermind migration 3) records each
change for undo.

**Tech Stack:** Python 3.12 (uv), stdlib `os`/`shutil`, pywin32 (`win32com.shell`,
`win32com.client`), SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-10-16-sazed-file-changes-2c-design.md`

## Global Constraints

- TDD for every behaviour; discrimination proofs appended to
  `docs/superpowers/proofs/2026-10-16-sub-project-2c.md`.
- Conventional Commits in English ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- pt-BR user-facing text via the persona; code and docs in English.
- `core`/`nlu` pure; skills import only `sazed.core` (and other skills); adapters may import skills.
- Nothing on disk changes without "sim" to a confirmation of the exact plan. Nothing is ever
  overwritten or permanently deleted.
- 2c intents: `learnable=False`, `repeatable=False`, `confirms_itself=True`.
- Real-desktop tests only touch a temporary folder they create under the user profile.
- Fixture bar: accuracy ≥ 0.90, false-execute 0.000; thresholds unchanged.
- Seeds: ≥ 8 per intent, normalised, unique, never the word "programa".

## Deviations from the spec

- **The item slot is an encoded string** (`"ultimo:Downloads"`, `"pasta:viagem"`,
  `"arquivo:relatório"`): skills may not import `nlu`, so the extractor classifies and the skill
  decodes (`decode_item`, pure, tested). Cost if wrong: one encode/decode pair to replace.
- **`novo_nome` is read from the original text** (`Utterance.text`) for case and punctuation:
  `RAW_SLOTS = {"novo_nome"}` in the runtime passes the raw text to that extractor only.

## Review Focus

1. A path that resolves outside the allowed area through a junction, a symlink or `..` must be
   refused — pure tests with a fake `realpath` (Task 2).
2. A file changed or removed between the question and "sim" must leave the disk untouched
   (Task 7).
3. "apaga a pasta downloads" / "renomeia a área de trabalho" (a known folder itself) refused;
   the same folders accepted as a destination (Task 2, Task 6).
4. A name without an extension and a folder name both get "(2)" correctly (`free_name`; the
   old `unique_name` produced " (2)foo" for a dotless name) (Task 2).
5. A cross-drive move that fails halfway keeps the original and removes the partial copy (Task 9,
   fakes for the second drive).

---

### Task 1: Outcomes and pt-BR templates

**Files:** `src/sazed/core/outcomes.py`, `src/sazed/core/persona/definition.py`,
`tests/core/persona/test_persona.py`

**Produces** (`@dataclass(frozen=True)`):
- Success: `FileChangeProposed(action: str)` (the plan's own pt-BR description; the plan object
  travels separately, see Task 6), `FileMoved(name: str, folder: str)`,
  `FileCopied(name: str, folder: str)`, `FileRenamed(old: str, new: str)`,
  `FileRecycled(name: str)`, `FolderCreated(name: str, folder: str)`, `ChangeUndone(action: str)`.
- Failure: `Protected(name: str)`, `IntoItself(name: str)`, `BadName(name: str, reason: str)`,
  `NameTaken(name: str)`, `PlanChanged()`, `FileBusy(action: str, name: str)`,
  `NoRecycleBin(name: str)`, `NothingToUndo()`, `UndoStale(name: str)`,
  `NotInRecycleBin(name: str)`.

Templates:
```python
    "FileChangeProposed": ("{action}. Confirma, {mestre}?",),
    "FileMoved": ("Pronto, {mestre}. {name} está em {folder}.",),
    "FileCopied": ("Pronto, {mestre}. Há uma cópia de {name} em {folder}.",),
    "FileRenamed": ("Pronto, {mestre}. {old} agora se chama {new}.",),
    "FileRecycled": ("{name} foi para a Lixeira, {mestre}.",),
    "FolderCreated": ("Criei a pasta {name} em {folder}, {mestre}.",),
    "ChangeUndone": ("Desfeito, {mestre}: {action}.",),
    "Protected": ("Por segurança, não mexo em {name}, {mestre}.",),
    "IntoItself": ("Não dá para colocar a pasta {name} dentro dela mesma, {mestre}.",),
    "BadName": ("Esse nome não serve para arquivos, {mestre}: {reason}.",),
    "NameTaken": ("Já existe '{name}' nessa pasta, {mestre}.",),
    "PlanChanged": ("O arquivo mudou desde que perguntei, {mestre}; não fiz nada.",),
    "FileBusy": (
        "Não consegui {action} {name}, {mestre}: ele está aberto em outro programa ou sem permissão.",
    ),
    "NoRecycleBin": ("Essa unidade não tem Lixeira, {mestre}; não vou apagar {name}.",),
    "NothingToUndo": ("Não há nada para desfazer, {mestre}.",),
    "UndoStale": ("{name} mudou depois, {mestre}; não vou desfazer.",),
    "NotInRecycleBin": ("{name} já não está na Lixeira, {mestre}; não consigo desfazer.",),
```
- [ ] Step 1: value tests for `FileChangeProposed`, `BadName`, `FileBusy` renders (the generic
  persona tests already demand a template per type). Step 2: FAIL. Step 3: implement. Step 4:
  PASS. Step 5: commit `feat(core): outcomes and pt-BR answers for file changes`.

---

### Task 2: Pure safety rules and names

**Files:** create `src/sazed/skills/pc/fileops.py` (pure part); modify
`src/sazed/adapters/windows/screen.py` (use `free_name`); test `tests/skills/test_fileops_rules.py`

**Produces:**
```python
@dataclass(frozen=True)
class Area:
    roots: tuple[str, ...]          # user profile + [folders]
    protected: tuple[str, ...]      # roots themselves, known folders, AppData, data dir, project
    realpath: Callable[[str], str]  # os.path.realpath in production

def check_source(path: str, area: Area) -> Protected | None
def check_destination(folder: str, area: Area) -> Protected | None
def name_problem(name: str) -> str | None      # pt-BR reason or None
def free_name(name: str, taken: Collection[str]) -> str   # case-insensitive; "x (2).ext"; dotless "x (2)"
def keep_extension(old: str, new: str, is_dir: bool) -> str
def is_inside(child: str, parent: str) -> bool  # normcase, separator-aware, after realpath
```
Rules exactly as spec §5. Drive roots are protected by shape (`C:\`), AppData by any path
segment equal to `appdata` under the profile.

- [ ] Step 1: failing tests: `..` escape (`C:/Users/a/Documents/../../b/x`), junction via fake
  realpath mapping `C:/Users/a/link` → `D:/elsewhere`, drive root, each known folder as source
  (parametrised from the `Area.protected` the test builds), the same folders accepted by
  `check_destination`, case and trailing separator variants, AppData; names: empty, spaces only,
  each invalid char (parametrised from the constant), reserved names with and without extension
  (`con`, `NUL.txt`, `com1`), trailing dot/space; `free_name` with extension, without, folder,
  case-insensitive taken set, "(2)" taken → "(3)"; `keep_extension` ("contrato assinado" +
  `.pdf`; already ending in `.pdf` not doubled; folders unchanged).
- [ ] Step 2: FAIL. Step 3: implement; `screen.py` uses `free_name` (its own test still passes).
- [ ] Step 4: PASS + proof mutations (drop `realpath`; drop the dotless branch). Step 5: commit
  `feat(skills): safety rules and names for file changes`.

---

### Task 3: Plans and undo plans (pure)

**Files:** `src/sazed/skills/pc/fileops.py`, test `tests/skills/test_fileops_plans.py`

**Produces:**
```python
ChangeKind = Literal["mover", "copiar", "renomear", "apagar", "criar"]

@dataclass(frozen=True)
class ItemState:
    path: str; is_dir: bool; size: int; mtime: float; count: int   # count = files inside (dirs)

@dataclass(frozen=True)
class ChangePlan:
    kind: ChangeKind
    source: str | None          # None for "criar"
    target: str                 # full final path
    is_dir: bool
    before: ItemState | None    # source state at planning time (re-checked before applying)
    renamed_for_clash: bool
    undo_of: int | None = None  # change-log id when this plan undoes a change

@dataclass(frozen=True)
class LoggedChange:
    id: int; kind: ChangeKind; source: str | None; target: str; is_dir: bool
    size: int; mtime: float; recycle_ref: str | None

def plan_change(kind, source: ItemState | None, folder: str | None, new_name: str | None,
                taken: Collection[str], area: Area) -> ChangePlan | Outcome
def plan_undo(change: LoggedChange, now: ItemState | None, original_free: bool) -> ChangePlan | Outcome
def describe_plan(plan: ChangePlan) -> str      # pt-BR, e.g. "Mover relatório.docx de Downloads para Documentos"
def human_size(size: int) -> str                # "2,3 GB" (pt-BR decimal comma)
```
- [ ] Step 1: failing tests: every kind's plan and description (exact strings incl. the clash
  note "Já existe relatório.docx lá; vou salvar como relatório (2).docx" and the folder count
  "Apagar a pasta viagem (128 arquivos, 2,3 GB) para a Lixeira"); folder into itself and into a
  subfolder → `IntoItself`; rename onto a taken name → `NameTaken`; create existing →
  `NameTaken`; protected source → `Protected`; bad name → `BadName`; `plan_undo` for each kind,
  `UndoStale` when size/mtime differ or the item is gone, `NotInRecycleBin` handled at apply
  (Task 6), original name taken → `UndoStale`.
- [ ] Step 2: FAIL. Step 3: implement. Step 4: PASS + proof (mutation: drop the into-itself
  check). Step 5: commit `feat(skills): plans and undo plans for file changes`.

---

### Task 4: Slots and the undo phrase

**Files:** create `src/sazed/nlu/slots/change.py`; modify `src/sazed/nlu/control.py`,
`src/sazed/runtime/extractors.py`, `src/sazed/runtime/assistant.py` (`RAW_SLOTS`);
tests `tests/nlu/test_slot_change.py`, `tests/nlu/test_control.py`, `tests/runtime/test_extractors.py`

**Produces:**
- `extract_item(normalized, folder_names, synonyms) -> SlotValue | None` — value
  `"ultimo:<Folder>"`, `"pasta:<words>"` or `"arquivo:<words>"` (words without verbs, fillers,
  type words; the destination part removed).
- `extract_destination(normalized, folder_names, synonyms) -> SlotValue | Unmatched | None` —
  after the **last** "pra/para/pro/na/no/em" (+ optional "a pasta"); known → canonical name;
  unknown → `Unmatched("destino", words, None)` (the skill then searches a folder by name).
- `extract_new_name(raw_text) -> SlotValue | None` — after the last "pra/para/como/chamada/chamado"
  in the original text, case and punctuation kept, trailing `.?!` and quotes stripped.
- `ControlKind.UNDO` for "desfaz isso", "desfaz", "desfazer", "volta atras", "desfaca isso",
  "desfaz o que voce fez".
- Runtime: `RAW_SLOTS = frozenset({"novo_nome"})`; `Assistant._extract` passes `u.text` to those.

Cases (all tested): "move o relatório de vendas pra pasta projetos" → item `arquivo:relatório
vendas`, destino `Projetos`; "manda o último download pra área de trabalho" → `ultimo:Downloads`,
`Área de Trabalho`; "copia a planilha de gastos pra pasta projetos" → `arquivo:gastos` (+ tipo
planilha); "renomeia o arquivo contrato pra Contrato Assinado" → item `arquivo:contrato`,
novo_nome `Contrato Assinado`; "muda o nome da pasta viagem pra viagem 2025" → `pasta:viagem`,
`viagem 2025`; "apaga a pasta temporários" → `pasta:temporários`; "joga o último print no lixo"
→ `ultimo:Capturas de Tela` and **no destination** ("no lixo" is not a folder: "lixo"/"lixeira"
are stop words); "cria uma pasta chamada viagem na área de trabalho" → novo_nome `viagem`
(the name stops before the destination marker), destino `Área de Trabalho`.
- [ ] Steps: failing tests → implement → PASS → proof (mutation: split on the first marker
  instead of the last) → commit `feat(nlu): item, destination and new-name slots; undo phrase`.

---

### Task 5: `confirms_itself` in the policy

**Files:** `src/sazed/core/skill.py` (`IntentSpec.confirms_itself: bool = False`),
`src/sazed/core/policy.py` (`IntentRequirements.confirms_itself`), `src/sazed/runtime/assistant.py`
(pass it), tests `tests/core/test_policy.py`

Rule: when `confirms_itself`, `LOW_SCORE` and `SMALL_GAP` confirms become `Execute`; below
`t_confirm` still `NotUnderstood`; missing required slots still `AskSlot`.
- [ ] Steps: failing policy tests (each reason; below t_confirm; AskSlot unaffected) → implement →
  PASS → proof (mutation: only LOW_SCORE handled) → commit
  `feat(core): intents that confirm through their own plan`.

---

### Task 6: `FileOpsSkill` and its ports

**Files:** `src/sazed/skills/pc/fileops.py`, `tests/fakes/ports.py` (+ tests), test
`tests/skills/test_fileops_skill.py`, `src/sazed/skills/CLAUDE.md`

**Produces:**
```python
class FileChanger(Protocol):
    def state(self, path: str) -> ItemState | None: ...
    def names_in(self, folder: str) -> set[str]: ...
    def move(self, src: str, dst: str) -> None: ...
    def copy(self, src: str, dst: str) -> None: ...
    def rename(self, src: str, dst: str) -> None: ...
    def make_folder(self, path: str) -> None: ...
    def can_recycle(self, path: str) -> bool: ...
    def recycle(self, path: str) -> str: ...          # recycle_ref
    def restore(self, ref: str) -> bool: ...
class ChangeBusy(Exception): ...                     # locked / permission (adapter raises)
class ChangeLog(Protocol):
    def record(self, plan: ChangePlan, after: ItemState | None, recycle_ref: str | None, at: datetime) -> int: ...
    def latest_open(self) -> LoggedChange | None: ...
    def mark_undone(self, change_id: int, at: datetime) -> None: ...
class FileOpsSkill:
    def __init__(self, folders: KnownFolders, search: FileSearch, changer: FileChanger,
                 log: ChangeLog, area: Area) -> None
    intents: arquivo_mover, arquivo_copiar, arquivo_renomear, arquivo_apagar, pasta_criar
    def execute(intent_id, slots, ctx) -> Outcome      # resolve → FileChangeProposed (sets self.proposed)
    proposed: ChangePlan | None                        # the plan behind the last FileChangeProposed
    def apply(self, plan: ChangePlan, ctx) -> Outcome  # re-check, act, log
    def propose_undo(self, ctx) -> Outcome             # FileChangeProposed or NothingToUndo/UndoStale
```
Resolution: `ultimo:<Folder>` → `search.newest(folder, None, 1)`; `pasta:<words>` → a folder by
name (`search.search` restricted to folders — add `FileSearch.folders(words, limit)` to 2b's
port and fakes, adapter query `System.Kind = 'folder'`); `arquivo:<words>` → 2b search with tipo;
several → `AmbiguousSlot("item", labels)` with labels mapped back like 2b `_shown`.
Re-check at `apply`: `changer.state(source)` equals `plan.before` (size and mtime), target name
still free, area checks again; else `PlanChanged`. `ChangeBusy` → `FileBusy`. Recycle on a drive
without bin → `NoRecycleBin` (checked at planning and again at apply).
- [ ] Steps: failing tests for every spec §6 row, the clash renaming, folder counts, the
  re-check (state changed → `PlanChanged`, and the fake records **no** call), undo of each kind,
  `restore` False → `NotInRecycleBin` and the row closed → implement → PASS → proofs (mutation:
  skip the re-check) → commit `feat(skills): file changes planned, confirmed and logged`.

---

### Task 7: Runtime — pending plan, undo control, never learned, safety test

**Files:** `src/sazed/core/context.py` (`AwaitPlan(intent_id, plan_id, utterance)`; the plan
object stays in the skill keyed by a counter), `src/sazed/runtime/assistant.py`,
tests `tests/runtime/test_fileops_dialogue.py`, `tests/runtime/test_fileops_safety.py`

Flow: `_execute` gets `FileChangeProposed` → pending `AwaitPlan`; "sim" → `skill.apply(plan)`;
"não" → `Cancelled`; any other phrase drops the plan (like other pendings). `UNDO` control →
`skill.propose_undo` → same pending. A plan pending is never learned from.
- [ ] Steps: failing tests: move asked once (text = plan description) → "sim" applies → log row
  re-read from SQLite; changed between → nothing; "não" → nothing; undo asked → applied → row
  `undone_at` set; ambiguous item → "o segundo" → plan for that file; safety test derived from
  `SPECS` (every `confirms_itself` intent, scripted scores 0.89/0.95/1.0, plus
  `learn_example(...)` attempt → `NOT_LEARNABLE`): the fake changer has no call before "sim".
  → implement → PASS → proofs → commit `feat(runtime): confirm and apply file-change plans; undo`.

---

### Task 8: Coppermind migration 3 (change log)

**Files:** `src/sazed/adapters/sqlite/coppermind.py`, `src/sazed/adapters/sqlite/reader.py`
(only if its schema tests require), tests `tests/adapters/test_coppermind_changes.py`

`MIGRATIONS[2]`: `CREATE TABLE file_changes(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, source
TEXT, target TEXT NOT NULL, is_dir INTEGER NOT NULL, size INTEGER NOT NULL, mtime REAL NOT NULL,
recycle_ref TEXT, at TEXT NOT NULL, undone_at TEXT)`. `SqliteCoppermind` implements
`ChangeLog`.
- [ ] Steps: failing tests: v2 database (built through the writer at version 2, then reopened)
  upgrades to 3 with examples/aliases/notes intact; record/latest_open/mark_undone round-trip
  re-read through a fresh connection; latest_open skips undone rows; dashboard reader opens a
  v3 file read-only → implement → PASS → commit `feat(adapters): change log in the coppermind`.

---

### Task 9: `WindowsFileChanger`

**Files:** create `src/sazed/adapters/windows/fileops.py`; tests
`tests/adapters/test_fileops_adapter.py` (pure + tmp_path, runs anywhere on Windows CI),
`tests/adapters/test_windows_fileops.py` (`-m windows`)

Per spec §8. Cross-drive: pure `move_across(src, dst, copy, remove, size_of)` taking callables,
so the failure path is tested with fakes: copy raises → partial target removed, source kept;
size mismatch → same. `state` counts files with `os.scandir` recursion bounded at 100 000.
`recycle`: `win32com.shell.shell.SHFileOperation((0, shellcon.FO_DELETE, path, None,
FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI, None, None))`; ref = JSON
`{"path": ..., "at": iso}`. `restore`: `Shell.Application().Namespace(10)`, item whose
`ExtendedProperty("System.Recycle.DeletedFrom")` + name match, deletion date closest to `at`
(within 2 min); `InvokeVerb("undelete")`; True when the original path exists afterwards.
`PermissionError`/`OSError` with winerror 32/33/5 → `ChangeBusy`.
- [ ] Steps: failing tests (tmp_path: move same-drive, copy file/folder, rename, make_folder,
  state counts; fakes for cross-drive failure) → implement → PASS → `-m windows`: a temp folder
  under the profile: recycle then restore round-trip; a file locked with `msvcrt.locking` refuses
  to move (`ChangeBusy`) → commit `feat(adapters): file changes on Windows with the Recycle Bin`.

---

### Task 10: Wiring, fixture, evaluation

**Files:** `src/sazed/runtime/skills.py` (`PcPorts.changer`, `.change_log`; `Area` from
config + profile + known folders + data dir + project), `runtime/wiring.py`, `runtime/editing.py`
(inert), `runtime/evaluation.py` (DryRun), `runtime/insight.py` (port descriptions),
`tests/support/harness.py`, `tests/fixtures/nlu_cases.toml`, `tests/skills/test_specs.py`
- [ ] Steps: failing tests (skills list, port descriptions, extractors for new slots) → wire →
  ~40 fixture cases incl. near-ties (move/copy, delete/open, rename/create, "desfaz" phrases
  are controls not cases) and `none` cases ("apaguei a luz", "mudei de casa", "copiei a prova")
  → measure with the real model; tune seeds as in 2b (no seed with "programa"; window/file seeds
  keep their objects) until accuracy ≥ 0.90 and false-execute 0.000 → model suite green →
  commit `feat(runtime): wire file changes`.

---

### Task 11: By hand, measurements, docs

- [ ] By hand through the real `Assistant` (temp data dir) on files the script creates in a temp
  folder under Documents: move, copy, rename, create, delete, each confirmed, then "desfaz isso"
  for each; a protected target ("apaga a pasta downloads") refused; cleanup.
- [ ] `scripts/measure_app.py` → startup/RSS.
- [ ] Full verification: fast, model, `-m windows -k "not media"`, ruff, format, mypy.
- [ ] Docs: root `CLAUDE.md` status/verified/unverified/next; local `CLAUDE.md` files.
- [ ] Commit `docs: sub-project 2c by-hand results, measurements and proofs`.
