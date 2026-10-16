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
- Volume up/down carry two number slots: `percent` is a step ("aumenta em 20") and `alvo` is
  the level to end at ("abaixa para 100" means 100%, even above the current volume). `alvo`
  wins; check it with `is not None`, since 0 is a real level.
- `repeatable` is opt-in: only level steps and track skips set it. "de novo" after anything
  else answers `NothingToRepeat` (opening a second Chrome was a real bug).
- `learnable=False` is enforced in one place, `Assistant._learn`. Power intents use it so a
  learned phrase can never weaken their confirmation.
- Power intents (`POWER_INTENTS`) use `requires_confirmation=always` and `learnable=False`;
  `tests/runtime/test_power_safety.py` derives its cases from the specs. The Windows adapter
  delays each action so the reply prints first, with `/t 0`: a shutdown.exe countdown implies
  `/f` and kills apps without asking to save. No test may call the real adapter.

## Not here
Text matching (→ `nlu`), Windows APIs (→ `adapters/windows`).
