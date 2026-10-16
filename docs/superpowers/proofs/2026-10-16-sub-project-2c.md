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
