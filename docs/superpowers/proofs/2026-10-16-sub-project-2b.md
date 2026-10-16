# Sub-project 2b — discrimination proofs

Each section: the mutation a person could plausibly write, and the failing output.

## Task 1: "vai pro X" offers to open only on focus
Mutation: drop the `WindowNotFound.offer_open` branch from `template_key`.
```
E       AssertionError: assert 'Spotify não ...Mestre Artur.' == 'Spotify não .... Devo abrir?'
E         - Spotify não está aberto, Mestre Artur. Devo abrir?
```

## Task 2: moving between monitors uses the source monitor's offset
Mutation: `round(v * dst.width / src.width)` (forgets `- src.left`).
```
FAILED tests/skills/test_window_geometry.py::test_moving_back_returns_to_the_same_place
```

## Task 3: folder and file names are masked before learning
Mutation: `_NAMED_SLOTS = {}` in `runtime/assistant.py`.
```
FAILED tests/runtime/test_assistant_learning.py::test_a_learned_folder_phrase_keeps_the_wording_not_the_folder
FAILED tests/runtime/test_assistant_learning.py::test_a_learned_file_phrase_keeps_the_wording_not_the_file
```
Mutation: always insert the placeholder (no collapse after the same literal word).
```
FAILED tests/nlu/test_slot_mask.py::test_a_placeholder_after_the_same_literal_word_collapses
```

## Task 4: Sazed's console is never a window target
Mutation: exclude only windows whose own pid is Sazed's (drop the hosted-child check — Windows
Terminal draws the console inside its own process's window).
```
FAILED tests/adapters/test_window_choice.py::test_a_frame_hosting_sazeds_console_is_excluded
```

## Task 5: a maximised window stays maximised after moving to another monitor
Mutation: drop the final `maximize` after `place`.
```
FAILED tests/skills/test_windows_skill.py::test_moving_a_maximised_window_keeps_it_maximised
```
