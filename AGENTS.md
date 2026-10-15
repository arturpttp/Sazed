# AGENTS.md

Start here if you are an agent working in this repository.

## The rules

[`.claude/rules/`](./.claude/rules/) holds the working agreements. They override default
behaviour and are not negotiable:

- [`development.md`](./.claude/rules/development.md) — TDD, git discipline, and
  **"every test must be able to fail"**
- [`engineering.md`](./.claude/rules/engineering.md) — boundaries, purity, validate
  before writing, absent-is-not-null, what never reaches a user
- [`documentation.md`](./.claude/rules/documentation.md) — where knowledge lives and
  how it is kept from going stale
- [`language.md`](./.claude/rules/language.md) — what language to write in, and where

These are **behavioural**: they describe how to work, not what this project is. They
were extracted from a codebase where each one was learned the expensive way, and they
carry no assumptions about stack, domain or framework.

## What belongs where

Anything specific to *this* project — stack, layout, commands, data model, current
status, toolchain traps — belongs in `CLAUDE.md` at the root, not in the rules. The
split is deliberate:

- **`.claude/rules/`** — things that must never change. Edit only with a decision behind it.
- **`CLAUDE.md`** — things that change as the project evolves.
- **A directory's own `CLAUDE.md`** — conventions local to that directory.

## The habit that matters most

Prove a test can fail before trusting it. Break the implementation, watch that specific
test go red, revert. Reporting that a probe *did not* discriminate is the expected
outcome, not a failure — bending the mutation until something goes red is the thing to
avoid.
