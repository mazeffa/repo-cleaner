# maintain

Session-end routine: route what changed to the file that owns it, then gate on the checker.

## 0. Refuse on an unmerged tree

If the repo is mid-rebase or mid-merge (`git status` shows unmerged paths), stop and say so
— `git diff`/`git log` are misleading in that state. Staged and unstaged changes otherwise
are fine; there's no need for a clean tree here.

## 1. Collect changed facts

- `git diff` (working tree + staged) for what changed.
- `git log` since the date of the log's last entry, capped at 30 days (use whichever is more
  recent/smaller). If the gap is large, that's not a maintain-sized job — say "run
  `/repo-clean reorganize`" instead and stop.

## 2. Route each fact via the table, to exactly one owner

For each change, ask "what kind of fact is this?":

- **Belief change** (a decision made, reversed, or confirmed) → a new `D-NNN` entry. If it
  reverses or replaces an earlier entry, set `Superseded-by`/`Supersedes` symmetrically on
  both, and update the Open-questions table if either entry's `Status: open` state changed.
- **Event** (something happened: a run, a fix, a result) → an entry in the current log
  period file.
- **Evidence** (new measurement, new research) → the subject's research doc, in place.
- **Correction to something already documented** → rewrite in place. Never append a
  correction above or below text that still reads as current.

Every fact goes to exactly one file. If two docs already assert the same fact differently,
report the contradiction — do not silently pick one and reconcile it.

## 3. No owner row?

If a fact doesn't match any routing-table row, don't invent a file for it. Collect all such
"no owner" questions from this session and ask the user once, in one batched prompt, rather
than interrupting per-item.

## 4. Append the log entry

Add a new `## YYYY-MM-DD [(N)] — headline` entry (see `example-layout.md` for the grammar)
with `Decisions:` and `Docs:` fields. Move the `State:` line: remove it from the previous
last entry (if present) and add it, updated, to this new entry — it is a one-line summary of
what's true now and what's pending.

"Where does this go?" asked mid-session is this same routing step, answered in words instead
of applied to a file.

## 5. Run the checker

`python scripts/tools/check_docs.py` (or the repo's install path). Fix findings until it
exits 0. Do not end the session, or claim the docs are in order, without having run it.
