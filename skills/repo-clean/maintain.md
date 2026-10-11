# maintain

Write what this session did into the docs: route each fact to the file that owns it, bring
the work list up to date, write one log entry, then run the checker. This is the one act that
writes the log; work rows are also written as things come up (D-029(1)).

It runs when the user asks (`/repo-clean maintain`, "log this") or says the session is over.
Opened above several homes, run it once for each home the session changed, passing that
home's path below.

## Mode

`maintain` edits. `maintain --check` reports and edits nothing — same routing analysis,
no writes, no confirmation prompts. Every step below says what `--check` does differently.

## 0. Refuse on an unmerged tree

If `.git` exists and is mid-rebase or mid-merge (`git status` shows unmerged paths), stop
and say so — `git diff`/`git log` are misleading in that state. Staged and unstaged changes
otherwise are fine; there's no need for a clean tree here. No `.git` at all: skip this step.

## 0b. Upgrade an older home, once

If `docs/WORK.md` is missing, the home predates the work list (D-029(8)). With the user's
confirmation: create it from `init.md`'s skeleton; make each decision with `Status: open` a
row (keep the entry as `active` if it holds a belief, otherwise delete it) and each
`DEFECTS.md` item a `bug` row; delete `DEFECTS.md`, the register's Open-questions table
and any `Verdict:` lines (adopted: delete; never in force: `Status: rejected`); and point the
`CLAUDE.md` routing rows at `docs/WORK.md`. Give each research doc a routing row.

`--check`: list what the upgrade would change.

## 1. Collect changed facts

Work from this conversation: what the user said and decided, what Claude did, which files
were edited, and the user's answers to questions and plan prompts. Open a tool's output or a
query result only when you need one specific fact that lives there, never in bulk — query
results can hold patient data. If the conversation holds nothing beyond idle reading, write
no entry and say so.

`git diff` and `git log` may help confirm a fact, but the conversation is the record — many
homes share a repo, and git doesn't say which session did what.

`--check`: report where each fact would go (step 2); write nothing.

## 2. Route each fact via the table, to exactly one owner

For each change, ask "what kind of fact is this?":

- **Belief change** (a decision made, reversed, or confirmed) → a new `D-NNN` entry. If it
  reverses or replaces an earlier entry, set `Superseded-by`/`Supersedes` symmetrically on
  both.
- **Work** (a bug found, a step put off, an idea, an item finished or abandoned) →
  `docs/WORK.md`: a new row, or an existing row's Status and Closed date. Sweep the whole
  session for these; Claude should have added most as they came up, so this catches the rest.
- **Event** (something happened: a run, a fix, a result) → an entry in the current log
  period file.
- **Evidence** (new measurement, new research) → the subject's research doc, rewritten in
  place, with its `Status:`/`Date:` header updated.
- **Correction to something already documented** → rewrite in place (`SKILL.md` Principles).

Every fact goes to exactly one file. If two docs already assert the same fact differently,
report the contradiction — do not silently pick one and reconcile it.

`--check`: report the routing for each fact as `path — fact — suggested owner`. Write nothing.

## 3. No owner row?

If a fact doesn't match any routing-table row, don't invent a file for it. Collect all such
"no owner" questions from this session and ask the user once, in one batched prompt, rather
than interrupting per-item.

`--check`: list them as unrouted. Ask nothing.

## 4. Append the log entry

One entry per `maintain` run. Add a
`## YYYY-MM-DD [(N)] — headline` entry (grammar: `SKILL.md` Vocabulary) with
`Decisions:` and `Docs:` fields. Write where you left off as prose; never edit an earlier
entry. Anything left to do is a `docs/WORK.md` row, not a line in the entry (`SKILL.md`
Principles). When the detail is longer than an entry should hold, point to the
file that holds it.

Write to `docs/log/<current year>.md`. If that file doesn't exist yet, create it with the
same format note at the top as last year's.

"Where does this go?" asked mid-session is this same routing step, answered in words instead
of applied to a file.

`--check`: skip.

## 5. Run the checker

Run `python <plugin>/skills/repo-clean/scripts/check_docs.py --root <home>` (D-015); the
plugin's own source repo uses its working-tree copy: `python skills/repo-clean/scripts/check_docs.py`.

In write mode, fix findings until it exits 0. In `--check` mode, report them and stop.

## 6. The pass the checker can't do

The checker verifies shape (`README.md`, "What the checker does not tell you"). These need
reading, and belong in both modes — in write mode raise them with the user, in `--check`
mode just list them:

- Topics discussed in the repo (issues, comments, commit messages) with no routing-table row.
- A fact restated in 2+ living docs in different words, or a doc restating a code constant.
- A doc line stating present-tense status that changes faster than docs are written —
  commit, push or deploy status, "currently running" — instead of dating it or pointing to
  its owner (D-029(3)).
- A research doc whose `Date:` is old relative to the code it describes.
- An `open` row in `docs/WORK.md` that the work has clearly already finished.
