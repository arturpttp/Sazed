# Sub-project 2c — discrimination proofs

Each section: the mutation a person could plausibly write, and the failing output.

## Task 1: outcomes and templates
The new value tests failed before the types existed (2 failed, ImportError); the persona suite
then demands a template for every new outcome type automatically.

## Task 2: links and junctions are followed before the area check
Mutation: `_resolved` uses the path as written (no `realpath`).
```
FAILED tests/skills/test_fileops_rules.py::test_anything_else_is_protected[C:\Users\a\Documents\atalho\cmd.exe]
FAILED tests/skills/test_fileops_rules.py::test_anything_else_is_protected[C:\Users\a\Documents\fora\x.txt]
```
## Task 2: a dotless name is numbered "name (2)"
Mutation: treat ".gitignore" as stem "" + ext → `FAILED …test_free_name_numbers_files_folders_and_ignores_case`.
The old `unique_name` (screenshots) produced " (2)foo" for "foo"; screenshots now use `free_name`.

## Task 3: a folder never goes into itself
Mutation: drop the into-itself check in `plan_change`.
```
FAILED tests/skills/test_fileops_plans.py::test_a_folder_never_goes_into_itself[C:\Users\a\Downloads\viagem]
FAILED tests/skills/test_fileops_plans.py::test_a_folder_never_goes_into_itself[C:\Users\a\Downloads\viagem\fotos]
```
## Task 3: undoing a move checks the original name is still free
Found by `test_undo_refuses_when_the_original_name_is_taken_again` on the first implementation,
which ignored the item's own name at the origin even for a move (right only for a rename).

## Task 4: the destination starts at the last marker
Mutation: scan markers from the first. With the first test set it still passed (a finding: no
case had two markers). Added `test_the_destination_starts_at_the_last_marker`, which then failed:
```
FAILED …[move o relatório pra entregar pra pasta projetos-arquivo:relatório entregar]
FAILED …[copia a foto da praia no rio pra pasta imagens-arquivo:praia rio]
```
## Task 4: a new name comes from the original text
Mutation: `_extract` passes the normalised text to `novo_nome` →
`FAILED tests/runtime/test_assistant_basic.py::test_a_new_name_is_read_from_the_original_text`.

## Task 5: a self-confirming intent is never asked twice
Mutation: only the LOW_SCORE confirm is turned into Execute →
`FAILED tests/core/test_policy.py::test_an_intent_that_confirms_itself_is_not_asked_twice_for_a_small_gap`.

## Task 6: the plan is re-checked against the disk before anything happens
Mutation: `apply_pending` skips `_still_valid`.
```
FAILED tests/skills/test_fileops_skill.py::test_a_file_changed_after_the_question_is_left_alone
FAILED tests/skills/test_fileops_skill.py::test_a_file_removed_after_the_question_is_left_alone
FAILED tests/skills/test_fileops_skill.py::test_a_target_taken_after_the_question_is_left_alone
```
`FileSearch.folders` (new on 2b's port) checked on the real index: "documents" → 1 folder.

## Task 8: change log (migration 3)
The four tests failed before the table and methods existed (`AttributeError: … 'record'`). A
version-2 database built through the writer upgrades to 3 with its examples intact; rows are
re-read through a fresh connection. Two older tests pinned "version 2"; they now use
`len(MIGRATIONS)` so the next migration does not break them again.

## Task 7: nothing on disk changes before "sim" (derived from the specs)
Mutation: apply the plan as soon as it is proposed → `20 failed` in
`tests/runtime/test_fileops_safety.py` (every intent × every score).
Mutation: `learnable=True` on the 2c intents → the 5 `test_no_file_change_phrase_can_be_taught`
cases fail. Finding: `test_nothing_from_a_file_change_is_ever_learned` (conversation) still
passed under that mutation — in conversation the guarantee lives in the pending plan, which never
reaches `_learn`; `learnable=False` is what blocks the dashboard and `sazed revisar`.

## Task 9: Windows file changes
- A file held open is busy (Python opens without delete sharing, like Word). Mutation: never map
  OSError to `ChangeBusy` → `FAILED …test_a_file_open_in_another_program_is_busy`.
- A cross-drive move never loses the original. Mutation: always remove the source (`finally`)
  → `FAILED …test_a_failed_copy_removes_the_partial_copy_and_keeps_the_original`,
  `FAILED …test_a_copy_with_the_wrong_size_is_removed_and_the_original_kept`.
- Real Recycle Bin (`-m windows`): a file and a folder recycled and restored. A same-named file
  deleted twice: the first `restore` took whichever the bin listed first —
  `test_restore_brings_back_the_copy_this_change_deleted` failed 1 run in 2
  (`assert 'primeiro' == 'segundo'`); with the deletion time compared it passed 4 of 4.
