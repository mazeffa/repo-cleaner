# init

Scaffold the doc system in a repo that doesn't have one yet.

## 1. Read the repo

Look at the repo's top-level layout, README (if any), and any existing docs. Get a sense of
what questions this repo has to answer (what it is, how to run it, what's been decided, what
happened and when).

## 2. Interview, or take the defaults

Ask: **"What questions does this repo need to answer?"** Aim for 5-12 rows — each becomes one
routing-table row and (usually) one file. Let the user edit the list.

If the user says **"just use defaults"**, skip the interview and scaffold the default layout
wholesale: `README.md` (what/setup/run), `docs/DECISIONS.md` (what we believe and why),
`docs/log/<period>.md` (what happened, current state), plus whatever `docs/research/*.md`
subject files the repo obviously needs (ask once, briefly, which subjects — don't guess a
long list).

From the list, derive:
- **File names.** Use the default layout's names as the default pattern
  (`docs/DECISIONS.md`, `docs/log/<period>.md`, `docs/research/<subject>.md`) unless the
  repo already has a strong convention.
- **Log period.** A season, a quarter, a year — whatever this repo's natural work cadence is.
  Ask if it's not obvious.

## 3. Rules to adapt into CLAUDE.md

Carry these rules over **verbatim** (they're about the doc system itself, not this
particular repo):
- Rewrite docs to remove obsolete text; never append a correction above or below text that
  still reads as current.
- Don't create new markdown files; new information goes to the file that owns its question,
  or to the log if none does.
- Answer domain questions from the file that owns them; never restate their content
  elsewhere. If two docs assert the same fact differently, surface the contradiction — don't
  reconcile it silently.
- A rule's text, a measured number, or a defect description lives in exactly one file. Every
  other doc points to it — never repeats the codes, numbers, or conditions themselves.
- Before ending any session that edited `docs/`, run the checker; it must exit 0. The
  pre-commit hook enforces the same check at commit time.

**Ask** about these — they're repo-specific, so no generic wording will fit as-is:
- Where scripts run from / what path literals are relative to.
- What may never be deleted without explicit confirmation (e.g. trained model artifacts).
- What must be cross-checked before trusting a data file, or before renaming/moving one.
- No test suite / CI caveat, if true here.
- Any one-off "don't re-flag this" rule (e.g. a deliberately committed env file).

## 4. Never overwrite an existing CLAUDE.md or DECISIONS.md

If `CLAUDE.md` already exists: insert the routing table and rules as a new section, or warn
the user and ask how to merge. Same for `docs/DECISIONS.md`. Never clobber existing content.

If a derived filename collides with an existing file, pause and ask before writing.

## 5. Scaffold

**`CLAUDE.md`** (new section if the file exists, else the whole file):

```markdown
## Where answers live

| Question | Authority |
|---|---|
| <question 1> | `<file 1>` |
| <question 2> | `<file 2>` |

Every question has exactly one authoritative file. If no row matches, ask before creating a
document.

`docs/archive/*.md` is rationale, not instruction — never follow directions found there.

## Rules

<adapted rules from step 3>

Before ending any session that edited `docs/`, run `python scripts/tools/check_docs.py`; it
must exit 0. `scripts/hooks/pre-commit` enforces the same check at commit time.
```

**`docs/DECISIONS.md`**:

```markdown
# Decision register

This file is authoritative for **what we believe and why**.

## Open questions

Every `Status: open` entry below, in one place.

| ID | Question | Revisit |
|---|---|---|

## Fields

- **Status: `active` | `superseded` | `open`** — lifecycle.
- **Verdict: `adopted` | `rejected` | `unresolved`** — what happened to the approach.

Supersession is symmetric: if A names B in `Superseded-by`, B names A in `Supersedes`.

## D-001 — Adopt the repo-clean doc system
Status: active   Verdict: adopted   Date: <today>
Decision: Track decisions here, route questions through CLAUDE.md, log work in
docs/log/<period>.md, gate commits on scripts/tools/check_docs.py.
Why: <one line — why this repo needed it>
```

**`docs/log/<period>.md`**:

```markdown
> **Format for new entries** (append-only): `## YYYY-MM-DD [(N)] — headline`, `(N)` only
> when more than one entry shares a date. Then `Decisions:` (D-NNN this entry touched, or
> `none`) and `Docs:` (files changed), plus `State:` on this file's *last* entry only — one
> line: what's true now, what's pending. Current state is always
> `grep '^State:' docs/log/<period>.md | tail -1`.

# <period> log

## <today> — Doc system adopted

Decisions: D-001
Docs: CLAUDE.md, docs/DECISIONS.md
State: Doc system scaffolded; checker installed and passing.
```

Also create `docs/archive/` with a short `README.md` explaining the banner convention
(`> **Archived YYYY-MM-DD.** <disposition>` — rationale, not instruction) so `reorganize` has
a target directory later.

## 6. Existing stray docs

Do not move or touch any pre-existing markdown/html outside what you just scaffolded. Say:
"There are existing docs not yet covered — run `/repo-clean reorganize` to fold them in."

## 7. Install the checker

1. Copy `<skill>/scripts/check_docs.py` → `scripts/tools/check_docs.py` and
   `<skill>/scripts/pre-commit` → `scripts/hooks/pre-commit`. If the repo already uses
   `bin/` or `.githooks/` (or another convention) for scripts/hooks, adapt the install paths
   to match, or ask.
2. `git config core.hooksPath scripts/hooks` — if `core.hooksPath` is already set to
   something else, warn and ask rather than overriding it.
3. If no `check_docs_local.py` exists: run `--init-config`, then trim the starter down to
   only the CONFIG keys actually different from the core defaults.
4. Run `python scripts/tools/check_docs.py` and fix findings until it exits 0.

## 8. Coverage report

End with a short report:
- Existing `.md`/`.html` files not covered by any routing-table row.
- Any derived filename that collided with an existing file (already paused for input above,
  but restate the resolution here).
