---
name: repo-clean
description: >
  Manages a repo's documentation as a "one question, one authoritative file"
  system: a CLAUDE.md routing table, a D-NNN decision register with symmetric
  supersession, an append-only work log whose last State: line is the only
  current truth, and a stdlib checker the session hooks run. Use when the user
  says "set up docs", "log this", "fold in", "the session is over", "where does
  this go", "update the decision", "supersede D-NNN", "reorganize the docs",
  "clean up the docs", "consolidate the docs", or "audit the docs".
  Subcommands: init (--migrate for a pre-marker home), maintain (--check for a read-only
  report), reorganize.
argument-hint: "init [--migrate] | maintain [--check] | reorganize"
license: GPL-3.0-or-later
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
  - "log this", "fold in", "where does this go", or the user saying the session is over →
    `maintain`.
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
- The log is append-only. Only the last entry carries `State:` and `Next:` lines, and they
  are the only current truth. Never edit an old entry's prose to make it read as current. An entry is
  what someone needs to resume — typically 5 to 15 lines — not a narrative of the session.
- Decisions supersede symmetrically: if A names B in `Superseded-by`, B names A in
  `Supersedes`.
- The checker must exit 0; the Stop hook runs it whenever a doc changed and blocks on a
  finding. Never claim it passed without having run it.
- Never commit, stash, stage, or change git settings (including `.gitignore`) on the
  user's behalf. Git is the user's storage, not this tool's (D-021).

## Vocabulary

- **Routing table** — the "Where answers live" table (conventionally in `CLAUDE.md`) mapping
  a question to its one authoritative file.
- **Authority** — the file a routing-table row names as owning a question.
- **Register** — the decision log, entries `D-NNN`, two closed-vocabulary fields:
  `Status: active | superseded | open` (lifecycle) and `Verdict: adopted | rejected |
  unresolved` (what happened to the approach). Supersession is symmetric.
- **Log grammar** — `## YYYY-MM-DD [(N)] — headline` headings (`(N)` only when more than one
  entry shares a date), each entry carrying `Decisions:` and `Docs:`, the last entry also
  carrying `State:` and `Next:`.
- **Fold-in** — Claude reading earlier sessions' transcripts and writing what happened into
  the docs (`maintain.md`). The only act that writes the log (D-021).
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

Three hooks, shipped in `hooks/` and wired in `hooks/hooks.json`, record the work and check
the docs; none of them writes a doc (D-021):

- **SessionStart.** Finds the **home** (D-018) by walking up from the working directory to
  the nearest `.repo-clean` marker, or a pre-marker (legacy) folder with `CLAUDE.md` and
  `docs/log/`; a legacy home gets a one-line `/repo-clean init --migrate` hint. It prints the
  log's last `State:` and `Next:`, then any checker finding — raise those before other work.
  On a fresh start (not resume, clear or compact), if earlier sessions in this home are not
  yet folded in, it says how many and prints the `fold.py` path: run fold-in
  (`maintain.md`) unless the user says not now. Opened above several homes, it prints one
  line naming those with un-folded work, or the homes found if none has any; with no home
  near, it points at `/repo-clean init` once.
- **PostToolUse** (`Edit`/`Write`/`MultiEdit`/`NotebookEdit`). Records the changed file under
  the home that file belongs to, resolved from the file's own path. No output.
- **Stop.** Records the session (its transcript path and time) against every home it
  touched, or the home it opened in if it edited nothing. If a `.md` in a touched home
  changed, it runs the checker for that home and blocks on a finding, naming it. It blocks
  once: while Claude is continuing because of the hook, it lets the session stop.

The record lives under the user's `.claude/repo-clean/homes/`, not in the home, one file per
home and session, kept until a fold-in covers it. Fold-in is triggered by words, not hooks:
the user asks (`/repo-clean maintain`, "fold in"), the user says the session is over, or the
session-start line above.

`hooks/selftest.py` drives all three hooks and `fold.py` against scratch homes; it tests this
plugin repo's own `hooks/`, not an installed plugin cache. Nothing runs it automatically —
run it by hand after changing `hooks/`.

## Checker

`scripts/check_docs.py` is a stdlib-only, config-driven checker. Key flags:

- `--selfcheck` — runs the bundled fixture, asserts every rule fires, prints
  `selfcheck ok, N findings` and exits 0. Use this to sanity-check the checker itself, not a
  target repo.
- `--init-config` — writes `check_docs_local.py` into the target repo's local-module dir
  (`scripts/tools/` if the script isn't already installed there; refuses to overwrite an
  existing one).
- `--root PATH` — repo root to check; defaults to `git rev-parse --show-toplevel`.
- `--version` — prints `CORE_VERSION`, a short digest of the checker's own source, and
  `CONFIG_VERSION`.

The checker exists once, in the plugin (D-015) — no copy is vendored into a target repo, and
there is nothing to re-sync. `check_docs_local.py` is the repo-specific extension point; it
is optional everywhere and a production repo shouldn't have one without recording why in its
own register (D-013).

## Never

- Move or delete a file without explicit confirmation from the user.
- Write anything outside the target repo.
- Claim the checker passed without having actually run it this session.
- Overwrite a tracked repo file without the user's confirmation.
