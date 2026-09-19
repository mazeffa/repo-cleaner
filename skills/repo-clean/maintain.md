# maintain

Route what changed to the file that owns it, then run the checker.

## Mode

`maintain` edits. `maintain --check` reports and edits nothing — same routing analysis,
no writes, no confirmation prompts. Every step below says what `--check` does differently.

## 0. Refuse on an unmerged tree

If `.git` exists and is mid-rebase or mid-merge (`git status` shows unmerged paths), stop
and say so — `git diff`/`git log` are misleading in that state. Staged and unstaged changes
otherwise are fine; there's no need for a clean tree here. No `.git` at all: skip this step.

## 1. Collect changed facts

If `.git` exists:
- `git diff` (working tree + staged) for what changed.
- `git log` since the date of the log's last entry, capped at 30 days (use whichever is more
  recent/smaller). If the gap is large, that's not a maintain-sized job — say "run
  `/repo-clean reorganize`" instead and stop.

No `.git`: use the Stop hook's per-session changed-file list (see Hooks in `SKILL.md`) plus
what this conversation actually did — there's no history to diff against.

## 2. Route each fact via the table, to exactly one owner

For each change, ask "what kind of fact is this?":

- **Belief change** (a decision made, reversed, or confirmed) → a new `D-NNN` entry. If it
  reverses or replaces an earlier entry, set `Superseded-by`/`Supersedes` symmetrically on
  both, and update the Open-questions table if either entry's `Status: open` state changed.
- **Event** (something happened: a run, a fix, a result) → an entry in the current log
  period file.
- **Evidence** (new measurement, new research) → the subject's research doc, rewritten in
  place, with its `Status:`/`Date:` header updated.
- **Correction to something already documented** → rewrite in place. Never append a
  correction above or below text that still reads as current.

Every fact goes to exactly one file. If two docs already assert the same fact differently,
report the contradiction — do not silently pick one and reconcile it.

`--check`: report the routing for each fact as `path — fact — suggested owner`. Write nothing.

## 3. No owner row?

If a fact doesn't match any routing-table row, don't invent a file for it. Collect all such
"no owner" questions from this session and ask the user once, in one batched prompt, rather
than interrupting per-item.

`--check`: list them as unrouted. Ask nothing.

## 4. Append the log entry

Add a new `## YYYY-MM-DD [(N)] — headline` entry (see `example-layout.md` for the grammar)
with `Decisions:` and `Docs:` fields. Move the `State:` line: remove it from the previous
last entry (if present) and add it, updated, to this new entry — it is a one-line summary of
what's true now and what's pending.

"Where does this go?" asked mid-session is this same routing step, answered in words instead
of applied to a file.

`--check`: skip.

## 5. Run the checker

`python scripts/tools/check_docs.py` (or the repo's install path). If the plugin isn't
installed in the target repo, `python <skill>/scripts/check_docs.py --root <repo>`.

In write mode, fix findings until it exits 0. In `--check` mode, report them and stop.

## 6. The pass the checker can't do

The checker verifies shape. These need reading, and belong in both modes — in write mode
raise them with the user, in `--check` mode just list them:

- Topics discussed in the repo (issues, comments, commit messages) with no routing-table row.
- A fact restated in 2+ living docs in different words, or a doc restating a code constant.
  The checker cannot compare docs to code or to each other for meaning — only structure.
- A log's last `State:` line that looks stale against recent `git log` activity.
- A research doc whose `Date:` is old relative to the code it describes.
- An `open` decision whose `Revisit:` trigger has clearly already been met.

## 7. Checker version drift

Compare the target repo's full `--version` line (`python scripts/tools/check_docs.py
--version`), digest included, against the plugin's copy. If they differ, report "target
X, plugin Y" and print the re-sync command:
`cp <skill>/scripts/check_docs.py <repo>/scripts/tools/check_docs.py`. A target that prints
no `+digest` predates this check and counts as drift.
