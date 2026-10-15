# Engineering Invariants

These are what keep a codebase testable and its failures legible. Do not violate them
to save a few lines.

## Dependency direction is one-way

- Draw the arrows once and never draw one back. A shared/core package is imported by
  everything and imports nothing from its consumers.
- The shared core stays **free of the environment**: no UI framework, no server
  framework, no database client, no I/O. It is plain code.
- A client never reaches past its boundary. If the browser can talk to a database
  directly, the boundary is already gone.

## Pure logic lives in the core, and stays pure

- Parsing, formatting, domain arithmetic, date math and aggregation have zero I/O and
  belong in the shared core, where they are testable without a server or a database.
- **Pure functions never read the clock, the environment, or the network.** Anything
  time-dependent takes `now`/`today` as a parameter. There should be exactly one place
  in the application where a clock is read, and it passes the value down.
- Handlers stay thin: validate → call the store → return. Business logic that can be
  pure must be pure and must live in the core.

## One contract, one place

- Request and response shapes are defined once and used by both sides. No codegen, no
  duplicated type definitions kept in sync by hand.
- Every request body and query string is validated against that shared schema before it
  reaches business logic. No hand-rolled parsing in handlers.

## Validate before writing, and write atomically

The recurring shape of partial-write defects is always the same: write first, discover
the problem second.

- **All validation precedes the first write.** Referenced rows exist, business rules
  hold, the payload is internally consistent — check all of it, then write.
- **A request that fails leaves no trace.** Any operation issuing more than one write
  uses the store's atomic primitive. Two sequential awaits are a partial write waiting
  for a network blip.
- **Know which guard is load-bearing.** When two layers both exclude something, only
  one of them is usually the rule; the other is an optimisation. Find out which by
  removing each and seeing whether a test fails, then put the assertion where the
  guarantee actually lives and say so in a comment.

## Failures are typed, and never leak internals

- **A domain failure is never a generic server error.** Throw a typed error carrying a
  message meant for a person and the right status code.
- **Check a conflict with a query, not by catching the driver's exception.** Parsing a
  database error message to classify a failure is how that message ends up on a user's
  screen.
- Never leak ORM messages, SQL error codes, stack traces or framework internals to a
  client. Map the unknown to a generic error and log the real one on the server.
- Every validation message is written for the reader, in the project's user-facing
  language, including the object-level one. A field without an explicit message falls
  back to the library's default — usually English, usually jargon. **Guard this with a
  schema-driven test, not by remembering.**

## Absent is not null

- `undefined` (key absent) and `null` (key explicitly null) mean different things and
  must be distinguished with `'key' in obj`, never a truthy check.
- In a partial update, absent means "leave alone" and null means "clear". A truthy
  check collapses them, and silently drops every legitimate falsy value — `0`, `false`,
  `''` — on the way.

## Secrets

- Never commit a secret, and **never fall back to a hardcoded default** when one is
  missing. A crypto routine will happily sign against the literal string `"undefined"`.
  Fail closed and log the misconfiguration.
- No credential or token in client-side storage.

## Explicit over spread at a boundary

- Map rows to the shapes you return field by field, never by spreading the record. A
  column added later should be withheld from the outside world until someone decides it
  belongs there — not exposed by default.
- The same applies in reverse for anything that must round-trip: list the fields, and
  let a test prove nothing was dropped.
