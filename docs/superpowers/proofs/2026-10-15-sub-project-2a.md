# Discrimination proofs — sub-project 2a

Each section: the realistic mutation, and the test output that caught it. Every mutation was
reverted afterwards.

## Step of zero
Mutation: `step = int_slot(slots, "percent") or DEFAULT_STEP` in `levels.stepped` (the original
truthy bug). `test_an_explicit_step_of_zero_changes_nothing`:
```
E       AssertionError: assert VolumeChanged(percent=60) == VolumeChanged(percent=50)
FAILED tests/skills/test_volume.py::test_an_explicit_step_of_zero_changes_nothing
```

## Correction episode
Mutation: the misfire branch of `_correct` reacts with `self._react(Reaction.CORRECTED)` (the
latest episode) instead of the corrected command's episode.
```
E       AssertionError: assert <Reaction.NONE: 'none'> is <Reaction.CORRECTED: 'corrected'>
FAILED tests/runtime/test_assistant_learning.py::test_correction_marks_the_corrected_command_not_a_later_reply
```

## Learnable gate
Mutation: delete the `examples = [e for e in examples if ...learnable]` line in `Assistant._learn`.
```
FAILED tests/runtime/test_assistant_learning.py::test_confirming_an_unlearnable_intent_learns_nothing
FAILED tests/runtime/test_assistant_learning.py::test_correcting_towards_an_unlearnable_intent_learns_nothing
```

## Opt-in repeat
Mutation 1: drop `and self._specs[last.intent_id][1].repeatable` from the REPEAT branch.
```
FAILED tests/runtime/test_assistant_dialogue.py::test_repeat_does_not_reopen_an_app
```
`test_bare_more_with_nothing_to_repeat_is_never_ranked` passes under mutation 1: it guards a
different line. Mutation 2: delete the `NothingToRepeat` return, so a bare "mais" falls through
to ranking:
```
E       AssertionError: assert VolumeChanged(percent=60) == NothingToRepeat()
FAILED tests/runtime/test_assistant_dialogue.py::test_bare_more_with_nothing_to_repeat_is_never_ranked
```

## Review safeguards
Mutation: `verdict = Verdict.SAVE` instead of calling `judge_example` in `label_episode`.
```
FAILED tests/runtime/test_admin.py::test_labelling_a_known_phrase_again_is_reported_and_not_duplicated
FAILED tests/runtime/test_admin.py::test_labelling_a_phrase_that_belongs_to_another_intent_needs_force
```

## Site URL scheme
Mutation: remove the `http://`/`https://` check from `_http_url` in `runtime/config.py`.
```
FAILED tests/runtime/test_config.py::test_invalid_sites_and_engines_stop_startup_in_pt_br[[sites]\nnotas = "file:///C:/notas.txt"\n-sites.notas-http]
FAILED tests/runtime/test_config.py::test_invalid_sites_and_engines_stop_startup_in_pt_br[[sites]\nnotas = "C:/notas.exe"\n-sites.notas-http]
```

## Exact app name
Mutation: delete the exact-name block in `extract_app`.
```
E       AssertionError: assert Ambiguous(name='app', raw='whatsapp', candidates=('WhatsApp', 'WhatsApp Web')) == SlotValue(name='app', value='WhatsApp', raw='whatsapp', confidence=1.0, exact=True)
FAILED tests/nlu/test_slot_app.py::test_an_exact_name_wins_over_a_longer_name_containing_it
```

## Store app frame windows
Mutation: `windows_to_close` returns only windows owned by the app's own processes (the old
behaviour), ignoring ApplicationFrameHost frames that host it.
```
FAILED tests/adapters/test_windows_pure.py::test_a_frame_window_hosting_the_app_is_closed
FAILED tests/adapters/test_windows_integration.py::test_store_calculator_opens_and_closes
```
(The real-desktop run left Calculator open; it was closed afterwards with the fixed code.)

## Search encoding
Mutation: `search_url` replaces only spaces (`query.replace(" ", "+")`) instead of `quote_plus`.
```
FAILED tests/skills/test_web.py::test_search_url_encodes_the_whole_query[p\xe3o & caf\xe9-https://x/?q=p%C3%A3o+%26+caf%C3%A9]
FAILED tests/skills/test_web.py::test_search_url_encodes_the_whole_query[c# #1-https://x/?q=c%23+%231]
FAILED tests/skills/test_web.py::test_search_url_encodes_the_whole_query[a/b?c=d-https://x/?q=a%2Fb%3Fc%3Dd]
3 failed, 3 passed in 0.22s
```

## Bare search answer
Mutation: `extract_query` returns `None` when no trigger verb is found.
```
FAILED tests/runtime/test_assistant_dialogue.py::test_search_without_a_query_asks_and_takes_a_bare_answer
1 failed, 24 deselected in 0.10s
```

## URI allowlist
Mutation: `is_allowed_uri` returns `True`.
```
FAILED tests/adapters/test_windows_pure.py::test_anything_else_is_refused[C:\\Windows\\System32\\cmd.exe]
FAILED tests/adapters/test_windows_pure.py::test_anything_else_is_refused[file:///C:/x.bat]
FAILED tests/adapters/test_windows_pure.py::test_anything_else_is_refused[calc]
FAILED tests/adapters/test_windows_pure.py::test_anything_else_is_refused[javascript:alert(1)]
4 failed, 23 deselected in 0.12s
```

## No media session
Mutation: `midia_proxima` ignores the result of `next()` and always reports `MediaNext()`.
```
FAILED tests/skills/test_media.py::test_without_a_session_sazed_says_so[midia_proxima]
1 failed, 8 passed in 0.24s
```

## Power always confirms
Mutation: `_power` drops `requires_confirmation=always`.
```
FAILED tests/runtime/test_power_safety.py::test_a_certain_power_command_still_confirms[pc_desligar]
FAILED tests/runtime/test_power_safety.py::test_a_certain_power_command_still_confirms[pc_reiniciar]
FAILED tests/runtime/test_power_safety.py::test_a_certain_power_command_still_confirms[pc_sair_conta]
FAILED tests/runtime/test_power_safety.py::test_a_certain_power_command_still_confirms[pc_suspender]
FAILED tests/runtime/test_power_safety.py::test_a_correction_towards_a_power_command_confirms_and_learns_nothing[pc_desligar]
FAILED tests/runtime/test_power_safety.py::test_a_correction_towards_a_power_command_confirms_and_learns_nothing[pc_reiniciar]
FAILED tests/runtime/test_power_safety.py::test_a_correction_towards_a_power_command_confirms_and_learns_nothing[pc_sair_conta]
FAILED tests/runtime/test_power_safety.py::test_a_correction_towards_a_power_command_confirms_and_learns_nothing[pc_suspender]
8 failed, 5 passed in 0.13s
```

## Power never learned
Mutation 1: `_power` drops `learnable=False`. The derived case list becomes empty, so the
parametrised learning tests are skipped; the guard test catches it:
```
FAILED tests/runtime/test_power_safety.py::test_there_are_power_intents_to_check
1 failed, 3 skipped in 0.10s
```
This is a finding about derived parametrisation, and is why the guard exists. To prove the
learning tests themselves, mutation 2 keeps the flag and deletes the gate in `Assistant._learn`:
```
FAILED tests/runtime/test_power_safety.py::test_confirming_a_low_score_power_command_learns_nothing[pc_desligar]
FAILED tests/runtime/test_power_safety.py::test_confirming_a_low_score_power_command_learns_nothing[pc_reiniciar]
FAILED tests/runtime/test_power_safety.py::test_confirming_a_low_score_power_command_learns_nothing[pc_sair_conta]
FAILED tests/runtime/test_power_safety.py::test_confirming_a_low_score_power_command_learns_nothing[pc_suspender]
FAILED tests/runtime/test_power_safety.py::test_a_correction_towards_a_power_command_confirms_and_learns_nothing[pc_desligar]
FAILED tests/runtime/test_power_safety.py::test_a_correction_towards_a_power_command_confirms_and_learns_nothing[pc_reiniciar]
FAILED tests/runtime/test_power_safety.py::test_a_correction_towards_a_power_command_confirms_and_learns_nothing[pc_sair_conta]
FAILED tests/runtime/test_power_safety.py::test_a_correction_towards_a_power_command_confirms_and_learns_nothing[pc_suspender]
8 failed, 5 passed in 0.13s
```

## Screenshot names
Mutation 1: `ScreenSkill` passes the fixed name `"Captura.png"` instead of `screenshot_name(ctx.now)`.
```
FAILED tests/skills/test_screen.py::test_screenshot_reports_the_name_actually_saved
1 failed, 2 passed in 0.10s
```
Mutation 2: `unique_name` returns the name unchanged (overwrites).
```
FAILED tests/adapters/test_windows_pure.py::test_unique_name_never_overwrites
1 failed, 30 deselected in 0.12s
```

## Brightness refused
Mutation: ignore the result of `set()` and always report success.
```
FAILED tests/skills/test_brightness.py::test_a_refused_set_is_unsupported - A...
1 failed, 6 passed in 0.12s
```

## WMI brightness call (found on the real desktop)
The plan's dynamic call `monitor.WmiSetBrightness(0, n)` raised "Parâmetro inválido";
`test_brightness_reads_and_rewrites_the_same_level` (`-m windows`) FAILED with `assert False`.
Fix: named in-parameters through `ExecMethod_`; the same test passes.

## pt-BR numbers
Mutation: `pt_number` returns `f"{x:,.{places}f}"` (English separators).
```
FAILED tests/skills/test_status.py::test_disks - AssertionError: assert DiskS...
7 failed, 2 passed in 0.12s
```

## Every skill wired
Mutation: remove `SettingsSkill(ports.opener)` from `build_skills`.
```
FAILED tests/runtime/test_skills.py::test_every_skill_is_built_once - Asserti...
1 failed, 4 passed in 0.10s
```

## Fixture never copies a seed
Mutation: rename the case "desliga o spotify aí" back to the `fechar_app` seed "desliga o spotify".
```
E       AssertionError: assert ['desliga o spotify'] == []
E         
```

## Final review fixes (each test watched failing before the fix)
- `test_power_commands_never_force_apps_closed` FAILED on `["shutdown", "/s", "/t", "5"]`
  (`/t` above 0 implies `/f` on Windows); passes with `/t 0`.
- `tests/nlu/test_ranking_pairs.py` (real model) FAILED for "fecha o gmail aí", "fecha o github",
  "fecha o youtube pra mim" (top `abrir_app`) and "desmuta o computador" (top `pc_desligar`);
  all pass after the close-site and "o pc" mute seeds.

## Store app close race (found after merging into main)
`test_store_calculator_opens_and_closes` failed every time inside the `-m windows` suite (after
the Character Map test): right after launch Calculator's own top-level
`Windows.UI.Core.CoreWindow` was the only target, it ignores WM_CLOSE, and the app stayed open.
Fix: never target a CoreWindow; wait up to 2 s for the ApplicationFrameHost frame. Mutation:
drop the CoreWindow exclusion from `windows_to_close`.
```
FAILED tests/adapters/test_windows_pure.py::test_a_store_apps_own_core_window_is_never_the_close_target
```

## Learned phrases keep the wording, not the app (found by hand after 2a)
Before the fix, with the real model (`tests/runtime/test_learning_with_model.py`, the code in
`runtime/` reverted to store the raw phrase):
```
>       assert top(app, "fecha o whatsapp") == "fechar_app"
E       AssertionError: assert 'abrir_app' == 'fechar_app'
>       assert top(app, "fecha o spotify pra mim") == "fechar_app"
E       AssertionError: assert 'abrir_app' == 'fechar_app'
2 failed
```
After: 3 passed. Measured with the real model after learning "bota o spotify pra rodar"
(stored as "bota o programa pra rodar"): "bota o discord pra rodar" abrir 0.915 / fechar 0.909
before, 0.958 / 0.909 after; "fecha o spotify" unchanged (fechar 0.960).
Mutations on `mask_app`: drop the alias keys →
`FAILED tests/nlu/test_slot_app.py::test_an_alias_is_masked`. Drop the command-word guard in
`is_name` → the first test set still passed (a finding: "Abrir Arquivo" was covered by the set
subtraction); added `test_a_verb_close_to_a_name_word_is_kept`, which then failed with
`assert 'programa o programa' == 'roda o programa'`.
