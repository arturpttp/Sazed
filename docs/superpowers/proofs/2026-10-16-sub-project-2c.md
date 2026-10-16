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

## Task 10: fixture with the real model (qint8), thresholds unchanged
| | cases | accuracy | false-execute | executed | asked |
|---|---|---|---|---|---|
| main after 2b | 198 | 0.923 | 0.000 | 0.542 | 0.458 |
| 2c + 33 new cases, first seeds | 231 | 0.897 | 0.000 | 0.477 | 0.523 |
| + seeds sharing objects (delete/open, rename/move, copy/move) | 231 | 0.903 | 0.000 | 0.472 | 0.528 |
| "renomeia a pasta fotos pra fotos antigas" replaced (it pulled "abre a pasta fotos antigas" to rename at 0.965) | 231 | 0.918 | 0.000 | 0.477 | 0.523 |

A self-confirming intent's Execute counts as *asked* in the evaluation (it is a proposal):
`test_a_file_change_proposal_counts_as_asked_never_as_a_false_execute` failed first.
Remaining 2c misrankings all ask: "apaga o arquivo orçamento" (abrir_arquivo 0.949 vs 0.946,
gap under g_min → "abrir o arquivo orçamento?"), "manda o último download pro lixo" (mover →
"Para qual pasta?"), "transfere a pasta fotos antigas pra documentos" (copiar 0.938 vs 0.937 →
the plan says "Copiar…", the user can say no).

## Task 11: by hand on the real disk, index and Recycle Bin
Through the real `Assistant` (temp data dir) on a file the script created under Documents:
move → "Mover … de sazed-teste-… para Documentos. Confirma?" → sim → moved → "desfaz isso" →
"Devolver … de Documentos para …" → sim → back; rename (case kept: "Orçamento Final.txt") and
back; copy and its undo (the copy to the Recycle Bin); new folder and its undo; delete to the
real Recycle Bin and "desfaz" → restored. Log: five changes, all undone. Nothing learned.

Found only on the real machine, each fixed with a test that failed first:
- "apaga a pasta downloads" listed five other folders named "downloads" (game mod packs):
  a known or configured folder named as the item is now recognised first and refused —
  `test_a_known_folder_named_as_the_item_is_refused_by_its_pt_br_name`.
- "renomeia a pasta documentos pra docs" said the folder did not exist (it is "Documents" on
  disk): now "Por segurança, não mexo em Documentos" (same test).
- "pra pasta windows" offered folders under AppData\Local\Packages: search results are filtered
  through the area rules before being offered — `test_search_results_outside_the_area_are_never_offered`.
- The index counts a `.zip` as a folder: `folders()` keeps real directories only —
  `test_folder_search_keeps_real_folders_only`.
- "apaga a pasta downloads" ranked opening the folder: delete seeds now share the folder objects
  ("apaga a pasta downloads"); fixture 233 cases, accuracy 0.919, false-execute 0.000.
Startup 2.91–2.95 s (2b: 2.5 s; 484 seed examples), RSS +430 MB unchanged.

## Final review fixes (each test watched failing before the fix)
- **C1 — a "delete" could be a silent permanent delete** (an item bigger than the bin's quota,
  the bin turned off, or a subst drive: under FOF_NOCONFIRMATION Windows destroys it without
  asking). `can_recycle` now receives the item and checks the drive's real bin settings
  (`BitBucket\Volume\{GUID}`: MaxCapacity, NukeOnDelete; this machine: 49 703 MB on C:), refuses
  subst drives, a folder whose count was capped, and unknown settings; `FOF_WANTNUKEWARNING` is
  set as a second net. `test_anything_the_bin_might_not_take_is_refused` (4 cases) failed first;
  mutation "ignore the capped count" → `FAILED …[10-100000-53687091200-False]`.
- **I1 — a pick from one list was searched as words after a second list replaced it** (the
  wrong file proposed). Choice lists are kept per slot; an unknown item encoding raises instead
  of searching. `test_picking_a_file_then_a_folder_keeps_both_choices` failed first; mutation
  "one shared list" → fails again.
- **I2 — a cross-drive move whose last step failed said "nothing happened"** while a copy existed
  and part of the original was gone (rmtree). The original now goes to the Recycle Bin after the
  copy is verified; if that fails, `MovedAsCopy` → logged as a copy, answered `CopiedNotMoved`.
  Mutation: no conversion → `FAILED …test_when_the_original_cannot_be_removed_the_copy_stays_and_says_so`.
- **I3 — the rollback could remove a folder it had not created.** Anything already at the
  destination is refused before copying; only this call's partial copy is removed. Mutation: no
  pre-check → `FAILED …test_something_already_at_the_destination_is_never_touched`.

## After the merge: a cross-drive move by hand (2026-10-16)
Only C: exists, so `S:` was a `subst` of `C:\sazed-drive-test`, configured as
`[folders] testedrive = "S:\alvo"`; a 36 000-byte file the script created in Documents.
- First run: "move o arquivo sazedcrossdrive pra pasta testedrive" → "Por segurança, não mexo em
  alvo". `check_destination` resolved the candidate through `realpath` (S:\alvo →
  C:\sazed-drive-test\alvo) but compared it with the area's folders unresolved, so a folder
  configured through a subst drive, junction or symlink never matched itself — and a protected
  tree named through a link did not protect what is really inside it. The area's roots, fixed
  folders and trees now go through `realpath` too.
  `test_a_folder_configured_through_a_subst_drive_is_a_destination_and_holds_sources` and
  `test_a_tree_named_through_a_link_still_protects_what_is_really_inside_it` failed first
  (`AssertionError: … isinstance(None, Protected)` for the file inside the linked tree).
- Second run: "Mover … de Documentos para alvo. Confirma?" → sim → "Pronto … está em alvo"; the
  copy's size equal (36000), the original in the real Recycle Bin (original location
  `C:\Users\Usuario\Documents`). "desfaz isso" → sim → copied back, and the copy on S: kept:
  "Copiei … mas não consegui tirar o original do lugar (pode estar aberto)" — a subst drive
  has no Recycle Bin, so `can_recycle` refuses it (C1) and nothing is deleted permanently.
  The "(pode estar aberto)" reason is misleading in that case (deferred minor).
