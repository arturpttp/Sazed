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
