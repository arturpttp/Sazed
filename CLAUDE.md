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
- **Next step:** the user reviews the plan and picks an execution mode; then Task 1.

Commands, layout and toolchain notes are added here as the project is scaffolded.
