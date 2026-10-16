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
  Dates come back in UTC; `_local`/`_utc` convert, and `newest` sends its "since" in UTC.
  COM is initialised per call (the REPL and dashboard threads differ). The SQL is built only by
  `skills/pc/files.py` (escaped there).
- `WindowsFileOpener.open` refuses `PROGRAM_EXTENSIONS` itself: that is the load-bearing guard,
  the skill's check only gives the better answer.
