---
name: repo-clean
description: >
  Manages a repo's documentation as a "one question, one authoritative file"
  system: a CLAUDE.md routing table, a work list, a D-NNN decision register
  with symmetric supersession, an append-only dated log, and a stdlib checker
  the session-start hook runs. Use when the user
  says "set up docs", "log this", "the session is over", "where does
  this go", "update the decision", "supersede D-NNN", "reorganize the docs",
  "clean up the docs", "consolidate the docs", or "audit the docs".
  Subcommands: init, maintain (--check for a read-only report), reorganize.
argument-hint: "init | maintain [--check] | reorganize"
license: GPL-3.0-or-later
---

# repo-clean

## Router

Look at the first token of `$ARGUMENTS`:

- `init` → read `init.md`.
- `maintain` → read `maintain.md`.
- `reorganize` → read `reorganize.md`.
- No token → infer from context:
  - No routing table present anywhere in the repo (no "Where answers live" table, no
    `CLAUDE.md`) → offer `init`.
  - "log this", "where does this go", or the user saying the session is over →
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
- The log is append-only dated history: no entry is edited, and no entry carries current
  state — that is read from its owners (D-029(6)). An entry is what someone needs to resume —
  typically 5 to 15 lines — not a narrative of the session.
- Work to do — a bug, a task, an idea — is a row in `docs/WORK.md`, not a decision or a line
  in the log. Claude updates it as things come up: a bug found, a step put off, something
  finished. A row is never deleted; closing it sets its Status and Closed date (D-029(8)).
- Decisions supersede symmetrically: if A names B in `Superseded-by`, B names A in
  `Supersedes`.
- The checker must exit 0; SessionStart runs it and prints any finding, and `maintain` runs
  it before finishing. Never claim it passed without having run it.
- Never commit, stash, stage, or change git settings (including `.gitignore`) on the
  user's behalf. Git is the user's storage, not this tool's (D-029(1)).

## Vocabulary

- **Routing table** — the "Where answers live" table (conventionally in `CLAUDE.md`) mapping
  a question to its one authoritative file.
- **Authority** — the file a routing-table row names as owning a question.
- **Register** — the decision log, entries `D-NNN`, one closed-vocabulary field:
  `Status: active | superseded | rejected`. Only decisions; nothing waits there.
- **Work list** — `docs/WORK.md`, one table `ID | Item | Type | Status | Added | Closed`;
  Type `bug | task | idea`, Status `open | done | dropped`.
- **Log grammar** — `## YYYY-MM-DD [(N)] — headline` headings (`(N)` only when more than one
  entry shares a date), each entry carrying `Decisions:` and `Docs:`.
- **Archive banner** — `> **Archived YYYY-MM-DD.** <disposition>` as the first line of a
  moved-not-deleted doc. A convention; the checker does not enforce it (D-029(7)).
- **Research doc** — `docs/research/<subject>.md`, the authority for a subject's *evidence*:
  measurements, accuracy, how something actually behaves. Rewritten in place rather than
  appended to, so it always reads as current, and carrying `Status:`/`Date:` because
  nothing else reveals its age (a convention the checker does not enforce, D-029(7)). Evidence goes here; the *belief* drawn from that evidence
  is a `D-NNN` entry. One session usually produces both. `init` writes one routing row per
  subject (`init.md`); `routing-coverage` does not require one, so an unrouted research doc
  is not flagged.

See `example-layout.md` for real excerpts of each of these. It is illustrative, not
canonical — the inline skeletons in `init.md` are what `init` actually writes.

## Hooks

One hook, SessionStart, shipped in `hooks/` and wired in `hooks/hooks.json`. It reads and
prints; it writes no doc, and its only state is offered.json, so the setup offer fires once
(D-029(a)).

It finds the **home** by walking up from the working directory to the nearest
`.repo-clean` marker (D-023). It prints one `Open:` line per open work item (or "nothing
open in docs/WORK.md"), then the log's last entry — heading, age in days, and body, read by
the checker's own parsers, so the two never disagree — then `repo-clean <version>` (the
running plugin's version, so a stale install shows), then any checker problem: raise those
before other work. It never runs git (D-029(a)). Opened above several homes, it prints one
line naming them; with no home near, it points at `/repo-clean init` once.

It runs through `hooks/run.sh`, which finds a Python 3.8+ (`py -3`, `python`, `python3`); if
there is none it says so instead of silently doing nothing.

The log is written when the user asks (`/repo-clean maintain`, "log this") or says the
session is over — words, not hooks.

`hooks/selftest.py` is the one test command: it drives the hook and `run.sh` against scratch
homes, and holds the checker's rule tests. It tests this plugin repo's own `hooks/`, not an
installed plugin cache. Nothing runs it automatically — run it by hand after changing
`hooks/` or the checker.

## Checker

`scripts/check_docs.py` is a stdlib-only checker. One flag:

- `--root PATH` — the home to check. Default: the nearest `.repo-clean` marker at or above
  the current folder. No marker there, or a `--root` that is not a home, exits 2 — nothing was
  checked.

Exit 0 clean, 1 findings, 2 nothing could be checked. No copy is vendored into a target repo
(D-015), and there is no per-project add-on: the checker never runs project code (D-022). Its
rules are listed in its own docstring (D-029(7)).

## Never

- Move or delete a file without explicit confirmation from the user.
- Write anything outside the target repo — the hook's offered.json is the one exception
  (D-029(a)).
- Overwrite a tracked repo file without the user's confirmation.
