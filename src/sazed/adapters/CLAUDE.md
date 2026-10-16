# sazed.adapters

Implementations of ports: `sqlite/` (coppermind), `onnx/` (embedder), `windows/` (catalog,
launcher, audio). This is the only package allowed to touch the OS, files, or models.

## Conventions
- Keep the Windows-API part thin and push decisions into pure functions (`build_entries`,
  `root_pids`) that are tested without Windows.
- Windows-only imports (`win32*`, `pycaw`, `comtypes`) are done inside methods, so the module
  imports on any machine and pure tests run anywhere.
- Integration tests are `@pytest.mark.windows` (real apps, real volume) or `@pytest.mark.model`.

## Traps
- Store apps come from `shell:AppsFolder` (`store.py`); their names may be English
  ("Calculator"), so `DEFAULT_APP_ALIASES` maps pt-BR names. Their visible window is owned by
  `ApplicationFrameHost.exe`, not the app: `windows_to_close` also closes frames hosting a
  child window of the app's process. Right after launch the app's own top-level
  `Windows.UI.Core.CoreWindow` exists before the frame adopts it and ignores WM_CLOSE: it is
  never a target, and `close` waits up to 2 s for the frame (a race seen in the windows suite).
- WinRT calls are async: adapters run them to completion with `asyncio.run` inside the method.
- Squirrel shortcuts target a launcher (`Discord` → `Update.exe`): `_matches` looks for the real
  executable under the launcher's folder.
- Closing posts `WM_CLOSE` and never terminates, so unsaved work gets the app's own prompt.
- `root_pids` counts instances by parent/child, otherwise Chrome's helpers look like many instances.
- SQLite migrations are append-only, and `PRAGMA user_version` is the schema version.
- `sqlite/reader.py` (dashboard) opens `file:…?mode=ro` per call. That URI mode is what keeps
  it read-only and stops it from creating a missing database; never drop it for a plain path.
  It must follow schema changes made in `coppermind.py` (its tests seed through the writer).
- Schema 2 adds `notes` (target example/alias/episode). Forgetting (`forget`, `forget_latest`)
  deletes the item's notes in the same transaction; `replace_example`/`replace_alias` delete and
  re-insert the same id in ONE transaction (a failure midway leaves the old row: tested).
  Check a conflict with a query before writing (`restore`), never by catching IntegrityError.
- e5 needs the `"query: "` prefix on both sides; it is applied only in `OnnxEmbedder`.
- The int8 e5 model quantizes activations over the whole batch, so `OnnxEmbedder` embeds one
  sentence per run. Batching again makes a vector depend on its batch-mates (see proofs).
- Windows Search (`windows/files.py`): `System.ItemPathDisplay` is a localised *display* path
  ("C:\Usuários\…\Documentos") that does not exist on disk — read `System.ItemUrl`.
  Dates come back in UTC; `_local` converts. `newest` lists its one folder with `os.scandir`
  (the index lags behind a fresh download) and skips partial downloads.
  COM is initialised per call (the REPL and dashboard threads differ). The SQL is built only by
  `skills/pc/files.py` (escaped there).
- `WindowsFileOpener.open` opens a folder or a file whose type is in `OPENABLE_EXTENSIONS` (an
  allow-list; a deny-list missed `.msc`/`.chm`) and refuses the rest itself: that is the
  load-bearing guard, the skill's check only gives the better answer.
- The ancestor walk for "Sazed's own console" stops at the shell (`SHELL_PROCESSES`):
  explorer.exe starts terminals and owns every File Explorer window.
- Minimised and maximised windows report `rcNormalPosition` (workspace → screen, minus
  `FRAME_INSET`): the minimised rect is the (-32000, -32000) parking spot.
- Windows (`windows/windows.py`): EnumWindows is z-order, frontmost first. A user window is
  visible, not DWM-cloaked (suspended Store apps, other virtual desktops), not a tool window,
  unowned, titled, and not a shell or CoreWindow class. Sazed's console = its own pid and every
  ancestor (terminal, shell, uv), plus any frame hosting one of them as a child.
- Windows 10/11 windows have ~7 px invisible borders: positions use
  `DWMWA_EXTENDED_FRAME_BOUNDS` and `outer_rect`; the real test checks within 2 px (8 px hid
  the bug). Restore a maximised/minimised window before `SetWindowPos`.
- `SetForegroundWindow` is refused unless this process had the last input: `focus` retries
  after a synthetic Alt key, then flashes the taskbar button and returns False.
- The real window tests use a throwaway Tk window (Character Map cannot be resized). Showing
  the desktop runs only with `SAZED_TEST_DESKTOP=1`: it minimises the user's windows too.
- With the display asleep (user idle for hours) Windows suspends a just-launched Store app
  before its frame adopts it: the Calculator close test fails on any branch. Run `-m windows`
  with the screen on.
