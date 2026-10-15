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
