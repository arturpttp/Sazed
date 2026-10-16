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
- `repeatable` is opt-in: level steps, track skips, and minimising/snapping/moving a window
  set it. "de novo" after anything else answers `NothingToRepeat` (opening a second Chrome
  was a real bug).
- `learnable=False` is enforced in one place, `Assistant._learn`. Power intents use it so a
  learned phrase can never weaken their confirmation.
- Power intents (`POWER_INTENTS`) use `requires_confirmation=always` and `learnable=False`;
  `tests/runtime/test_power_safety.py` derives its cases from the specs. The Windows adapter
  delays each action so the reply prints first, with `/t 0`: a shutdown.exe countdown implies
  `/f` and kills apps without asking to save. No test may call the real adapter.
- Window commands without an app act on the frontmost user window, which the adapter
  guarantees is never Sazed's console. `janela_focar` on an app with no window answers
  `WindowNotFound(offer_open=True)`; the runtime turns that into an "abrir?" confirmation that
  must not be learned (the phrase meant focus).
- `skills/pc/windows.py` keeps the geometry pure (`half`, `move_between`, `target_monitor`);
  the window choice needs processes, so it lives in `adapters/windows/windows.py`.

- `skills/pc/files.py` builds the Windows Search SQL itself: every word goes through
  `escape_sql_like` and every path through quote-doubling. Never format a user's words into
  the SQL any other way. A hit whose type is not in `OPENABLE_EXTENSIONS` is revealed, never opened.
- Restore targets a minimised window first, then a maximised one: a minimised window is at the
  bottom of the z-order, so "the front window" would be the wrong one.

- "programa" is the learning placeholder for app names: only `abrir_app`/`fechar_app` seeds
  may use it (tests/skills/test_specs.py). Window seeds that said "programa" made every learned
  open phrase "conflict" with them. Window seeds also avoid the apps the open/close seeds name
  (Spotify, Discord): e5 weighs the object, and "desminimiza o discord" pulled "desliga o discord".

## Not here
Text matching (→ `nlu`), Windows APIs (→ `adapters/windows`).
