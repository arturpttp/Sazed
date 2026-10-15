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
