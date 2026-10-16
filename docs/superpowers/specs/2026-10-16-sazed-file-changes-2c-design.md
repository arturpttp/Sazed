# Sazed — Sub-project 2c: moving, copying, renaming, deleting files

Date: 2026-10-16
Status: Draft, awaiting review.
Builds on: sub-projects [1](./2026-10-14-sazed-core-design.md), [2a](./2026-10-15-sazed-pc-skills-2a-design.md)
and [2b](./2026-10-16-sazed-pc-skills-2b-design.md), all merged on `main`. Everything there
still holds unless this document says otherwise; 2b's file search, folder names, allow-list and
choice list are reused.

## 1. Context and intent

**What the user asked for** (brainstorm, 2026-10-16):
- Operations: **move, copy, rename, delete (to the Recycle Bin), create a folder**.
- **Always confirm**, showing exactly what will happen; never learned as a shortcut.
- **Undo the last change** by voice ("desfaz isso").
- Allowed area: **the user's own folders only** (the user profile and `[folders]` from config).
- Name clash at the destination: **keep both** ("relatório (2).docx"), never overwrite.
- **Folders too**, with counts in the confirmation; the known folders themselves are never
  moved, renamed or deleted.
- Approach **A**: standard Python file calls + the Windows Recycle Bin, a change log in the
  coppermind.

**Assumption, not stated by the user:** success means doing the everyday file chores by typed
pt-BR without ever losing a file: every change is visible before it happens and reversible after.

### 1.1 Success criteria

1. In the terminal, pt-BR phrases move, copy, rename and delete files and folders and create
   folders inside the allowed area, each after a confirmation that states the exact effect.
2. Nothing on disk changes without "sim" to a confirmation of the exact plan — at any score,
   after any learning (a safety test derived from the specs, like power actions).
3. Nothing is ever overwritten or permanently deleted; "desfaz isso" reverts the last change
   while the files are as Sazed left them.
4. No path outside the allowed area, and no protected folder, is ever changed.
5. NLU fixture keeps accuracy ≥ 0.90 and false-execute 0.000.

### 1.2 Out of scope

Bulk operations by pattern ("apaga todos os pdf"), compressing/extracting, changing a file's
extension on purpose, permanent delete, undo history beyond the last open change (the log keeps
it; only the last is undoable), file contents, cloud folders' online-only state handling beyond
what the file calls do, voice.

## 2. Intents

All five intents: `learnable=False`, `repeatable=False`, `confirms_itself=True` (§4).

| Intent | Example phrases | Slots |
|---|---|---|
| `arquivo_mover` | "move o relatório pra pasta documentos", "manda o último download pra área de trabalho" | item (req.), destino (req.) |
| `arquivo_copiar` | "copia a planilha de gastos pra pasta projetos" | item (req.), destino (req.) |
| `arquivo_renomear` | "renomeia o arquivo contrato pra contrato assinado", "muda o nome da pasta viagem pra viagem 2025" | item (req.), novo_nome (req.) |
| `arquivo_apagar` | "apaga o arquivo rascunho", "joga o último print no lixo", "apaga a pasta temporários" | item (req.) |
| `pasta_criar` | "cria uma pasta chamada viagem na área de trabalho" | novo_nome (req.), destino (opt., default Área de Trabalho) |

Seeds follow the rules: opposing verbs share objects (move/copy, delete/open, rename/create);
no seed uses the learning placeholder "programa"; ≥ 8 per intent.

**Undo** is a control phrase (`nlu/control.py`), not an intent: "desfaz isso", "desfaz",
"desfazer", "volta atrás", "desfaça isso". It is recognised before ranking, like "esquece isso".

## 3. Slots

| Slot | Reads | Value |
|---|---|---|
| item | the words between the verb and the destination marker | an `ItemRef`: `latest` of a folder ("o último download/print"), a folder by name ("a pasta X"), or a file by name (+ `tipo` words, as 2b) |
| destino | after the last "pra/para/pro/na/no/em" (+ optional "pasta"/"a pasta") | a known/configured folder name, or a folder name to find |
| novo_nome | after "pra/para/como/chamada/chamado" (rename, create) | the name as typed (accents and case kept, from the original text, not the normalised one) |

The split is pure and tested on every seed shape. Rename keeps the extension: "contrato
assinado" for `contrato.pdf` → `contrato assinado.pdf`; a new name that already ends in the same
extension is not doubled. Folder names found by search use the index (`System.Kind = 'folder'`)
within the allowed area.

## 4. Plan, confirm, apply

1. **Resolve** the item (and destination). Several files → the 2b numbered list of the 5 newest;
   the pick resumes resolution.
2. **Plan** (pure, `plan_change`): `ChangePlan(kind, source, target, final_name, is_dir, count,
   size, renamed_for_clash)`. All checks of §5 run here, before any confirmation. A failure is an
   outcome (§6), never a plan.
3. The skill returns **`FileChangeProposed(plan)`**; the runtime sets a pending confirmation
   whose text is the plan's description, e.g. "Mover relatório.docx de Downloads para
   Documentos?", "Apagar a pasta viagem (128 arquivos, 2,3 GB) para a Lixeira?", "Já existe
   relatório.docx lá; vou salvar como relatório (2).docx. Confirma?".
4. **"sim" → `apply(plan)`**: the plan is re-checked against the disk first (source still exists
   with the same size and modification time; target name still free; §5 rules still hold). Any
   difference → `PlanChanged` ("O arquivo mudou desde que perguntei; não fiz nada.") and nothing
   happens.
5. After applying, one row goes to the change log (§7).

`confirms_itself=True` on an `IntentSpec`: the policy's low-score `Confirm` becomes `Execute`
for these intents (the plan is the confirmation; never two questions). Below `t_confirm` they are
still `NotUnderstood`. `learnable=False` keeps every 2c phrase out of learning, including the
dashboard and `sazed revisar` (already enforced by `learn_example`).

## 5. Safety rules (pure, `skills/pc/fileops.py`)

- **Allowed roots:** the user profile and every `[folders]` path. A path is allowed only if its
  fully resolved form (`os.path.realpath`: links, junctions and `..` followed; case-insensitive
  compare) is strictly inside a root.
- **Protected (never source, never moved/renamed/deleted):** each allowed root itself, each known
  folder itself (Downloads, Documentos, Área de Trabalho, Imagens, Vídeos, Músicas, Capturas de
  Tela), drive roots, anything under `AppData`, Sazed's data dir and the Sazed project folder.
  Known folders remain valid **destinations**.
- A folder is never moved or copied into itself or a subfolder of itself.
- **Names:** not empty after trimming; none of `\ / : * ? " < > |` or control characters; not a
  reserved device name (CON, PRN, AUX, NUL, COM1–9, LPT1–9, with any extension); no trailing dot
  or space; total path length checked against the adapter's limit.
- **Clashes:** move/copy into a folder holding the same name → `free_name` ("x (2).ext", "(3)"…);
  rename onto an existing name → refused (`NameTaken`), never numbered (the user asked for that
  name); create an existing folder → `NameTaken`.
- **Delete** only where the Recycle Bin is available (`FileChanger.can_recycle(path)`); otherwise
  refused, never a permanent delete.
- The test for the allowed area is driven from one list of protected kinds, so a new kind is
  covered automatically.

## 6. Failures (pt-BR, all tested)

| Situation | Outcome |
|---|---|
| Item not found | `FileNotFound` (2b) / `FolderNotFound` |
| Outside the area or protected | `Protected(name)` — "Por segurança, não mexo em {name}, Mestre Artur." |
| Destination folder missing | `FolderNotFound(name)` — never created implicitly |
| Folder into itself | `IntoItself(name)` |
| Bad new name | `BadName(name, reason)` — "Esse nome não serve para arquivos: {reason}." |
| Rename/create onto an existing name | `NameTaken(name)` |
| File changed between question and "sim" | `PlanChanged()` |
| Locked / permission denied | `FileBusy(name)` — "Não consegui {acao} {name}: ele está aberto em outro programa ou sem permissão." A cross-drive move that fails removes its partial copy and never deletes the original. |
| No Recycle Bin on that drive | `NoRecycleBin(name)` |
| Undo: nothing open | `NothingToUndo()` |
| Undo: changed since | `UndoStale(name)` — "{name} mudou depois; não vou desfazer." |
| Undo: emptied from the Recycle Bin | `NotInRecycleBin(name)` (the log row is closed) |

Unexpected adapter exceptions become `ActionFailed` (existing rule) and are logged.

## 7. Change log and undo

Coppermind **migration 3**: table `file_changes(id, kind, source, target, is_dir, size, mtime,
recycle_ref, at, undone_at)`; `PRAGMA user_version` 3. One row per applied change, written after
the change succeeds. `size`/`mtime` describe the item **after** the change (for undo checks).

"desfaz isso" → the latest row with `undone_at IS NULL` → an undo plan (pure,
`plan_undo(row, now_state)`):
- move → move back (to the original name; if taken, refused with `UndoStale`);
- rename → rename back;
- copy / new folder → the copy/folder **to the Recycle Bin**;
- delete → restore from the Recycle Bin (`FileChanger.restore(recycle_ref)`).
The undo plan is confirmed like any change ("Devolver relatório.docx de Documentos para
Downloads?"); on "sim" it is re-checked, applied, and the row gets `undone_at`. Undo itself is
not logged as a new undoable change (no redo). The dashboard reader learns the table (read-only
list) in this sub-project only as far as its schema tests require.

## 8. Ports and adapters

`FileChanger` (`skills/pc/fileops.py`), adapter `WindowsFileChanger`
(`adapters/windows/fileops.py`):

| Method | Adapter |
|---|---|
| `state(path) -> ItemState or None` (exists, is_dir, size, mtime, count) | `os.stat`; for folders a walk summing files (bounded: stops counting after 100 000 entries and says "mais de 100 000") |
| `move(src, dst)` | same volume: `os.rename`; other volume: copy (`shutil.copy2`/`copytree`), verify the size, and only then remove the original; on any failure remove the partial copy and leave the original |
| `copy(src, dst)` | `shutil.copy2` / `shutil.copytree` |
| `rename(src, new_name)` | `os.rename` within the folder |
| `make_folder(path)` | `os.mkdir` (not `makedirs`) |
| `can_recycle(path)` | fixed local drive (`GetDriveType == DRIVE_FIXED`) |
| `recycle(path) -> RecycleRef` | `SHFileOperationW(FO_DELETE, FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI)`; the ref = original path + deletion time |
| `restore(ref) -> bool` | Shell `Namespace(10)` (Recycle Bin): the item whose original location and name match and whose deletion time is closest to `ref`; verb "undelete" |
| `limits()` | max path length (260 unless long paths are enabled) |

Everything else is pure. `free_name` moves from `adapters/windows/screen.py` to a pure home
shared by both.

## 9. Testing

- **Pure:** allowed area (`..`, junction/symlink pointing outside via a fake realpath, drive
  root, each known folder, AppData, case and trailing separator); names (reserved, invalid
  characters, trailing dot/space, extension kept, extension not doubled); `free_name`; every
  plan kind incl. into-itself and clashes; `plan_undo` for every kind and every stale case; the
  slot split on every seed shape and on the fixture phrases.
- **Skill/runtime with fakes:** every row of §6 with its pt-BR text; the plan is the only
  confirmation; "sim" applies exactly the confirmed plan; a change between question and "sim" does
  nothing; undo confirmed then applied; nothing from 2c learned (conversation and `learn_example`);
  the change log re-read from SQLite after each apply/undo.
- **Safety, derived from the specs:** for every intent with `confirms_itself`, at scores from
  `t_confirm` to 1.0 and after an attempt to learn its phrase, the fake `FileChanger` records no
  call before "sim".
- **Fixture:** ~40 cases, incl. near-ties move/copy, delete/open file, rename/create, "desfaz"
  vs other phrases, and `none` cases ("apaguei a luz", "mudei de casa"). Accuracy ≥ 0.90,
  false-execute 0.000.
- **`-m windows`:** inside a temporary folder the test creates under the user profile (and
  removes): move, copy, rename, create, each undone; delete to the real Recycle Bin and restore
  with undo; a file held open (`open(..., 'r+')` with a share lock via `msvcrt.locking`) refuses
  to move; the cross-drive path with a fake second volume is covered by fakes only.
- **By hand at the end:** the same flow through the real `Assistant`, on files Sazed's test
  created, never the user's.
- **Migration:** a database at version 2 upgrades to 3 with its data intact; the dashboard
  reader still opens it read-only.

**Unverified unless the user helps:** a real cross-drive move (needs a `[folders]` entry on
another drive).

## 10. Documentation

Local `CLAUDE.md` updated in the same commits: `skills` (confirms_itself, never learned, plan
re-check), `adapters` (Recycle Bin, cross-drive move, migration 3), `nlu` (item/destination
split, undo phrases), `runtime` (pending plan, undo flow). Proofs in
`docs/superpowers/proofs/2026-10-16-sub-project-2c.md`.
