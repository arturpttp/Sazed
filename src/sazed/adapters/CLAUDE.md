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
  child window of the app's process.
- WinRT calls are async: adapters run them to completion with `asyncio.run` inside the method.
- Some shortcuts target a launcher (`Discord` → `Update.exe`), so closing cannot find their process.
- Closing posts `WM_CLOSE` and never terminates, so unsaved work gets the app's own prompt.
- `root_pids` counts instances by parent/child, otherwise Chrome's helpers look like many instances.
- SQLite migrations are append-only, and `PRAGMA user_version` is the schema version.
- e5 needs the `"query: "` prefix on both sides; it is applied only in `OnnxEmbedder`.
- The int8 e5 model quantizes activations over the whole batch, so `OnnxEmbedder` embeds one
  sentence per run. Batching again makes a vector depend on its batch-mates (see proofs).
