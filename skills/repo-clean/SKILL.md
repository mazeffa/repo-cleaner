---
name: repo-clean
description: >
  Manages a repo's documentation as a "one question, one authoritative file"
  system: a CLAUDE.md routing table, a D-NNN decision register with symmetric
  supersession, an append-only work log whose last State: line is the only
  current truth, and a stdlib checker gated by a git pre-commit hook. Use when
  the user says "set up docs", "log this", "where does this go", "update the
  decision", "supersede D-NNN", "reorganize the docs", "clean up the docs",
  "consolidate the docs", or "audit the docs".
  Subcommands: init, maintain (--check for a read-only report), reorganize.
argument-hint: "init | maintain [--check] | reorganize"
license: MIT
---

# repo-clean

## Router

Look at the first token of `$ARGUMENTS`:

- `init` → read `init.md`.
- `maintain` → read `maintain.md`.
- `reorganize` → read `reorganize.md`.
- `audit` or `check` → read `maintain.md`, run it in `--check` mode.
- No token → infer from context:
  - No routing table present anywhere in the repo (no "Where answers live" table, no
    `CLAUDE.md`) → offer `init`.
  - "log this" or "where does this go" → `maintain`.
  - "reorganize", "consolidate", "clean up the docs" → `reorganize`.
  - "audit", "check the docs" → `maintain --check`.
  - Still ambiguous → ask.

Each subcommand file is one level deep under this skill's directory; read only the one you
need.

## Principles

These hold across all three subcommands:

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
- The checker must exit 0 before you commit; the Stop hook enforces this every session that
  changed files, and the pre-commit hook is a backstop where git exists. Never claim it
  passed without having run it.

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
- **Research doc** — `docs/research/<subject>.md`, the authority for a subject's *evidence*:
  measurements, accuracy, how something actually behaves. Rewritten in place rather than
  appended to, so it always reads as current, and carrying `Status:`/`Date:` because
  nothing else reveals its age. Evidence goes here; the *belief* drawn from that evidence
  is a `D-NNN` entry. One session usually produces both. Research docs are exempt from
  routing coverage — the subject dir is routed, not each file.

See `example-layout.md` for real excerpts of each of these. It is illustrative, not
canonical — the inline skeletons in `init.md` are what `init` actually writes.

## Hooks

Four hooks, shipped in `hooks/` and wired in `plugin.json`, make the doc system automatic
instead of relying on the model to remember it:

- **SessionStart.** If the repo has no routing table or no checker, it says so and points
  at `/repo-clean init`. Otherwise it prints the log's last `State:` line, so the session
  starts with the current picture instead of re-discovering it.
- **PostToolUse** (`Edit`/`Write`/`MultiEdit`/`NotebookEdit`). Records which file just
  changed, keyed to this session. No output, no cost — bookkeeping only.
- **Stop.** If this session changed files, it does the log work itself: creates or updates
  this session's entry (heading, `Decisions:`, `Docs:`), moves `State:` onto it, and runs
  the checker — then blocks, naming exactly what's unresolved (an unfilled headline/`State:`,
  a checker finding, or both). It keeps blocking on retry until fixed, but only for three
  tries — after that it fails open with a warning rather than wedging the session shut over
  something Claude can't fix (e.g. a finding that needs a human decision). A reply that only
  reads or answers, touching no files, is silent and never blocks.
- **PreCompact.** Folds any pending edits into the log entry before context is lost, so a
  compaction never drops the record of what changed. Non-blocking — compaction can't be
  refused, this just leaves something to resume from.

Session state (which files changed, which entry belongs to this session) lives under
`~/.claude/repo-clean/sessions/`, not in the repo, so this works identically with or
without git.

`hooks/selftest.py` drives all four hooks and the pre-commit gate against a scratch repo;
it tests this plugin repo's own `hooks/`, not an installed plugin cache. Run it directly,
or it runs automatically from `scripts/hooks/pre-commit` when that file is present.

## Checker

`scripts/check_docs.py` is a stdlib-only, config-driven checker. Key flags:

- `--selfcheck` — runs the bundled fixture, asserts every rule fires, prints
  `selfcheck ok, N findings` and exits 0. Use this to sanity-check the checker itself, not a
  target repo.
- `--init-config` — writes `check_docs_local.py` into the target repo's local-module dir
  (`scripts/tools/` if the script isn't already installed there; refuses to overwrite an
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
