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

- 2026-10-14: brainstorm done; spec in
  [`docs/superpowers/specs/2026-10-14-sazed-core-design.md`](./docs/superpowers/specs/2026-10-14-sazed-core-design.md).
- 2026-10-15: sub-project 1 (core + text CLI + PC slice) implemented per
  [`docs/superpowers/plans/2026-10-14-sazed-core.md`](./docs/superpowers/plans/2026-10-14-sazed-core.md)
  on branch `feat/sub-project-1`. Discrimination proofs:
  [`docs/superpowers/proofs/2026-10-14-sub-project-1.md`](./docs/superpowers/proofs/2026-10-14-sub-project-1.md).
- NLU fixture (87 cases: 39 apps, 27 volume, 21 out of domain, incl. opposing near-ties):
  accuracy 0.909, false-execute 0.011 (1 case), in-domain executed 0.409 / asked 0.591 /
  not understood 0.000, with t_exec=0.94, t_confirm=0.88, g_min=0.01 (embedder variant qint8).
  The tuner never goes below g_min=0.01 (0 would disable the spec's gap rule). Before the
  near-tie cases (82 cases, g_min=0.0): int8 accuracy 0.918 / false-execute 0.012 / executed
  0.459; fp32 0.918 / 0.000 / 0.393 — int8 kept (it meets the bar).
- e5-small weighs the object (app name, number) over the verb: seeds deliberately share objects
  across opposing intents (open/close, up/down/set) so the verb decides. Keep that when adding seeds.
- **Unverified:** `learning.t_conflict` / `t_dup` are placeholders (no fixture measures them yet);
  Store (UWP) apps are not in the catalog; closing apps whose shortcut targets a launcher.
- 2026-10-15: sub-project 1 merged into `main`. Sub-project 2 split into 2a (one-shot PC skills:
  media, system, web, status, Store apps) and 2b (windows, files). 2a spec:
  [`docs/superpowers/specs/2026-10-15-sazed-pc-skills-2a-design.md`](./docs/superpowers/specs/2026-10-15-sazed-pc-skills-2a-design.md).
- 2a plan: [`docs/superpowers/plans/2026-10-15-sazed-pc-skills-2a.md`](./docs/superpowers/plans/2026-10-15-sazed-pc-skills-2a.md) (16 tasks).
- **Next step:** user review of the 2a plan, then implementation on `feat/sub-project-2a`.

## Measurements

2026-10-15, Ryzen 5 8600G, `scripts/measure_embedder.py`, variant qint8:
load 0.72 s, RSS +402 MB (process total 470 MB); 92 seed examples embedded in 164 ms;
single sentence median 1.9 ms, p95 2.8 ms. Breakdown measured separately: the tokenizer
(`tokenizer.json`, 250k-token vocabulary) alone is +277 MB, the ONNX session +139 MB. The spec's
~200 MB estimate is exceeded mainly by the tokenizer — a candidate fix for a later sub-project.

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
2026-10-15 (after a bug report from use): `abaixa o volume para 100` at 40% → 100%;
`aumenta o volume pra 30` at 100% → 30%; `abaixa o volume pra zero` → 0%.
**Unverified:** typing in an interactive console (only piped stdin was used), Ctrl-C handling,
`sazed aprendizado` / `revisar` against the real data dir (covered only by tests with fakes).
