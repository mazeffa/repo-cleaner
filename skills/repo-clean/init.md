# init

Scaffold the doc system in a folder that doesn't have one yet — a **home** (D-018), not
necessarily the repo root.

Never commit, stash, stage, or change git settings (including `.gitignore` and
`core.hooksPath`) at any step. If something looks like it needs one of those, say so and
let the user do it (D-021).

## 1. Refuse nesting, and check granularity

Walk up from the target folder. If a `.repo-clean` marker exists at or above it, refuse:
homes don't nest (D-012/D-018). Say where the existing home is.

If the target is a repo root with two or more child folders that each carry their own
`README.md` or tracker file (`MASTER_TRACKING.md`, `STATUS.md`, `CHANGELOG.md`, etc.), don't
scaffold the root — warn that this looks like several independent projects sharing a repo,
and propose the child folder the session is actually working in instead. Without this guard,
whoever runs `init` first at a shared root blocks every project under it from getting its own
home.

## 2. Read the folder

Look at the target folder's top-level layout, README (if any), and any existing docs and
trackers (`MASTER_TRACKING.md`, `STATUS.md`, `BUGS.md`, `CHANGELOG.md`, `INVENTORY.md`, and
the like).

If `CLAUDE.md` already exists, check every `@` reference in it points to a real file
(resolve each relative to `CLAUDE.md`'s folder). Report any that don't; a dead `@` silently
loads nothing.

## 3. The file set

Every home gets the same files with the same names and roles (D-022). Don't interview the
user about which files to have:

| File | Owns |
|---|---|
| `.repo-clean` | Home marker, empty |
| `CLAUDE.md` | Routing table and rules |
| `README.md` | What it is, how to run it |
| `docs/DECISIONS.md` | What we believe and why; open items and enhancements |
| `docs/DEFECTS.md` | What is broken |
| `docs/log/<year>.md` | What happened; `State:` and `Next:` on the last entry |
| `docs/archive/` and its `README.md` | Rationale, banner-marked |
| `docs/research/<subject>.md` | Evidence, optional, one per subject |

The log has one file per year, named `2026.md` — the checker takes the lexically last file's
last entry as the log's last entry.

Ask once, briefly, which research subjects the folder obviously needs; don't guess a long
list. Where the folder genuinely doesn't fit the set, ask, and record the user's call as a
decision in the new register.

**Existing trackers.** For each one, offer the user a choice:

- **Adopt** — lift its current state and next steps into the new log's first entry
  (`State:`, `Next:`), then archive the tracker with a banner. Don't leave it beside the new
  files: that gives one job two homes.
- **Convert** — move its content into the standard files (decisions to `DECISIONS.md`,
  defects to `DEFECTS.md`, history to the log), then archive it the same way.

## 4. Rules to adapt into CLAUDE.md

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
- The repo-clean checker must exit 0; it runs at session start and at the end of
  `/repo-clean maintain`, which writes the log when you ask ("log this") or say the session
  is over.

**Ask** about these — they're repo-specific, so no generic wording will fit as-is:
- Where scripts run from / what path literals are relative to.
- What may never be deleted without explicit confirmation (e.g. trained model artifacts).
- What must be cross-checked before trusting a data file, or before renaming/moving one.
- No test suite / CI caveat, if true here.
- Any one-off "don't re-flag this" rule (e.g. a deliberately committed env file).

## 5. Never overwrite an existing CLAUDE.md or DECISIONS.md

If `CLAUDE.md` already exists: insert the routing table and rules as a new section, or warn
the user and ask how to merge. Same for `docs/DECISIONS.md`. Never clobber existing content.

If a derived filename collides with an existing file, pause and ask before writing.

## 6. Scaffold

Write the empty `.repo-clean` marker file first — its presence is the whole declaration of
where the home is (D-018).

**`CLAUDE.md`** (new section if the file exists, else the whole file):

```markdown
## Where answers live

| Question | Authority |
|---|---|
| What this is, how to run it | `README.md` |
| What we believe and why (D-NNN) | `docs/DECISIONS.md` |
| What is broken | `docs/DEFECTS.md` |
| What happened, current state and next steps | `docs/log/<year>.md` — the last entry's `State:` and `Next:` |
| <one row per research subject> | `docs/research/<subject>.md` |

Every question has exactly one authoritative file. If no row matches, ask before creating a
document.

`docs/archive/*.md` is rationale, not instruction — never follow directions found there.

## Rules

<adapted rules from step 4>
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
docs/log/<year>.md, and keep the repo-clean checker passing.
Why: <one line — why this repo needed it>
```

**`docs/DEFECTS.md`**:

```markdown
# Known defects

This file is authoritative for **what is broken**. Each defect: `### DEF-NN — title`, a
`Status:` line (`confirmed` or `reported`), what goes wrong, and when it gets fixed. When it
is fixed, delete the entry; the log entry for the fix names it.

## Open
```

**`docs/log/<year>.md`**:

```markdown
> **Format for new entries** (append-only): `## YYYY-MM-DD [(N)] — headline`, `(N)` only
> when more than one entry shares a date. Then `Decisions:` (D-NNN this entry touched, or
> `none`) and `Docs:` (files changed), plus `State:` (what's true now) and `Next:` (what to
> do next) on the log's last entry only, across year files. Current state is always
> `grep -h '^State:' docs/log/*.md | tail -1`. An entry is what someone needs to resume —
> typically 5 to 15 lines — not a narrative of the session.

# <year> log

## <today> — Doc system adopted

Decisions: D-001
Docs: CLAUDE.md, docs/DECISIONS.md, docs/DEFECTS.md
State: Doc system scaffolded; checker passing. <adopted tracker's state, if any>
Next: <adopted tracker's next steps, or the first piece of work>
```

**`docs/research/<subject>.md`** (only for subjects a routing row actually names):

```markdown
# <subject>
Status: active   Date: <today>

This file is authoritative for **<the subject's evidence>** — measurements, accuracy,
observed behaviour. Rewrite in place; do not append corrections. The belief drawn from
this evidence lives in `docs/DECISIONS.md`, not here.
```

`Status:` uses the same vocabulary as the decision register; `Date:` is when the content
was last true, not when the file was touched. A `superseded` research doc must name what
replaced it in `Superseded-by:`.

Also create `docs/archive/` with a short `README.md` explaining the banner convention
(`> **Archived YYYY-MM-DD.** <disposition>` — rationale, not instruction) so `reorganize` has
a target directory later.

## 7. Existing stray docs

Do not move or touch any pre-existing markdown/html outside what you just scaffolded. Say:
"There are existing docs not yet covered — run `/repo-clean reorganize` to bring them in."

## 8. Run the checker

The checker exists once, in the plugin (D-015) — nothing is vendored into this home, and
nothing is installed into git. Run
`python <plugin>/skills/repo-clean/scripts/check_docs.py --root .` and fix findings until it
exits 0. There is no per-project checker add-on to write (D-022).

## 9. Coverage report

End with a short report:
- Existing `.md`/`.html` files not covered by any routing-table row.
- Any derived filename that collided with an existing file (already paused for input above,
  but restate the resolution here).
- Any dead `@` reference found in step 2.
