# sazed.interfaces.dashboard

The local admin page (`uv run sazed painel`): stdlib HTTP server, GET JSON reads, POST writes
of learned items and notes, and one static page. Design and rulings:
`docs/superpowers/specs/2026-10-15-dashboard-design.md` (§4 reads, §6 writes).

## Layout rule
- Pure, stdlib-only, no I/O or clock: `ledger`, `stats`, `redact`, `processes`
  (`tests/interfaces/dashboard/test_pure_modules.py` enforces it; keep new pure logic there).
- Impure shell: `sources` (files, git, psutil), `api` (GET: query validation → payload),
  `writes` (POST: pydantic body → editor → pt-BR answer), `server` (HTTP and security only),
  `launch` (the one clock, the token, wiring). Nothing outside this package imports it except
  `interfaces/cli/main.py`, lazily (tested).
- Data and edits come through `sazed.runtime` (`insight`, `editing`, `admin`); this package may
  import only `sazed.runtime` and itself (`tests/test_architecture.py`).

## Invariants
- Bind `HOST` (127.0.0.1) only; Host header checked on every request.
- GET never writes and never loads the model: reads use `CoppermindReader` (`mode=ro`);
  `/api/editor` only reports state (proof: "reads: the editor status 'warms up' the model").
- Writes are POST only, to `WRITE_ROUTES`, and `_write_refusal` runs before the body is read:
  token (`hmac.compare_digest`), exact same-origin `Origin` (or same-origin `Referer`), JSON
  content type, `Content-Length` ≤ `MAX_BODY`. Only `do_GET`/`do_POST` exist; `__getattr__`
  turns every other verb into 405 — never add another `do_` method.
- Every write runs on `WriteApi`'s single worker thread (SQLite connections are per thread).
- Every body model forbids extra fields; every field has a pt-BR label in `FIELD_LABELS` and
  every pydantic error type a pt-BR text in `_ERRORS` (`test_writes.py` derives both from the
  models). Every result code has a pt-BR message in `MESSAGES`.
- Unexpected errors are logged and answered generically; never put exception text in a payload.
- The page loads nothing from outside; CSP has no `'unsafe-inline'`; data reaches the DOM only
  as `textContent` (`h()`); all POSTs go through `write()` in `app.js` (token, notices, force,
  undo).

## Traps
- `print` is block-buffered when stdout is piped: console messages go through `say()`.
- Import onnxruntime before WinRT (`runtime.editing.real_catalog` does): the other order is a
  native access violation that kills the process (`-m windows` test).
- Live refresh re-renders the panel: a form being filled must be marked with `dirty()` or it
  is wiped (`panelBusy`).
- `uv run sazed` is four processes; RSS lives in the last `python.exe`. Do not match "sazed" as
  a substring: the project folder is named Sazed.
- psutil's first `cpu_percent` reads 0; the first sample after start is always 0%.
- The ledger format belongs to another agent: never drop a line you do not recognise.
- After a new skill or port lands, update `PORT_DESCRIPTIONS` in `runtime.insight`; the listing
  itself comes from `build_skills`, and its parity test fails if they drift.
- Tests run `serve_forever(0.02)`; the default 0.5 s poll makes each server test 0.5 s slower.

## Not here
SQL (→ `adapters/sqlite`), skill/config introspection (→ `runtime/insight.py`), edit rules and
safeguards (→ `runtime/admin.py`, `runtime/editing.py`).
