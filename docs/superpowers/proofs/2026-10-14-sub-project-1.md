# Discrimination proofs — sub-project 1

Each entry: the property, the mutation (a bug a person would write), the failing output, reverted.

## Architecture guard
Mutation: `import sazed.runtime` in `sazed/core/__init__.py`.
```
>       assert violations == []
E       AssertionError: assert ['__init__.py: sazed.runtime'] == []
FAILED tests/test_architecture.py::test_package_imports_only_what_it_may[core]
1 failed, 8 passed in 0.07s
```
Mutation: `datetime.now()` in `sazed/core/__init__.py`.
```
>       assert violations == []
E       AssertionError: assert ['__init__.py:4 .now'] == []
FAILED tests/test_architecture.py::test_pure_packages_do_not_touch_clock_env_or_io[core]
1 failed, 8 passed in 0.07s
```

## Confirm band
Mutation: delete the `top.score < th.t_exec` → `Confirm(LOW_SCORE)` branch in `core/policy.py`.
```
FAILED tests/core/test_policy.py::test_score_in_confirm_band_confirms_with_low_score_reason
FAILED tests/core/test_policy.py::test_score_exactly_at_t_confirm_still_confirms
2 failed, 11 passed in 0.09s
```

## Destructive-action confirmation
Mutation: `_close_needs_confirmation` returns `not app.exact` (drops the several-instances clause).
```
FAILED tests/skills/test_apps.py::test_close_with_several_instances_needs_confirmation
1 failed, 9 passed in 0.08s
```

## Learning transaction
Mutation: `self._conn.commit()` right after inserting each learned example in `SqliteCoppermind.learn`.
Test: `test_a_learning_step_that_fails_midway_leaves_no_rows` FAILED:
```
E       AssertionError: assert [StoredExampl...x02\x03\x04')] == []
E         
E         Left contains one more item: StoredExample(id=1, text='abre a� o chrome', intent_id='abrir_app', embedding=b'\x01\x02\x03\x04')
E         Use -v to get more diff
```
(A first attempt used a text anchor that the formatter had changed, so the mutation did not apply and the test passed. It was discarded and redone by line.)

## Forget
Mutation: `Assistant._forget` deletes from the store but skips removing items from the in-memory index/aliases.
```
FAILED tests/runtime/test_assistant_learning.py::test_forget_removes_the_latest_alias_from_store_and_memory
FAILED tests/runtime/test_assistant_learning.py::test_forget_removes_a_learned_example_from_the_index
FAILED tests/runtime/test_assistant_learning.py::test_forgetting_a_learned_alias_restores_the_configured_one
3 failed, 1 passed, 13 deselected in 0.09s
```
