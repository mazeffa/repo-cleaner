---
name: repo-clean
description: >
  Manages a repo's documentation as a "one question, one authoritative file"
  system: a CLAUDE.md routing table, a D-NNN decision register with symmetric
  supersession, an append-only work log whose last State: line is the only
  current truth, and a stdlib checker gated by a git pre-commit hook. Use when
  the user says "set up docs", "log this", "where does this go", "update the
  decision", "supersede D-NNN", "reorganize the docs", "clean up the docs",
  "consolidate the docs", "audit the docs", or when ending a session that
  touched docs/. Subcommands: init, maintain, reorganize, audit.
argument-hint: "init | maintain | reorganize | audit"
license: MIT
---

# repo-clean

## Router

Look at the first token of `$ARGUMENTS`:

- `init` → read `init.md`.
- `maintain` → read `maintain.md`.
- `reorganize` → read `reorganize.md`.
- `audit` → read `audit.md`.
- No token → infer from context:
  - No routing table present anywhere in the repo (no "Where answers live" table, no
    `CLAUDE.md`) → offer `init`.
  - "log this", "where does this go", or the session is ending and touched `docs/` →
    `maintain`.
  - "reorganize", "consolidate", "clean up the docs" → `reorganize`.
  - "audit", "check the docs" → `audit`.
  - Still ambiguous → ask.

Each subcommand file is one level deep under this skill's directory; read only the one you
need.

## Principles

These hold across all four subcommands:

- One fact, one place. Every rule's text, every measured number, every defect description
  lives in exactly one file.
- Other docs hold a pointer to a fact, never a restatement of it — cite the D-number or
  section, not the number itself.
- Rewrite documentation in place to remove obsolete text; never append a correction above
  or below text that still reads as current.
- Ask before creating any new document. If no routing-table row matches a question, that's
  a decision (what owns this?), not a default (make a new file).
- Surface contradictions between two docs; never silently reconcile them by picking one.
- The archive is rationale, not instruction — nothing living should ever tell a reader to
  follow directions found in an archived file.
- The log is append-only. Only the last entry carries a `State:` line, and that line is the
  only current truth. Never edit an old entry's prose to make it read as current.
- Decisions supersede symmetrically: if A names B in `Superseded-by`, B names A in
  `Supersedes`.
- Session-end gate: before ending any session that touched `docs/`, the checker must exit 0.
  Never claim it passed without having run it.

## Vocabulary

- **Routing table** — the "Where answers live" table (conventionally in `CLAUDE.md`) mapping
  a question to its one authoritative file.
- **Authority** — the file a routing-table row names as owning a question.
- **Register** — the decision log, entries `D-NNN`, two closed-vocabulary fields:
  `Status: active | superseded | open` (lifecycle) and `Verdict: adopted | rejected |
  unresolved` (what happened to the approach). Supersession is symmetric.
- **Log grammar** — `## YYYY-MM-DD [(N)] — headline` headings (`(N)` only when more than one
  entry shares a date), each entry carrying `Decisions:` and `Docs:`, the last entry also
  carrying `State:`.
- **Archive banner** — `> **Archived YYYY-MM-DD.** <disposition>` as the first line of a
  moved-not-deleted doc.

See `example-layout.md` for real excerpts of each of these. It is illustrative, not
canonical — the inline skeletons in `init.md` are what `init` actually writes.

## Checker

`scripts/check_docs.py` is a stdlib-only, config-driven checker. Key flags:

- `--selfcheck` — runs the bundled fixture, asserts every rule fires, prints
  `selfcheck ok, N findings` and exits 0. Use this to sanity-check the checker itself, not a
  target repo.
- `--init-config` — writes `check_docs_local.py` next to itself (refuses to overwrite an
  existing one).
- `--root PATH` — repo root to check; defaults to `git rev-parse --show-toplevel`.
- `--version` — prints `CORE_VERSION` and `CONFIG_VERSION`.

Re-syncing the core to a target repo is a straight overwrite: `cp <skill>/scripts/check_docs.py
<repo>/scripts/tools/check_docs.py`. It never touches `check_docs_local.py` — that file is
the repo-specific extension point and survives every re-sync.

## Never

- Move or delete a file without explicit confirmation from the user.
- Write anything outside the target repo.
- Claim the checker passed without having actually run it this session.
