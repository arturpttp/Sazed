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
- `COMMAND_WORDS` are removed from every app query, and aliases match only the whole query:
  a missing verb ("bota") makes the alias miss ("bota calculadora"). Never add a word that is
  also an app-name word: "poe" (stripped "põe") would make "abre o poe" name no app.
- Window commands share the `app` slot, so `WINDOW_WORDS` (their verbs and "janela",
  "esquerda", "monitor"…) are command words too: without them "minimiza essa janela" named an
  app "essa janela". Checked against the real catalog: "com" stays out ("Ação com um clique").
- `extract_folder` also finds a folder name or synonym as a run of words inside a longer phrase
  ("o último print que eu tirei").
- `mask_app` (used before learning) must keep the verb: command words are never masked, even
  when one is a fuzzy match for a word of the app name ("roda" vs "Rodas").
- Folder and file names are masked before learning with `mask_words` (slots `pasta`,
  `arquivo`): the span from the first to the last named word becomes one placeholder, so the
  inner fillers of a name ("gastos de outubro") go too.
- `arquivo` is "whatever is left" after verbs, fillers and type words: add a new filler to
  `files._FILLERS`, or it becomes part of every file name ("agora" was one).
- `IntentMatcher.add_examples` embeds in one batch; adding seeds one at a time is ~N× slower with the real model.

## Not here
The ONNX model (→ `adapters/onnx`), app catalog I/O (→ `adapters/windows`), deciding what
to do with a match (→ `core.policy`).
