# Sazed

A local, offline, JARVIS-style personal assistant for Windows 11, with the persona of
Sazed, the Terris Keeper from *Mistborn*. Read [`AGENTS.md`](./AGENTS.md) and
[`.claude/rules/`](./.claude/rules/) first.

- **User-facing language:** pt-BR, masculine persona, addresses the user as "Mestre Artur".
- **No external AI APIs, ever.** Deterministic NLU core; a local SLM only on demand.
- **Stack:** Python 3.12 (uv), onnxruntime embedder (multilingual-e5-small), SQLite.
- **Hardware budget:** Ryzen 5 8600G, ~12 GB RAM, iGPU only. Everything is CPU-bound;
  keep idle memory low.

## Status

- 2026-10-14: brainstorm done. Roadmap and sub-project 1 design are in
  [`docs/superpowers/specs/2026-10-14-sazed-core-design.md`](./docs/superpowers/specs/2026-10-14-sazed-core-design.md).
- 2026-10-14: spec approved; implementation plan written in
  [`docs/superpowers/plans/2026-10-14-sazed-core.md`](./docs/superpowers/plans/2026-10-14-sazed-core.md).
- **Next step:** execute docs/superpowers/plans/2026-10-14-sazed-core.md (inline, branch
  `feat/sub-project-1`).

## Commands

- `uv sync` — install (Python 3.12 is pinned in `.python-version`; the machine default is 3.14).
- `uv run pytest` — fast suite (excludes `model` and `windows` markers).
- `uv run pytest -m model` — tests that need the downloaded embedder (`uv run python scripts/fetch_model.py` first).
- `uv run pytest -m windows` — tests that open real apps and change the real volume.
- `uv run ruff check . && uv run ruff format --check . && uv run mypy` — lint, format, strict types (`core`, `nlu`).
- `uv run sazed` — the REPL.

## Layout

`src/sazed/{core,nlu,skills,adapters,runtime,interfaces}`. The dependency direction is enforced by
`tests/test_architecture.py`. Test doubles live in `tests/fakes/`, and each has its own test.

## Toolchain traps

- Ruff formats Python code blocks inside Markdown; `*.md` is excluded in `pyproject.toml` so
  docs are not rewritten.

## Verified by hand

2026-10-15, real model (int8) and desktop, placeholder thresholds, via piped stdin to
`uv run sazed --config <temp>`: `volume em 30` → 30%; `aumenta o volume` → 40%; `de novo` → 50%;
`muta` / `tira do mudo` → muted / unmuted; `abre o character map` → opened;
`fecha o character map` → confirmation asked (low score), `sim` → closed and the phrase was learned;
`esquece isso` → that example forgotten. Volume restored afterwards.
**Unverified:** typing in an interactive console (only piped stdin was used), Ctrl-C handling,
`sazed aprendizado` / `revisar` against the real data dir (covered only by tests with fakes).
