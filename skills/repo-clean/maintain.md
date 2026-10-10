# maintain

Fold in: read what earlier sessions did, route each fact to the file that owns it, write
one log entry, then run the checker. This is the one act that writes the docs (D-021).

It runs when the user asks (`/repo-clean maintain`, "fold in", "log this"), when the user
says the session is over, or when the session-start hook says earlier sessions are waiting.
In that last case, go ahead unless the user says not now — other windows may still be open,
and the sessions will come up again next time. Opened above several homes, fold in each
home the hook named, one at a time, passing that home's path below.

## Mode

`maintain` edits. `maintain --check` reports and edits nothing — same routing analysis,
no writes, no confirmation prompts. Every step below says what `--check` does differently.

## 0. Refuse on an unmerged tree

If `.git` exists and is mid-rebase or mid-merge (`git status` shows unmerged paths), stop
and say so — `git diff`/`git log` are misleading in that state. Staged and unstaged changes
otherwise are fine; there's no need for a clean tree here. No `.git` at all: skip this step.

## 1. Collect changed facts

`fold.py` sits in the plugin's `hooks/` folder, two levels above this skill's folder; the
session-start line prints its full path.

1. `python <plugin>/hooks/fold.py list <home>` lists the sessions not yet folded in, with
   their transcript paths. When the user says the session is over, this session is in the
   list too. It ends with the `done` line to run in step 7 — keep it.
2. For each one, `python <plugin>/hooks/fold.py read <transcript>`. It prints only what the
   user said, what Claude said, and which files were edited. Work from that. Open a tool's
   output or a query result only when you need one specific fact that lives there, never in
   bulk — query results can hold patient data.
3. If `read` says it recognized nothing, stop and tell the user; don't fold an empty
   session. If a transcript is gone (they expire, 30 days by default), record that the
   session happened and its detail was lost — never guess what it did.
4. If the sessions hold nothing beyond an earlier fold-in or idle reading, write no entry;
   go straight to step 7.

`git diff` and `git log` may help confirm a fact, but the transcripts are the record — many
homes share a repo, and git doesn't say which session did what.

`--check`: run `list` and `read` and report where each fact would go (step 2); write nothing,
and don't run `done`.

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

One entry per fold-in, however many sessions it covers. Add a
`## YYYY-MM-DD [(N)] — headline` entry (see `example-layout.md` for the grammar) with
`Decisions:` and `Docs:` fields, then `State:` (what's true now) and `Next:` (what to do
next). Remove `State:` and `Next:` from the previous last entry — only the last entry carries
them. An entry is what someone needs to resume, typically 5 to 15 lines. When the detail is
longer, `State:` may point to the file that holds it.

Write to `docs/log/<current year>.md`. If that file doesn't exist yet, create it with the
same format note at the top as last year's, and remove `State:` and `Next:` from the last
entry of last year's file.

"Where does this go?" asked mid-session is this same routing step, answered in words instead
of applied to a file.

`--check`: skip.

## 5. Run the checker

The checker exists once, in the plugin (D-015) — no copy is vendored into the home. Run
`python <plugin>/skills/repo-clean/scripts/check_docs.py --root <home>`; the plugin's own
source repo uses its working-tree copy: `python skills/repo-clean/scripts/check_docs.py`.

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

## 7. Record the fold-in

Run the `done` line that `list` printed. It marks exactly the sessions `list` showed, so a
session that stopped during the fold-in still comes up next time, and this session doesn't.
A session that keeps working afterwards comes up again. Skip in `--check` mode.
