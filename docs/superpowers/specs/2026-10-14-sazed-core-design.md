# Sazed — Sub-project 1: Core + text CLI + PC slice

Date: 2026-10-14
Status: Approved in brainstorm, pending written-spec review

## 1. Context and intent

Sazed is a local, offline, JARVIS-style personal assistant for Windows 11. It must
never call an external AI API. Commands are understood by a deterministic NLU core
(intent recognition + entity/slot extraction, pt-BR); a free, local small language
model (SLM, 1–3B) is loaded only on demand, as a fallback and for conversation.

**What the user asked for:**
- Priorities: (A) control the PC, (B) personal organization, (C) conversation /
  knowledge; plus a study-partner function.
- Voice first, but also a text interface, possibly in the browser.
- A small local model, never an external API. Chosen architecture: deterministic core
  + SLM as fallback that translates unrecognised commands into known intents.
- Persistent, continuous learning: errors must always become learning.
- Persona: Sazed, the Terris Keeper from Brandon Sanderson's *Mistborn*. Masculine
  pt-BR. Addresses the user as "Mestre Artur".

**Hardware constraint:** Ryzen 5 8600G, ~12 GB RAM, integrated Radeon 760M only. All
inference is CPU-bound; idle memory must stay low because the assistant is always on.

### 1.1 Roadmap (each sub-project gets its own spec → plan → implementation)

1. **Core + text CLI + PC slice** ← this spec
2. PC skills (apps, windows, media, files)
3. Organization skills (reminders, alarms, timers, notes; scheduler + persistence)
4. Voice (wake word "Sazed", STT, TTS)
5. Browser interface (local web chat over the same core)
6. SLM fallback (tool-calling into known intents) + free conversation
7. Study partner

### 1.2 Success criteria for this sub-project

- In the terminal, pt-BR phrases open and close installed applications and control
  the system volume.
- Each command ends in exactly one of: execute, confirm, ask for a missing slot,
  not understood. The decision follows from calibrated scores.
- Confirmations, corrections and slot choices are learned, persist across restarts and
  change later decisions.
- Every response is in Sazed's voice, in pt-BR, and never leaks internals.
- The NLU fixture meets the accuracy and false-execute thresholds (§10, item 4).

### 1.3 Out of scope

Voice, the browser UI, the SLM, scheduling, automatic threshold tuning, frequency-based
preferences, an "update the app list" intent, and pattern suggestions ("you always
open X with Y"). The data model must not prevent any of them.

## 2. Stack

- Python **3.12**, pinned with `uv` (`.python-version`). The machine has 3.14, and ML
  wheels (onnxruntime, tokenizers) may lag behind it; this is confirmed during setup.
- `onnxruntime` + `tokenizers` for the embedder; `rapidfuzz` for fuzzy matching; `pycaw` for volume; `pywin32` for `.lnk` resolution
  and processes; `psutil` for running processes; `pydantic` for config; stdlib
  `sqlite3` for persistence. (`dateparser` arrives with sub-project 3; the slot
  extractor interface must not preclude it.)
- Dev: `pytest`, `ruff`, `mypy --strict` on `core` and `nlu`.
- Layout: `src/sazed/`, entry point `uv run sazed`.
- Own git repository at `C:\Programacao\JARVIS\Sazed`.

## 3. Architecture

Dependency direction is one-way:

```
interfaces (cli) → runtime → skills → core
                           ↘ nlu    → core
adapters (windows, onnx, sqlite) implement ports declared in core / skills
```

| Package | Responsibility | May import |
|---|---|---|
| `sazed.core` | Pure types, decision policy, dialogue context, learning rules, persona. No I/O, no clock, no models. | stdlib only |
| `sazed.nlu` | Normalisation, `Embedder` protocol, `IntentMatcher`, slot extractors. | `core` |
| `sazed.skills` | Skills: intents + examples + slot schema + `execute`. Calls ports only. | `core` |
| `sazed.adapters` | `windows/` (app catalog, launcher, audio), `onnx/` (embedder), `sqlite/` (coppermind store). | `core`, `nlu`, `skills` (to implement their ports) |
| `sazed.runtime` | `Assistant.handle(text) -> Response`; wiring; the **only** place the clock and the RNG seed are read. | everything except `interfaces` |
| `sazed.interfaces.cli` | Terminal REPL. Future voice/browser interfaces sit beside it. | `runtime` |

### 3.1 Core types (in `core`)

- `Utterance(text, normalized, received_at)`
- `IntentScore(intent_id, score)`; `Ranking` = ordered list
- `SlotValue(name, value, raw, confidence)`
- `ParseResult(utterance, ranking, slots, missing_slots)`
- `Decision` = `Execute | Confirm | AskSlot | NotUnderstood`
- `Outcome` = success outcomes per skill action + typed errors (§6)
- `Response(text, outcome, decision)` — `text` is always rendered by the persona

### 3.2 Skill contract

```python
class Skill(Protocol):
    id: str
    intents: list[IntentSpec]   # id, example phrases (pt-BR), slot schema,
                                # requires_confirmation predicate
    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome: ...
```

Skills never touch the OS. They call ports (`AppCatalog`, `AppLauncher`,
`AudioControl`), declared next to the skill and implemented in `adapters/windows`.

### 3.3 PC slice in this sub-project

| Intent | Example | Slots |
|---|---|---|
| `abrir_app` | "abre o chrome" | `app` (required) |
| `fechar_app` | "fecha o spotify" | `app` (required) |
| `volume_definir` | "volume em 30" | `percent` (required) |
| `volume_aumentar` / `volume_diminuir` | "aumenta o som" | `percent` (optional step, default 10) |
| `volume_mudo` | "muta" / "tira do mudo" | — |

Control intents handled by the runtime, not a skill: `confirmar` (sim), `negar` (não),
`corrigir` ("não, era X"), `esquecer` ("esquece isso").

## 4. Command flow

1. **Normalise** (pure): lowercase, collapse whitespace, strip punctuation. Accents are
   kept for the embedder and stripped only for catalog matching.
2. **Rank intents:** embed the utterance; for each intent the score is the maximum
   cosine similarity over its examples (seed + learned).
3. **Extract slots** for the top intent, running only the extractors it declares.
   `app`: fuzzy match against the app catalog plus learned aliases. `percent`: numbers,
   "metade", "%". Extractors return a value with confidence, `Ambiguous(candidates)`, or
   nothing.
4. **Decide** (pure, `core.policy`), from `top`, `gap = top − second` and slots:
   - `top ≥ T_exec` and `gap ≥ G_min` and all required slots resolved → `Execute`
     (unless `requires_confirmation` → `Confirm`)
   - `T_confirm ≤ top < T_exec`, or `gap < G_min` → `Confirm`
   - required slot missing → `AskSlot`; ambiguous slot → `AskSlot` with candidates
   - `top < T_confirm` → `NotUnderstood` (sub-project 6 plugs the SLM in here)
5. **Execute** the skill → `Outcome` → persona renders the `Response`.
6. **Record an episode** (§5.3) for every turn.

### 4.1 Dialogue context (pure, `core.context`)

- Holds the last executed intent + slots ("aumenta mais" repeats `volume_aumentar`).
- Holds at most one pending question (`Confirm` or `AskSlot`). The next utterance is
  first tried as an answer to it (`sim`/`não`/slot value) before normal ranking.
- Expires after `context_ttl_seconds`, computed from `now` passed in. An expired
  pending question is discarded; "sim" then gets `NotUnderstood`.

### 4.2 Destructive actions

`fechar_app` declares `requires_confirmation` when there are several running
instances or when the app match is not exact. It always confirms in those cases, even
at `top ≥ T_exec`.

## 5. Persistent learning — the coppermind

Learning means adding examples and aliases. Intents are recognised by examples, so a
new example takes effect immediately with no retraining.

**Principle:** learn only from explicit user signals, never from the assistant's own
guesses.

### 5.1 Learning signals

| Situation | Learned |
|---|---|
| `Confirm` answered "sim" | utterance → example of the confirmed intent |
| `Execute` followed (within TTL) by a correction "não, era X" | utterance → example of X; the misfire is recorded |
| `NotUnderstood`, then a rephrase within TTL that executes | Sazed asks "Posso guardar que '<original>' significa isso?"; on "sim", original → example |
| Ambiguous slot resolved by the user | alias (`"code"` → Visual Studio Code) |
| `AppNotFound`, then "é o Discord" | alias (`"disc"` → Discord) |
| (sub-project 6) SLM interpretation confirmed | utterance → example |

### 5.2 Safeguards (pure rules in `core.learning`)

- **Conflict:** if the candidate example scores ≥ `T_conflict` against another intent's
  examples, do not save silently; ask first.
- **Dedupe:** a candidate with similarity ≥ `T_dup` to an existing example of the same
  intent is not saved.
- **Forget:** "esquece isso" removes the most recent learned item. A CLI subcommand
  `sazed aprendizado` lists everything learned and removes items by id.
- The labelled NLU fixture never includes learned examples.

### 5.3 Episodes

Every turn records: utterance, ranking (top N with scores), extracted slots, decision,
outcome, and the user's reaction (confirmed / denied / corrected / none). This feeds
`sazed revisar` (lists recent failures for manual labelling) and future threshold
tuning.

### 5.4 Storage

SQLite (`sqlite3`) in a local data directory (`%LOCALAPPDATA%\Sazed\coppermind.db`,
configurable). Tables: `learned_examples` (id, text, intent_id, embedding BLOB,
origin, created_at), `slot_aliases` (id, slot, alias, value, created_at), `episodes`.
Any learning step writing more than one row runs in a single transaction. Embeddings
are stored with the example so startup does not recompute them. The schema carries a
version number, and migrations are explicit.

## 6. Errors

Typed errors in `core`, each rendered by the persona:

- `AppNotFound(query, suggestion?)`
- `AppNotRunning(app)`
- `AmbiguousSlot(slot, candidates)` → becomes a pending `AskSlot`
- `ActionFailed(action)`: an adapter failure. The user sees a generic persona
  message, and the real exception is logged only.

The runtime catches any unexpected exception, logs it with the episode id, and
answers with the generic message. A failing skill never stops the assistant. No stack
trace, exception text or library message ever reaches a `Response`.

## 7. Persona — Sazed

Source material: personality traits only, never copied passages. Sazed is a Terris
Keeper: a soft-spoken, kindly, very polite scholar and steward who stores knowledge in
copperminds. He specialises in religions, gently disagrees when it matters, and serves
by choice rather than servility. He is humble about leading, yet quietly effective.
He values people and their beliefs.

**Behaviour rules:**
- Formal, courteous register, but short for commands: "Pois não. Abrindo o Chrome."
- Addresses the user as "Mestre {nome}" (`user.name` in config).
- Masculine agreement in pt-BR ("Pronto.", "Obrigado.").
- Gentle disagreement before risky actions ("Posso fechar, mas há um arquivo não
  salvo. Deseja mesmo?").
- Learning has its own voice ("Guardarei isso em minha mente de cobre: 'zap' é o
  WhatsApp.").
- Humble when wrong ("Peço desculpas, parece que me enganei.").
- Lore references are light and rare. Humour is gentle and infrequent.

**Implementation:** `core/persona/` holds the single persona definition: traits, plus
message templates keyed by outcome/decision, with several variants per key. The variant
is chosen by an `rng` passed in, so rendering stays pure. Sub-project 6 generates the
SLM system prompt from this same definition.

## 8. Configuration

`config.toml`, validated by pydantic at startup. An invalid config stops startup with
a clear pt-BR message. Keys: `user.name`, `nlu.t_exec`, `nlu.t_confirm`, `nlu.g_min`,
`learning.t_conflict`, `learning.t_dup`, `dialogue.context_ttl_seconds`,
`model.embedder_path`, `data.dir`, `aliases` (user-defined, e.g. `zap = "WhatsApp"`).
Threshold values are tuned against the NLU fixture, not guessed. Initial values are
placeholders that the fixture run replaces.

## 9. Models and adapters

- **Embedder:** `intfloat/multilingual-e5-small`, exported to ONNX, run with
  `onnxruntime` on CPU. Expected: ~120 MB on disk, ~200 MB RAM, a few ms per sentence.
  These figures are measured during implementation. A setup script downloads it once
  into `models/` (gitignored), and after that everything is offline. The e5 query/passage
  prefixes are applied consistently.
- **Seed example embeddings** are computed at startup (a few hundred phrases, under
  1 s). There is no cache until measurement says otherwise.
- **App catalog:** resolves `.lnk` shortcuts in the user and all-users Start Menu
  folders into display name → target. Built at startup.
- **Launcher / closer:** start the target; close by matching running processes to the
  catalog entry (`psutil`).
- **Audio:** `pycaw` master volume (set, step, mute).
- **Logging:** a rotating local file, INFO by default. Debug mode logs the full
  ranking and scores per turn.

## 10. Testing

TDD throughout ([development rules](../../../.claude/rules/development.md)).

1. **Pure unit tests** (`core`, `nlu`, `persona`): every policy band, the context TTL
   with injected `now`, the extractors, and the learning rules (conflict, dedupe,
   forget). These use a deterministic fake embedder, and the fake itself is tested
   first (same text → same vector; different texts → different vectors).
2. **Skills with fake ports:** fakes record calls, and tests assert the fake's state
   (which process opened, which volume level), not only the response text.
3. **Coppermind persistence** (temp-file SQLite): learn, close and reopen, then assert
   the example persists and changes the decision. A transaction failing midway leaves
   no rows.
4. **NLU fixture** `tests/fixtures/nlu_cases.toml` (phrase → expected intent and
   slots), run against the real embedder under `@pytest.mark.model`. It asserts a
   minimum intent accuracy and a maximum false-execute rate. Executing when the
   system should have asked is the costliest error.
5. **Schema-driven persona test:** iterates over every `Outcome` and `Decision` type
   (not a hand list) and asserts that a pt-BR template exists and renders with
   `{nome}` filled.
6. **Windows adapters:** integration tests under `@pytest.mark.windows` (open and close
   Notepad, set the volume). Anything verified only by hand is named as such.

**Discrimination proofs:** for the confirm band, the destructive-action confirmation,
forget, and the learning transaction, break the implementation, watch the specific
test fail, revert, and record the output.

## 11. Documentation

A root `CLAUDE.md` covers the stack, commands, layout and current status, and fixes
the user-facing language as pt-BR. Local `CLAUDE.md` files in `src/sazed/core`,
`src/sazed/nlu` and `src/sazed/skills` cover their conventions, invariants and traps.

## 12. Open questions resolved during implementation

- Exact Python minor version (3.12 unless a wheel forces otherwise).
- Measured embedder RAM and latency on this machine.
- Initial threshold values, from the first fixture run.
