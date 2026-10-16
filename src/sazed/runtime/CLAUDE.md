# sazed.runtime

Wires config, adapters, skills and the assistant together; the only place the clock is read.

## Conventions
- Every skill is built by `skills.build_skills(PcPorts, Config)`. Wiring, evaluation, scripts and
  the test harness all call it, so a new skill appears everywhere at once.
- `DryRunPorts` implements every port and never touches the machine; evaluation relies on it.
- `Assistant._learn` is the single gate for learned examples (`IntentSpec.learnable`), and the
  REPEAT control never falls through to ranking.
- Every learned example goes through `Assistant.learnable_text` first (conversation and
  `admin` alike): for intents with an `app` slot the app name becomes "programa". Without it a
  learned "abre o whatsapp" made "fecha o whatsapp" rank opening (e5 weighs the object).
- `admin` holds every learned-item edit (CLI and dashboard share it): validate first, write
  once. `learn_example` is the one path for examples taught outside a conversation
  (`label_episode` uses it) and applies masking, `learnable`, dedupe and conflict-unless-forced.
- `editing.Editor` is the dashboard's writer: one thread, lazy model (examples only), undo for
  forget. Its ports raise on use; the dashboard never executes a skill.
- `[folders]` in config adds folders by name; a configured name that matches a known folder
  overrides it. A missing directory does not stop startup: it is logged and answered as
  `FolderNotFound` when asked.
- Folder names for the extractor come from `KNOWN_FOLDERS` plus config, never from the
  folders port (the dashboard's inert ports raise when called).
- `janela_focar` on a closed app leaves a pending "abrir?" with `learn_example=False`.
- File changes: a `FileChangeProposed` outcome becomes `AwaitPlan`; only "sim" calls the
  skill's `apply_pending` (re-checks the disk first). "desfaz isso" (`ControlKind.UNDO`) asks the
  `PlanningSkill` for an undo plan, confirmed the same way. A pending plan never reaches `_learn`.
  `build_skills(..., change_log=store)`: without a store (dashboard, evaluation) a no-op log.
- `RAW_SLOTS` (`novo_nome`) get the original text, so a new file name keeps its case.

## Traps
- Import onnxruntime before WinRT in any process that will load both (`build_default_app`
  imports the embedder first; `editing.real_catalog` does it explicitly). The other order is a
  native access violation.
- Removing a learned example must also leave this session's index (`index.remove`), or the next
  dedupe judges against a ghost.
- Sites are catalog entries (`CombinedCatalog`); an installed app with the same name wins.
- `DEFAULT_APP_ALIASES` are added only for apps present in the catalog; config aliases win.
- Turns can share a timestamp (tests use a manual clock): track "this turn ran a command" by
  `LastTurn` identity, never by comparing times.

## Not here
Skill logic (→ `skills`), OS access (→ `adapters`), the REPL and its pt-BR strings (→ `interfaces`).
