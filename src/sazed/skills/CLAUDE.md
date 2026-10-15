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
