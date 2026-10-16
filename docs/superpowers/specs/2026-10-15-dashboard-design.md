# Sazed — Admin dashboard (`sazed painel`)

Date: 2026-10-15
Status: Implemented on `feat/dashboard`: read-only first round, then editable learnings (§6).
Builds on: [sub-project 1](./2026-10-14-sazed-core-design.md). Runs beside
[sub-project 2a](./2026-10-15-sazed-pc-skills-2a-design.md), which was being built at the same time.

## 1. What the user asked for

"Antes de tudo, faça um painel para eu acompanhar o progresso, o uso de recursos e os
pensamentos, além de outras coisas; vai ser um site rodando localmente." Clarified: a complete
admin dashboard, read-only at first, "with everything you think it needs to be nice".

## 2. Panels and their sources

| Panel | Shows | Source |
|---|---|---|
| Visão geral | Sazed running or not, commands today, failure rate, learned totals, dev progress, PC CPU/RAM, live recent commands, last commit | all of the below |
| Raciocínio | per command: utterance, ranking with scores against the threshold marks, slots, decision and why, outcome, failure flag, reaction, what was learned from it; live, filterable, paged | `episodes`, `learned_examples`, `slot_aliases` |
| Desenvolvimento | active plan, tasks done/active/pending with commits and test results, current task, rulings, final fixed/deferred items, unknown ledger lines verbatim, recent commits and branch, proofs files, all plans | `docs/superpowers/plans/*.md`, `.superpowers/sdd/<plan>/progress.md`, `git log`, `docs/superpowers/proofs/*.md` under `--raiz` |
| Aprendizado | per day: executed / asked / not understood, failure rate, examples and aliases learned, cumulative totals; 7/30/90/365 days; each chart has a table view | `episodes`, learned tables |
| Recursos | Sazed's process (RSS, CPU, uptime, the launcher chain), PC CPU/RAM history while the page is open, disks, the dashboard's own RSS | psutil |
| Coppermind | episodes, learned examples, aliases, with search and filters | coppermind (read-only) |
| Capacidades & Config | every skill and intent (seed count and texts, slots and questions, confirmation), ports and their adapters, what Sazed may touch, effective config with origin and redaction, data/model paths and presence, the app catalog | skill specs, `config.toml` + defaults, the file system, `StartMenuCatalog` |

**Why a decision was made** is not stored. The dashboard re-runs `core.policy.decide` on the
stored scores with the *current* thresholds (so the rule is never restated), says which case
applied, and flags a recorded decision the current thresholds would not make.

**Failure** means: decision `NotUnderstood`/`error`, a failure outcome, or a `denied`/`corrected`
reaction — the same rule as `SqliteCoppermind.recent_failures`; a test asserts they agree.
Dialogue-control turns ("sim", "esquece isso") are not counted as commands.

## 3. Shape

- `adapters/sqlite/reader.py` — read-only reader (`file:…?mode=ro`, one connection per call).
- `runtime/insight.py` — skills listed with inert ports, ports derived from skill constructors,
  decision explanations, config view, paths.
- `interfaces/dashboard/` — pure `ledger`, `stats`, `redact`, `processes`; impure `sources`
  (files, git, psutil); `api` (validated query → payload); `server` (HTTP); `launch` (CLI entry);
  `static/` (one page, vanilla JS, inline SVG charts).
- `sazed painel [--porta N] [--raiz PASTA]` in the CLI; it never loads the model.

## 4. Rulings

1. **Loopback only, not configurable.** Binds `127.0.0.1`; the page holds private data and has
   no login. *Cost if wrong:* no access from another device until a token scheme exists.
2. **Host header must be `127.0.0.1:<port>` or `localhost:<port>`** (403 otherwise), against DNS
   rebinding from a web page. *Cost:* a custom hosts alias for 127.0.0.1 is refused.
3. **GET reads, POST writes** (round 2; first round was GET only); every other verb 405 through
   one catch-all, so a new `do_X` cannot slip in.
4. **Strict CSP** (`default-src 'self'`), no CDN, no inline script or style. Styles set from JS
   use the CSSOM, which CSP allows.
5. **Read-only by SQLite, not by convention:** `mode=ro`. A missing database is an empty state,
   never created. The dashboard writes only its own log, `logs/painel.log` (it creates the logs
   folder if missing). *Cost:* none known.
6. **The dashboard is an I/O shell like the CLI.** psutil, git and file reads live in
   `interfaces/dashboard/sources.py`, not in `adapters`: interfaces may not import adapters, and
   moving them would mean three runtime pass-through modules for no testability gain (the pure
   logic is already separate and tested). *Cost if wrong:* a later move to adapters, mechanical.
7. **Skills are listed with inert ports** (`runtime.insight.skills_for_listing`), not by building
   the app (that loads the model and opens the writable store). A test asserts the list equals
   `build_app`'s; it fails when a skill is added without updating the listing.
8. **Ports are derived** from each skill constructor's Protocol annotations; descriptions are a
   map with a test that every derived port has one.
9. **Redaction by key name** (`secret`, `token`, `password`, `key`, substring, case-insensitive),
   whole value or whole section. *Cost:* a harmless alias named like "keyboard" is hidden too.
10. **The ledger is parsed tolerantly**; every non-blank line is kept, unknown ones as `raw`.
    The active plan is the newest plan file (by name) whose ledger exists.
11. **The repo root defaults to the project root** of the running code; `--raiz` points it at
    the main checkout (the ledger is git-ignored and lives only there).
12. **Sazed's process** is any process whose command line *runs* sazed (`sazed.exe`,
    `python …\sazed.exe`, `python -m sazed…`, `uv run sazed`), never one that merely mentions a
    "Sazed" folder, and never `sazed painel`. The main process is a match with no matching child
    (the real interpreter under uv's launchers, verified on this machine).
13. **Sampling only while polled**, at most once a second, process rescan every 10 s, 150 samples
    (about 5 minutes at the 2 s poll). Nothing samples when no page is open.
14. **An invalid `config.toml` stops `sazed painel`** with the same pt-BR message Sazed gives.
15. **Confirmation is shown as "nunca" or "conforme o pedido"**: a predicate cannot be told
    apart from "always" by probing it.

## 5. Not in this round (needs a decision or a schema change)

- Per-command latency, the confirm reason as decided at the time, the thresholds in force, and
  the response text are not in `episodes`; they need a migration.
- Learned items that were forgotten disappear from the per-day counts (rows are deleted).
- Editing the config from the page is still absent.

## 6. Round 2: editable learnings

Asked: add and remove learned items, fix (edit) them, and comment on them. Sub-project 2a was
merged into `feat/dashboard` first, so the edits reuse its `IntentSpec.learnable`, the
`label_episode` safeguards and `build_skills`.

| Action | Where in the page | Path | Same as |
|---|---|---|---|
| Forget an example/alias, then "Desfazer" | Coppermind | `runtime.editing.Editor.forget/undo` → `SqliteCoppermind.snapshot/forget/restore` | `sazed aprendizado --esquecer` |
| Teach a phrase (text + intent) | Coppermind → Exemplos | `admin.learn_example` | live learning safeguards |
| Teach what a command meant | Raciocínio | `admin.label_episode` | `sazed revisar --rotular [--forcar]` |
| Fix an example's text or intent | Coppermind → Exemplos | `admin.edit_example` → `replace_example` | — |
| New alias / fix its target | Coppermind → Apelidos | `admin.add_alias/edit_alias` → `replace_alias` | — |
| Notes (add, edit, remove) | every example, alias and command | `notes` table (migration 2) | — |

Results come back as codes (`learned`, `conflict`, `not_learnable`, `already_known`, `empty`,
`saved`, `app_unknown`, `exists`, `forgotten`, `restored`, …) and the page shows a pt-BR
message for each; a conflict offers "Guardar mesmo assim" (force), a forget offers "Desfazer".
Every change to what Sazed knows says "Vale a partir do próximo início do Sazed."

### Rulings (round 2)

16. **Writes are POST only**, JSON bodies validated by pydantic models with `extra="forbid"`
    and per-field limits, messages translated to pt-BR by a table (a schema-driven test sends a
    bad value to every field of every model and rejects English or the fallback).
17. **Every POST needs** the per-launch token (`secrets.token_urlsafe(32)`, put into the page
    as a `<meta>`, compared with `hmac.compare_digest`), an `Origin` equal to the dashboard's
    origin (or, without `Origin`, a same-origin `Referer`), `Content-Type: application/json`,
    and a `Content-Length` of at most 16 KiB. The checks run before the body is read.
    *Cost if wrong:* a local program that can read the page can still write — the same reach
    it already has over the database file.
18. **Reads and writes use different connections.** GET stays on the `mode=ro` reader; writes
    go through `runtime.editing.Editor` on a single worker thread (a SQLite connection belongs
    to its thread) with `SqliteCoppermind` (default busy timeout 5 s). The first write creates
    the database if it is missing.
19. **The model loads only for examples** (teach, fix, label), lazily, once; aliases, notes and
    forget never load it. `/api/editor` reports idle/loading/ready/failed and the page shows a
    loading notice. A missing model is a pt-BR `EditorUnavailable`, and the next try retries.
20. **Editing keeps the id**: `replace_example` / `replace_alias` delete and re-insert the same
    id in one transaction (refs like `e3` and the notes stay attached) and give it a new
    learning batch, so "esquece isso" in Sazed would forget the corrected item.
    *Cost if wrong:* a user expecting "esquece isso" to undo only the correction loses the item.
21. **An edit is judged as a new example without its old version** (removed from the session
    index first, put back if refused or failed), otherwise changing only the intent would
    always conflict with itself.
22. **Aliases are slot `app` only**, normalised like live aliases, the target must match a
    catalog name (Start menu + Store + configured sites, accents and case ignored), and adding
    never overwrites an existing alias (`exists` → use Corrigir).
23. **Notes are for Mestre Artur only**: Sazed never reads them; forgetting an item deletes its
    notes in the same transaction (also for "esquece isso"); undo restores both. Episodes are
    never deleted, so their notes stay. Notes do not get the "next start" remark.
24. **Undo lives in the dashboard's memory** (last 50 forgets, until it stops). It restores the
    exact row (embedding included) and notes, and refuses if the id or the alias was taken.
25. **The dashboard's ports raise** (unlike evaluation's `DryRunPorts`, which absorb calls): it
    never executes a skill, so reaching a port is a bug.
26. **onnxruntime is loaded before WinRT** whenever the dashboard scans the catalog (native
    crash otherwise; see the proofs).

### Not in round 2

- A running Sazed does not see edits until it restarts (its index is in memory). A reload
  command or a file watch would need its own design.
- Undo for an edit (only forget has undo) and an audit log of who changed what.
