# sazed.nlu

Understanding text: normalisation, the embedder port, intent ranking, slot extraction and
dialogue-control phrases. Pure functions over already-loaded data; no OS access, no clock.

## Conventions
- `normalize()` keeps accents (the embedder benefits). Every *matching* step uses
  `strip_accents()` on both sides. Never compare a stripped string with an unstripped one.
- Extractors return `SlotValue | Ambiguous | Unmatched | None`. `None` means "nothing was
  named", and the policy asks for it. `Unmatched` means "named, but unknown", and the skill reports it.
- App matching score = max(token_set_ratio(query, name), best per-token ratio). 100 is
  "exact" (no confirmation needed to close). Thresholds: MIN_SCORE 80, SUGGEST_SCORE 60, MARGIN 3.

## Traps
- `um`/`uma` are articles, not the number one ("abaixa um pouco").
- "não é o X" is not a correction: without the comma it is a negation.
- A number right after "para/pra/pro/até" is also read as the `alvo` slot (a level, not a
  step). The `percent` extractor still reads it too: `volume_definir` seeds say "pra 70".
- Numbers outside 0–100 are `Unmatched` (never clamped): the skill answers `InvalidPercent`
  with the valid range. `Unmatched` counts as given, so the policy does not ask again.
- `IntentMatcher.add_examples` embeds in one batch; adding seeds one at a time is ~N× slower with the real model.

## Not here
The ONNX model (→ `adapters/onnx`), app catalog I/O (→ `adapters/windows`), deciding what
to do with a match (→ `core.policy`).
