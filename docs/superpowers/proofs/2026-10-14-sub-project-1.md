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

## Embedder batch independence
Finding: with the int8 model, a sentence vector depended on its batch-mates (max abs diff 0.011 next to another sentence of the *same* length — so not padding). Cause: dynamic int8 quantization scales activations over the whole batch. Fix: `OnnxEmbedder.embed` runs each text alone.
Mutation: batch all texts in one run again. `test_batch_mates_do_not_change_a_sentence_vector`:
```
FAILED tests/adapters/test_onnx_embedder.py::test_padding_does_not_change_a_sentence_vector
1 failed, 4 passed in 1.12s
```
Planned mutation `pooled = hidden.mean(axis=1)` (unmasked pooling) **did not discriminate**: one-row runs have no padding, so masking cannot matter. Reported as a finding, not bent into a failure; masked pooling stays for correctness if batching ever returns.
```
5 passed in 1.29s
```

## Volume level ("para N")
Bug from use: "abaixa o volume para 100" set 0% (100 was read as a step down). Fix: an `alvo`
slot for the number after "para/pra/pro/até"; volume up/down set that level when present.
Mutation: `if level:` instead of `if level is not None:` in `VolumeSkill.execute`.
```
>       assert audio.volume == 0
E       assert 40 == 0
FAILED tests/skills/test_volume.py::test_a_level_of_zero_is_kept - assert 40 ...
1 failed, 11 passed in 0.10s
```
Mutation: `alvo` extractor not wired in `runtime/extractors.py`.
`test_lowering_the_volume_to_a_level_above_the_current_one_sets_that_level`:
```
>       assert h.audio.volume == 100
E       assert 50 == 100
1 failed, 9 deselected in 0.09s
```
