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
- Store (UWP) apps have no `.lnk`: WhatsApp, the new Notepad and Calculator are invisible
  to `StartMenuCatalog`. Integration tests use `charmap.exe` for that reason.
- Some shortcuts target a launcher (`Discord` → `Update.exe`), so closing cannot find their process.
- Closing posts `WM_CLOSE` and never terminates, so unsaved work gets the app's own prompt.
- `root_pids` counts instances by parent/child, otherwise Chrome's helpers look like many instances.
- SQLite migrations are append-only, and `PRAGMA user_version` is the schema version.
- `sqlite/reader.py` (dashboard) opens `file:…?mode=ro` per call. That URI mode is what keeps
  it read-only and stops it from creating a missing database; never drop it for a plain path.
  It must follow schema changes made in `coppermind.py` (its tests seed through the writer).
- e5 needs the `"query: "` prefix on both sides; it is applied only in `OnnxEmbedder`.
- The int8 e5 model quantizes activations over the whole batch, so `OnnxEmbedder` embeds one
  sentence per run. Batching again makes a vector depend on its batch-mates (see proofs).
