# Development Strategy

## TDD

- Always use TDD (Test Driven Development). This is non-negotiable and paramount.
- Write failing tests first, then implement the minimum code to make them pass, then refactor.
- Never write implementation code without a preceding test.

## Git Discipline

- Maintain an organized git history with professional commit standards.
- Follow Conventional Commits: `type(scope): description` (e.g. `feat(auth): add session refresh`, `fix(parser): reject an ambiguous prefix`).
- Each commit represents a single logical unit of work.
- Write commit messages in English.
- Never commit broken or half-finished code to the main branch.

## Every test must be able to fail

A test nobody has watched fail is a guess. Codebases ship, routinely, tests that are
green while being structurally incapable of catching the bug they exist for.

- **When a test exists to pin a specific property, prove it discriminates:** deliberately break the implementation, confirm that test fails, then revert. Paste the failing output into the report or PR description.
- **Pick the mutation a person would actually write.** Swapping two mutually exclusive `instanceof` checks, or `'k' in obj` for `obj.k !== undefined`, proves nothing — those are semantically equivalent. The realistic bug is the truthy check, the forgotten `await`, the missing exclusion clause, the off-by-one default.
- **Assert the value, not just the shape.** A test asserting a field *exists* can pass for months while the value inside it is wrong — the wrong language, the wrong unit, the wrong sign.
- **Re-query the source, don't trust the response.** A handler can return the right payload without persisting anything. Tests that assert stored state catch what response assertions cannot.
- **Never hand-enumerate what can be derived.** A guard listing today's fields will not cover tomorrow's; drive it from the schema's own keys (or equivalent) so a new field is covered automatically.
- **Verify a shared test helper before building on it.** A broken helper invalidates every test that depends on it, silently and all at once. Prove the helper does what its name says before anything relies on it.
- **A test that passes under the mutation is a finding, not a failure.** Say so, move the assertion to where the guarantee actually lives, and prove it there. Do not keep mutating until something goes red.

## Verification

- Never claim work is complete, fixed, or passing without running the verification command and reading its output.
- Evidence before assertions, always.
- Read the code, but *run* the commands. The most damaging defects are the ones that look correct on the page and only fail when executed — a command that silently resolves to something else, a config that is ignored, a version that is not the one pinned.
- When something cannot be verified — no device, no credentials, a tool that will not start — **say so plainly and name what is unverified**. Do not let "tests pass" stand in for "I checked it works".
