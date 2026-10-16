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
- NLU fixture (150 cases after sub-project 2a, incl. opposing near-ties, sites, Store apps, power):
  accuracy 0.928, false-execute 0.000, in-domain executed 0.496 / asked 0.504 / not understood
  0.000, with t_exec=0.94, t_confirm=0.88, g_min=0.01 (embedder variant qint8; not re-tuned for 2a).
  Before 2a (87 cases): accuracy 0.909, false-execute 0.011. `tests/nlu/test_fixture_rules.py`
  forbids fixture phrases that copy a seed.
- e5-small weighs the object (app name, number) over the verb: seeds deliberately share objects
  across opposing intents (open/close, up/down/set) so the verb decides. Keep that when adding seeds.
- **Unverified:** `learning.t_conflict` / `t_dup` are placeholders (no fixture measures them yet);
  closing apps whose shortcut targets a launcher.
- **Fixed (2026-10-15):** once "abre o whatsapp" was learned from a confirmation, "fecha o
  whatsapp" ranked `abrir_app` (e5 weighs the object). Learned phrases now store "programa" in
  place of the app name (`mask_app`), so a learned wording also works for every app. Pinned with
  the real model in `tests/runtime/test_learning_with_model.py` (the fixture never learns).
  Not masked yet: numbers ("pra 20") and the web search's query and site.
- 2026-10-15: sub-project 1 merged into `main`. Sub-project 2 split into 2a (one-shot PC skills:
  media, system, web, status, Store apps) and 2b (windows, files). 2a spec:
  [`docs/superpowers/specs/2026-10-15-sazed-pc-skills-2a-design.md`](./docs/superpowers/specs/2026-10-15-sazed-pc-skills-2a-design.md).
- 2a plan: [`docs/superpowers/plans/2026-10-15-sazed-pc-skills-2a.md`](./docs/superpowers/plans/2026-10-15-sazed-pc-skills-2a.md) (16 tasks),
  implemented on `feat/sub-project-2a`. Proofs:
  [`docs/superpowers/proofs/2026-10-15-sub-project-2a.md`](./docs/superpowers/proofs/2026-10-15-sub-project-2a.md).
- 2a final review done (fresh reviewer): 1 Critical + 2 Important fixed (forced shutdown,
  site closes, "desmuta o computador"); minors deferred in the 2a ledger.
- 2026-10-15: 2a, the editable dashboard and the Store close-race fix merged into `main`.
- **Next step:** brainstorm 2b (windows, files).

## Measurements

2026-10-15, Ryzen 5 8600G, `scripts/measure_embedder.py`, variant qint8:
load 0.72 s, RSS +402 MB (process total 470 MB); 92 seed examples embedded in 164 ms;
single sentence median 1.9 ms, p95 2.8 ms. Breakdown measured separately: the tokenizer
(`tokenizer.json`, 250k-token vocabulary) alone is +277 MB, the ONNX session +139 MB. The spec's
~200 MB estimate is exceeded mainly by the tokenizer — a candidate fix for a later sub-project.

2026-10-15, after 2a, `scripts/measure_app.py` (full app: model, 9 skills, 285 seed examples,
Start-menu + Store catalogs, all adapters): startup 2.4–2.8 s, RSS +430 MB (process 473 MB).

## Commands

- `uv sync` — install (Python 3.12 is pinned in `.python-version`; the machine default is 3.14).
- `uv run pytest` — fast suite (excludes `model` and `windows` markers).
- `uv run pytest -m model` — tests that need the downloaded embedder (`uv run python scripts/fetch_model.py` first).
- `uv run pytest -m windows` — tests that open real apps and change the real volume.
- `uv run ruff check . && uv run ruff format --check . && uv run mypy` — lint, format, strict types (`core`, `nlu`, the dashboard and its reader/insight modules; list in `pyproject.toml`).
- `uv run sazed` — the REPL.
- `uv run sazed painel [--porta 8765] [--raiz <repo>]` — local dashboard (reads; edits learned items and notes) at
  http://127.0.0.1:8765 (see `src/sazed/interfaces/dashboard/CLAUDE.md`).

## Layout

`src/sazed/{core,nlu,skills,adapters,runtime,interfaces}`. The dependency direction is enforced by
`tests/test_architecture.py`. Test doubles live in `tests/fakes/`, and each has its own test.

## Toolchain traps

- Ruff formats Python code blocks inside Markdown; `*.md` is excluded in `pyproject.toml` so
  docs are not rewritten.
- A redirected or piped stdout on Windows is cp1252 (no "→"): `cli.main` reconfigures
  stdout/stderr to UTF-8 once, at entry. Print nothing before that call.

## Verified by hand

2026-10-15, real model (int8) and desktop, placeholder thresholds, via piped stdin to
`uv run sazed --config <temp>`: `volume em 30` → 30%; `aumenta o volume` → 40%; `de novo` → 50%;
`muta` / `tira do mudo` → muted / unmuted; `abre o character map` → opened;
`fecha o character map` → confirmation asked (low score), `sim` → closed and the phrase was learned;
`esquece isso` → that example forgotten. Volume restored afterwards.
2026-10-15 (after a bug report from use): `abaixa o volume para 100` at 40% → 100%;
`aumenta o volume pra 30` at 100% → 30%; `abaixa o volume pra zero` → 0%.
2026-10-15, sub-project 2a, real model and desktop, through the real `Assistant` (temp data dir):
`o que está tocando` → title and channel of the Vivaldi video; `pausa a música` / `continua a música`
→ paused, resumed; `tira um print` → `Captura 2026-10-15 18-21-34.png` (2.1 MB) in
`Pictures\Screenshots`; memory / CPU / disk → pt-BR numbers; `desliga o computador` → confirmation,
`não` → nothing; `abre as configurações de bluetooth` → that page; `brilho em 50` → WMI reads 50
(restored to 100); `abre o youtube`, `pesquisa lofi no youtube` → browser tabs;
`abre a calculadora` / `fecha a calculadora` → opened, closed; `fecha o whatsapp` → confirmed,
window closed (WhatsApp keeps running in the background, as with its own X); `fecha o youtube` →
"não consigo fechar abas".
**Unverified (2a):** `próxima música` / `música anterior` (not run: would skip the user's video),
`recorta a tela` (opens an overlay that waits for the user), `bloqueia o computador` (needs the
user present), whether brightness 50 was visibly dimmer (WMI accepted it).
2026-10-16: `uv run sazed --config <temp> aprendizado > file` over a copy of the real
coppermind → exit 0, UTF-8 file with "→" (before the fix: UnicodeEncodeError, exit 1).
**Unverified:** typing in an interactive console (only piped stdin was used), Ctrl-C handling,
`sazed revisar` against the real data dir (covered only by tests with fakes).
