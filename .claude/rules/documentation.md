# Documentation

## Every important directory carries a local CLAUDE.md

Each significant directory has its own `CLAUDE.md` explaining what someone needs to
know **before** touching that directory. The purpose is twofold: correctness, so
conventions are not rediscovered or violated; and cost, so reading one short file
replaces re-reading the whole directory.

**Where they belong** — one per directory that has its own domain, not one per folder.
A directory earns one when it has conventions of its own, invariants to uphold, or
traps someone has already fallen into.

**What a local CLAUDE.md contains:**

- The directory's one-sentence responsibility.
- Conventions that are not obvious from reading one file — naming, ordering, the pattern every file here follows.
- Invariants that code here must uphold, and where they are enforced.
- The traps: things that look correct and are not, and defects previously fixed here so they are not reintroduced.
- What must NOT go in this directory, and where it goes instead.

**What it must not contain:**

- A file-by-file inventory. That goes stale immediately and duplicates what `ls` shows.
- Anything already covered by `.claude/rules/` — link to the rule instead of restating it.
- Implementation detail that changes with every commit.

**Keep them current.** When you change a convention in a directory, update its
`CLAUDE.md` in the same commit. A stale local `CLAUDE.md` is worse than none, because
it is trusted.

**Before saving a new pattern**, summarize it and confirm where it belongs — the local
`CLAUDE.md` for changeable conventions, `.claude/rules/` only for things that must
never change.

## Documentation that makes claims must be tested

Prose rots silently. Whenever a document states a formula, a worked example or an
expected result:

- Keep the example as a real fixture and parse it with the real schema in a test.
- Recompute every published number in that test, so a wrong one fails the build.
- If the document restates a formula the code implements, assert the two agree across a
  range of inputs. Otherwise a reader following the document will compute something the
  application does not.

A document whose claims are checked can be trusted after its author has forgotten it.
A document whose claims are not checked starts lying the first time the code moves.
