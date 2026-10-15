# sazed.runtime

Wires config, adapters, skills and the assistant together; the only place the clock is read.

## Conventions
- Every skill is built by `skills.build_skills(PcPorts, Config)`. Wiring, evaluation, scripts and
  the test harness all call it, so a new skill appears everywhere at once.
- `DryRunPorts` implements every port and never touches the machine; evaluation relies on it.
- `Assistant._learn` is the single gate for learned examples (`IntentSpec.learnable`), and the
  REPEAT control never falls through to ranking.

## Traps
- Sites are catalog entries (`CombinedCatalog`); an installed app with the same name wins.
- `DEFAULT_APP_ALIASES` are added only for apps present in the catalog; config aliases win.
- Turns can share a timestamp (tests use a manual clock): track "this turn ran a command" by
  `LastTurn` identity, never by comparing times.

## Not here
Skill logic (→ `skills`), OS access (→ `adapters`), the REPL and its pt-BR strings (→ `interfaces`).
