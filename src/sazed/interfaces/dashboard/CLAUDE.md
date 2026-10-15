# sazed.interfaces.dashboard

The local, read-only admin page (`uv run sazed painel`): stdlib HTTP server, JSON endpoints and
one static page. Design and rulings: `docs/superpowers/specs/2026-10-15-dashboard-design.md`.

## Layout rule
- Pure, stdlib-only, no I/O or clock: `ledger`, `stats`, `redact`, `processes`
  (`tests/interfaces/dashboard/test_pure_modules.py` enforces it; keep new pure logic there).
- Impure shell: `sources` (files, git, psutil), `api` (query validation → payload), `server`
  (HTTP only), `launch` (the one clock, wiring). Nothing outside this package imports it except
  `interfaces/cli/main.py`, lazily (tested).
- Data from the rest of Sazed comes through `sazed.runtime.insight`; this package may import
  only `sazed.runtime` and itself (`tests/test_architecture.py`).

## Invariants
- Bind `HOST` (127.0.0.1) only; Host header checked; GET only (`__getattr__` turns every other
  `do_X` into 405 — never define another `do_` method).
- The coppermind is opened through `CoppermindReader` (`mode=ro`). No endpoint writes anything.
- Every endpoint query goes through its `ROUTES` spec (`parse_query`); messages are pt-BR.
- A source that cannot be read answers `available: false` with a pt-BR message; unexpected
  errors are logged and answered with `GENERIC_ERROR`. Never put exception text in a payload.
- The page loads nothing from outside (`test_static_files` scans for URLs); CSP has no
  `'unsafe-inline'`, so no inline `<script>`, `<style>` or `style=""`; set styles from JS.
- Data reaches the DOM only as `textContent` (`h()`); never `innerHTML` with data.

## Traps
- `print` is block-buffered when stdout is piped: console messages go through `say()` (flushes).
- `uv run sazed` is four processes; RSS lives in the last `python.exe`. Do not match "sazed" as
  a substring: the project folder is named Sazed.
- psutil's first `cpu_percent` reads 0; the first sample after start is always 0%.
- The ledger format belongs to another agent: never drop a line you do not recognise.
- After a new skill or port lands, update `runtime.insight.skills_for_listing` and
  `PORT_DESCRIPTIONS`; their tests fail until you do.
- Tests run `serve_forever(0.02)`; the default 0.5 s poll makes each server test 0.5 s slower.

## Not here
SQL (→ `adapters/sqlite/reader.py`), skill/config introspection (→ `runtime/insight.py`).
