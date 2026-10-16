# Sazed — Sub-project 2b: windows, folders and files

Date: 2026-10-16
Status: Draft, awaiting review.
Builds on: [sub-project 1](./2026-10-14-sazed-core-design.md) and
[sub-project 2a](./2026-10-15-sazed-pc-skills-2a-design.md), both merged on `main`. Everything
there still holds unless this document says otherwise.

## 1. Context and intent

**What the user asked for** (brainstorm, 2026-10-16):
- Window commands: minimise / maximise / restore, focus ("switch to"), show desktop and snap,
  move to another monitor — all four groups.
- File commands: open known folders, find and open a file, recent files, and
  move/rename/delete. Split, as the user chose: **2b (this spec)** has every window command and
  the read-only file commands; **2c** (its own brainstorm) changes files, with undo and safety
  rules of its own.
- File search uses the **Windows Search index** (no scan of our own, no fallback scan).
- Without an app name, a window command acts on **the last window used before Sazed's
  console**, not on the console.
- Several matching files: **list the 5 newest**, the user picks with "o primeiro" etc. One
  match opens directly.
- Windows access: **native APIs in-process** (approach A, as in 2a).
- The user has **two monitors**, one switched off at the time of the brainstorm: design and
  test for two.

**Assumption, not stated by the user:** success means doing, by typed pt-BR, the window and
file chores the user would otherwise reach for the mouse to do. Voice remains sub-project 4.

**Facts checked on 2026-10-16:** the `WSearch` service is running and an `ADODB` query on
`SYSTEMINDEX` through `Search.CollatorDSO` returns rows; one monitor was on.

### 1.1 Success criteria

1. In the terminal, pt-BR phrases minimise, maximise, restore, focus, snap and move windows of
   named apps or of the last-used window; show the desktop and bring windows back; open known
   and configured folders; find and open files by name (and type); open the newest download or
   screenshot; list today's downloads.
2. The NLU fixture, extended with the new intents, keeps accuracy ≥ 0.90 and false-execute at
   0.000 (it is 0.000 today; 2b must not be the first to execute a wrong command).
3. A file found by search that is itself a program is never run (§6).
4. No file content is ever read or recorded; the episode log keeps a file's name only.

### 1.2 Out of scope

Moving, renaming, copying, deleting files and creating folders (2c); searching file contents;
virtual desktops; window layouts with more than halves (quarters, thirds); per-window
transparency or always-on-top; closing a single window of a multi-window app (closing stays as
in 2a); voice.

## 2. Intents

All intents are `learnable`. "Repeatable" is opt-in (2a rule).

| Intent | Example phrases | Slots | Repeatable |
|---|---|---|---|
| `janela_minimizar` | "minimiza o chrome", "minimiza essa janela" | app (opt.) | yes |
| `janela_maximizar` | "maximiza o spotify", "deixa em tela cheia" | app (opt.) | no |
| `janela_restaurar` | "restaura o discord", "desmaximiza essa janela" | app (opt.) | no |
| `janela_focar` | "vai pro discord", "mostra o spotify", "troca pro chrome" | app (req.) | no |
| `janela_encaixar` | "joga o chrome pra esquerda", "encaixa na direita" | app (opt.), lado (req.) | yes |
| `janela_mover_monitor` | "manda o chrome pro outro monitor", "pro monitor 2" | app (opt.), monitor (opt., default "outro") | yes |
| `area_trabalho_mostrar` | "mostra a área de trabalho", "minimiza tudo" | — | no |
| `area_trabalho_voltar` | "volta as janelas", "restaura tudo" | — | no |
| `abrir_pasta` | "abre a pasta downloads", "abre meus documentos" | pasta (req.) | no |
| `abrir_arquivo` | "abre o arquivo relatório", "acha a planilha de gastos" | arquivo (req.), tipo (opt.) | no |
| `abrir_recente` | "abre o último download", "abre o último print" | pasta (opt.; default Downloads, "print"/"captura" → Screenshots) | no |
| `listar_recentes` | "quais arquivos baixei hoje", "o que eu baixei hoje" | — (Downloads, today) | no |

Seeds follow the existing rule: opposing intents share objects so the verb decides
(minimise/maximise/restore over the same apps; `janela_focar` "mostra o spotify" against
`abrir_app` "abre o spotify"; `abrir_pasta` "abre a pasta downloads" against `abrir_app`).

`janela_focar` on an app with no window answers "X não está aberto. Devo abrir?"; "sim" runs
`abrir_app` for that app (a pending confirmation for `abrir_app`, `learn_example=False`: the
phrase meant "focus", it must not be learned as "open").

## 3. Slots

| Slot | Extractor | Values |
|---|---|---|
| app | existing `extract_app` (optional for window intents) | catalog name |
| lado | new, pure | `esquerda`, `direita` ("pra esquerda", "no lado esquerdo", "à direita") |
| monitor | new, pure | `outro` or a number 1–9 ("monitor 2", "segundo monitor", "outra tela") |
| pasta | new, pure, fuzzy like apps | known folders (§5.2) plus `[folders]` names from config |
| arquivo | new, pure | the words left after verbs, fillers and the type word; `None` when empty |
| tipo | new, pure | `planilha`, `documento`, `pdf`, `apresentacao`, `foto`, `video`, `musica`, `texto` |

**Masking before learning** (the 2a learning fix, generalised): `Assistant.learnable_text`
masks every slot that names a thing — app → "programa" (existing), pasta → "pasta",
arquivo → "arquivo". Numbers are still not masked (deferred since 2a).

## 4. Choosing the window (pure)

Input: the windows from the adapter in front-to-back order, each with `hwnd`, `pid`,
`exe_path`, `class_name`, `title`, `visible`, `cloaked`, `tool_window`, `owner`, `state`
(normal/minimised/maximised), `rect`, `monitor`; and Sazed's own pids.

- **Candidates:** visible, not cloaked, not a tool window, unowned, non-empty title, not a
  `Windows.UI.Core.CoreWindow` (2a trap), not the shell (`Progman`, `WorkerW`,
  `Shell_TrayWnd`).
- **Sazed's console is never a target.** Own pids = Sazed's process and its ancestors
  (`conhost.exe`, `WindowsTerminal.exe`, `pwsh`/`powershell`/`cmd`, `uv`). A window owned by
  one of them is excluded. Trade-off accepted: another tab of the same Windows Terminal window
  is excluded too.
- **Named app:** the windows whose process the app's `entry_matcher` accepts, plus
  `ApplicationFrameHost` frames hosting the app (2a's Store rule). Frontmost wins.
- **No app named:** the frontmost candidate.
- None found: `WindowNotFound(app)` ("X não está aberto") or `NoWindow` ("Não há janela para
  isso, Mestre Artur.").

## 5. Ports and adapters

Ports live next to the skill that uses them; adapters in `adapters/windows`. Skills stay pure.

### 5.1 `WindowControl` (`skills/pc/windows.py`)

| Method | Adapter (pywin32/ctypes) |
|---|---|
| `windows() -> list[WindowInfo2b]` | `EnumWindows` (z-order), `DwmGetWindowAttribute(DWMWA_CLOAKED)`, `GetWindowPlacement`, `MonitorFromWindow` |
| `monitors() -> list[Monitor]` | `EnumDisplayMonitors` + `GetMonitorInfo` (work area, primary flag), ordered left-to-right then top-to-bottom; number = position + 1 |
| `minimize / maximize / restore(hwnd)` | `ShowWindow(SW_MINIMIZE / SW_MAXIMIZE / SW_RESTORE)` |
| `focus(hwnd) -> bool` | restore if minimised; `SetForegroundWindow`; on refusal, the documented workaround (`AllowSetForegroundWindow`/simulated Alt key), re-check; still refused → `FlashWindowEx` and return False |
| `place(hwnd, rect)` | restore if minimised or maximised, then `SetWindowPos`, compensating the invisible DWM frame (`DWMWA_EXTENDED_FRAME_BOUNDS`) |
| `show_desktop() / undo_show_desktop()` | `Shell.Application` COM `MinimizeAll` / `UndoMinimizeALL` |

Pure geometry (tested without Windows): `half(work_area, side) -> Rect`;
`move_between(rect, src_work_area, dst_work_area) -> Rect` keeps relative position and size,
clamped inside the destination (negative coordinates allowed: a monitor left of the primary);
`target_monitor(monitors, current, wanted)` — `outro` cycles to the next, a number picks it.

### 5.2 Files (`skills/pc/files.py`)

| Port | Method | Adapter |
|---|---|---|
| `KnownFolders` | `resolve(name) -> Path or None`, `names()` | `SHGetKnownFolderPath` for Downloads, Documents, Desktop, Pictures, Videos, Music, and `Pictures\Screenshots`; plus `[folders]` from config |
| `FileSearch` | `search(query, kinds, limit) -> SearchResult` | `ADODB.Connection` on `Provider=Search.CollatorDSO` via `win32com`; `SELECT TOP n System.ItemPathDisplay, System.DateModified ... ORDER BY System.DateModified DESC` |
| `FileSearch` | `newest(folder, since) -> list[FileHit]` | same index, `SCOPE` on that folder (falls back to listing that one folder with `os.scandir` when the folder is not indexed — a single directory, not a scan) |
| `FileOpener` | `open(path)`, `reveal(path)` | `os.startfile`; `explorer.exe /select,"<path>"` |

**Known folder names (pt-BR):** downloads/baixados; documentos/meus documentos; área de
trabalho/desktop; imagens/fotos; vídeos; músicas; prints/capturas de tela.

**Config:** a new `[folders]` table, name → existing directory path. Validated at load like
`[sites]`: a path that is not an existing directory is dropped and logged (the folder may live
on an unplugged drive); a name that collides with a known folder overrides it.

**Search query (pure builder):** the name is escaped for Windows Search SQL — `'` doubled;
`%`, `_` and `[` escaped inside `LIKE` (`[%]`, `[_]`, `[[]`) — and matched with
`System.FileName LIKE '%<name>%'`, each word as its own `AND` term. Scope: the user profile and
the configured folders (`SCOPE='file:<dir>'` joined with `OR`); never the whole index (system
and program files stay out). `tipo` maps to extensions (`planilha` → xlsx/xls/ods/csv, `pdf` →
pdf, `documento` → docx/doc/odt/rtf/pdf, `apresentacao` → pptx/ppt/odp, `foto` →
jpg/jpeg/png/heic/webp/gif, `video` → mp4/mkv/mov/avi/webm, `musica` → mp3/flac/wav/m4a/ogg,
`texto` → txt/md). Folders themselves are excluded from results
(`System.Kind <> 'folder'`). Limit: `TOP 6` (5 to show + 1 to know there are more), plus a
`COUNT` only when 6 come back.

## 6. Safety

- **Program files are never run from a search.** A pure `is_program(path)` checks the
  extension against one list (`.exe .com .bat .cmd .ps1 .psm1 .vbs .vbe .js .jse .wsf .wsh
  .msi .msp .scr .pif .lnk .url .hta .cpl .jar .reg .appref-ms`); such a hit is revealed in
  Explorer, never opened, with "Por segurança, não executo programas encontrados na busca;
  abri a pasta dele." The test derives its cases from that list.
- The search string never reaches the SQL unescaped (pure builder, tested with quotes, `%`,
  `_`, `[`, `--`, `;`).
- `FileOpener.open` receives only paths that came from `FileSearch`/`KnownFolders` in this
  turn; it re-checks `is_program` itself (the load-bearing guard is in the adapter, the
  skill's check gives the better message — both tested).
- No file content is read. Episodes record the file **name**; the full path appears only in
  the episode's details in the dashboard.

## 7. Dialogue

- **Several files:** `AmbiguousSlot("arquivo", candidates)` where candidates are full paths;
  the persona renders each as `nome.ext (Pasta, quando)` with `quando` from `ctx.now`
  ("hoje 14:02", "ontem", "12/10"). More than 5: "Encontrei 12; os 5 mais recentes: …". The
  existing ordinal pick ("o primeiro", "o segundo") resolves it; choosing by label words
  ("o de ontem") is a later improvement, not 2b.
- One match: opens it. Exactly one hit whose name without extension equals the query
  (accents and case ignored) opens directly even when other names only contain it.
- `listar_recentes` answers the names (up to 10) and the count: "Hoje você baixou 3 arquivos:
  …".

## 8. Failures (pt-BR answers, all tested)

| Situation | Outcome |
|---|---|
| Named app without a window | `WindowNotFound` — "Spotify não está aberto, Mestre Artur." (focus offers to open) |
| No candidate window at all | `NoWindow` |
| Focus refused after the workaround | `FocusRefused` — "Não consegui trazer o X para frente; ele está piscando na barra de tarefas." |
| Monitor number too high | `NoSuchMonitor(n, count)` — "Só há 2 monitores, Mestre Artur." |
| Only one monitor on, "outro monitor" | `SingleMonitor` — "Só há um monitor ligado, Mestre Artur." |
| Windows Search unavailable / query error | `SearchUnavailable` — "A pesquisa do Windows não está disponível agora." (logged) |
| Nothing found | `FileNotFound(name, tipo)` — "Não encontrei nenhum arquivo chamado 'X'." / "nenhuma planilha chamada 'X'" |
| Configured folder missing | `FolderNotFound(name)` |
| Hit deleted after search | `FileGone(name)` — "Esse arquivo não existe mais." |
| Program hit | `ProgramRevealed(name)` (§6) |
| Downloads empty today | `NothingRecent` — "Você não baixou nada hoje, Mestre Artur." |

Adapters never raise to the user: unexpected exceptions become `ActionFailed` (existing rule).

## 9. Testing

- **Pure:** window choice (console excluded, z-order, Store frames, cloaked/tool/owned/
  CoreWindow skipped); geometry (halves; moves between monitors of different sizes; a monitor at
  negative x; clamping); monitor targeting; SQL builder escaping; `is_program` driven from its
  own list; tipo → extensions; every new extractor; label formatting with a fixed `now`;
  masking of pasta/arquivo.
- **Skills with fakes:** every row of §8, asserting the pt-BR text; focus-offers-open flow and
  that it learns nothing; repeat of minimise/snap/move.
- **NLU fixture:** ~50 new cases incl. near-ties (minimise/maximise/restore; focus vs open;
  folder vs app; file vs folder). Re-measure accuracy, false-execute, executed/asked; `t_*`
  unchanged unless re-tuning is justified and recorded.
- **Real model:** learning a window phrase does not pull its opposite
  (`tests/runtime/test_learning_with_model.py`).
- **`-m windows`:** Character Map minimise / restore / maximise / snap left / focus, reading the
  real placement back each time; show desktop / undo; index search finds a uniquely named temp
  file created in the user's Documents (polled until indexed, skipped with a reason after 30 s);
  open and close the Downloads folder window.
- **By hand at the end**, through the real `Assistant`, recorded in `CLAUDE.md`.
- **Measured:** search latency (median/p95 over 20 queries), startup time and RSS after 2b.

**Unverified unless the user helps:** moving a window to the second monitor on the real
desktop (needs the second monitor on — ask the user at by-hand time, otherwise record it as
unverified); a real foreground refusal (timing-dependent; covered with fakes only).

## 10. Documentation

Local `CLAUDE.md` updated in the same commits: `skills` (new intents, focus-offers-open rule),
`adapters/windows` (cloaked windows, DWM frame offset, foreground lock, index SQL escaping,
program-file rule), `nlu` (new extractors, masking of pasta/arquivo), `runtime` (config
`[folders]`). Proofs in `docs/superpowers/proofs/2026-10-16-sub-project-2b.md`.
