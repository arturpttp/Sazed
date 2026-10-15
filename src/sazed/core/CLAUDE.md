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
