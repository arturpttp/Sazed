# Language

- **Always respond to the user in English**, even when they write in Portuguese.
- **Code identifiers, comments, commit messages and documentation are in English.**
- **The user-facing interface is in the project's own language** — every label, button,
  placeholder, empty state, toast and error message. Set that language once in the
  project's `CLAUDE.md`; this rule only fixes that the two are separate decisions.

The split is the point: the code reads in one language for anyone who maintains it, and
the product reads in another for whoever uses it. Mixing them produces an English
validation message on a Portuguese screen, which is the defect this prevents.
