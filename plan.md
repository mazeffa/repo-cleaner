# 0.9.1: make fold-in complete, the hooks unable to wedge, and remove dead surface

## Context
A second three-model review of 0.9.0 (committed as `80ef634`) found these problems:
- Fold-in can quietly read only the start of a long session.
- Fold-in drops the user's answers to questions and plan feedback.
- Fold-in re-reads work it already folded.
- Fold-in makes Claude copy long decimal numbers into `done`.
- A slow or crashed checker blocks the user.
- Records can be lost to a crash mid-write.
- Opening a project can run that project's Python.
- reorganize's rollback can erase other projects' uncommitted work.

You chose to stop running project code (both the self-check copy and add-on files) and to drop the
old pre-marker layout. Everything below is one release, 0.9.1.

## 1. Fold-in: three commands, nothing to copy (`hooks/fold.py`, `hooks/_lib.py`)
- **New command shape:** `list HOME`, `read HOME [--from N]`, `done HOME`. Claude only ever
  passes the home path.
- **`list`**
  - Prints the waiting sessions.
  - Saves each record's current `last_stop` as `listed_stop`.
  - Writes `<home key>/folding.json` holding `{session: CLAUDE_CODE_SESSION_ID, at: now}`.
  - If that file already exists, is under 1 hour old and belongs to another session, `list`
    prints "another window is folding in this home since HH:MM (Central)" and exits 1.
- **`read`**
  - Reads every listed session in order, oldest first, under a header line per session.
  - Prints only transcript entries newer than that record's `folded_stop`, using each
    entry's `timestamp`. This stops facts being folded twice.
  - Keeps today's output (user words, Claude words, edited paths) and adds the text of
    `tool_result` blocks whose `tool_use` was `AskUserQuestion` or `ExitPlanMode`, as
    `[user answer]`. I confirmed that shape in this session's transcript.
  - Pages at about 20,000 characters. A page that stops early ends with
    `-- more: items N..M of T; run: python "<fold.py>" read "<home>" --from N`.
  - A transcript that is gone prints "detail lost" for that session.
  - Exits 1 only if a transcript that exists yields nothing recognizable at all. A session with
    nothing new since its fold prints "nothing new".
- **`done`**
  - Copies `listed_stop` to `folded_stop` on each record that has it, and removes
    `listed_stop`.
  - Deletes `folding.json`.
  - Sets `fold_pending` on its own session, as today.
  - The `id@float` arguments and their parser go.
- **`_lib._write_json`**: write to a temporary file, then `os.replace`, so a crash can't leave a
  half-written record.
- **`maintain.md` step 1**: rewrite to the three commands.
  - Steps 1–2 become `list`, then `read` until there is no "more" line.
  - `--check` reads but never runs `done`, and doesn't run `list`'s writes. `list --check`
    skips them.

## 2. The end-of-session hook can't wedge a session (`hooks/stop.py`, `_lib.run_checker`)
- Block only when the checker exits 1, which means findings.
- A timeout or any other exit code (2 means an internal error) does not block. It leaves `dirty`
  set, so the next session start reports it.
- `run_checker` returns stderr when stdout is empty.
- Share one deadline across homes: `timeout = min(25, 27 - elapsed)`. If under 2 seconds
  remain, skip the home and leave `dirty` set.

## 3. Never run project code (supersedes part of D-015 and D-013)
- **`_lib.checker_path`**: always use the plugin's own `check_docs.py` and drop the in-project
  lookup. The `None` branches in `run_checker`/`stop.py` go too.
- **`check_docs.py`**: delete the add-on support:
  - `local_module_dir`, `load_local_module` and `run_local_check`
  - `LOCAL_STARTER`, `--init-config` and `CONFIG_VERSION`
  - their selfcheck cases (about lines 724–812, plus the cases near 960–1270)
- Grep `init.md`, `SKILL.md` and `README.md` for `check_docs_local` and `--init-config` and
  remove those mentions.
- **This repo:** CLAUDE.md's rule to run `python skills/repo-clean/scripts/check_docs.py` by hand
  stays. The hooks here will use the installed plugin's checker.

## 4. Drop the old layout (supersedes D-018(c))
- **`_lib.find_home`**: returns just the path, and only `.repo-clean` counts. Update the
  callers in `fold.py`, `stop.py`, `post_tool_use.py` and `session_start.py`.
- **`find_homes_nearby`**: drop the `docs/log` glob.
- **Delete:**
  - `migrate_already_offered` and the migrate hint in `session_start.py`
  - `init.md` step 0 (`--migrate`)
  - `--migrate` from `SKILL.md`'s description and `argument-hint`
- **`check_docs._is_home`**: the marker only.
- **The checker with no `--root`:** walk up from the current folder to the nearest marker
  instead of using the git top folder.
  - Exit 2 with "no repo-clean home at or above X" when there is none. A typo can no longer pass
    with nothing checked.
  - Delete `git_root` and its selfcheck.

## 5. reorganize rollback limited to its own files (`skills/repo-clean/reorganize.md`)
- Step 7 becomes `git restore -- <each path it moved or rewrote>`, plus deleting the new
  `docs/archive/` copies it names.
- Drop `git reset --hard` from steps 6 and 7.

## 6. Wording that no longer matches the code
- **`post_tool_use.py` docstring and `SKILL.md:103`**: it marks the home as touched and docs
  as changed. It does not record which file.
- **`SKILL.md:129`**: the new `--root` default.
- **`.claude-plugin/plugin.json` description**: "fold earlier sessions into it" instead of
  "maintain it during work". Bump the version to 0.9.1 here and in `marketplace.json`.
- **`fold.py` docstring**: "never prints tool output". Claude's own words may still quote a
  result, so it should not claim "or query results".

## 7. Self-test (`hooks/selftest.py`) and checker selfcheck
- **Update:**
  - the fold-in sequence moves to `list`/`read`/`done HOME`
  - the `find_home` tests move to marker-only
  - remove the legacy and migrate checks
  - the no-home checker test expects exit 2
- **Add:**
  - `read` includes an AskUserQuestion answer.
  - `read --from` pages and prints a "more" line on a long fake transcript.
  - After `done` and a new Stop, `read` prints only the new entries.
  - A second `list` from another session ID within the hour exits 1.
  - A checker that exits 2 does not block Stop and leaves `dirty` set.
  - A record write survives as valid JSON. A plain read-back is enough.

## 8. Docs (one place each)
- **`docs/DECISIONS.md`**:
  - New D-022: never run project code. It supersedes D-015's working-copy clause and D-013's
    add-on allowance, with both sides set symmetrically.
  - New D-023: marker only. It supersedes D-018(c).
- **`docs/DEFECTS.md`**: one fixed entry per real bug, in the `Was:` form:
  - long-session truncation
  - dropped answers
  - double fold
  - wedging checker
  - torn record
  - reorganize reset
  - green on no home
- **`docs/log/2026.md`**: one entry.
  - Its `State:` corrects the stale "not committed" line. 0.9.0 is commit `80ef634`; 0.9.1 is
    built, not committed.
- **`CLAUDE.md`**: change "release 0.9.0" to 0.9.1.

## Not doing
- **Dropping the edit hook** in favor of scanning the transcript at Stop: that reads megabytes
  every turn.
- **Recording only sessions with edits:** D-021(5) records every session on purpose.
- **Including subagent side chains:** Claude relays agent results in its own words.
- **Pruning old records.**
- **Merging the two field parsers.**
- **Shrinking the rest of the checker.**

## Verification
- `python hooks/selftest.py` → `selftest ok`.
- `python skills/repo-clean/scripts/check_docs.py` → exit 0. Run from a folder with no marker
  above it → exit 2.
- `python skills/repo-clean/scripts/check_docs.py --selfcheck` passes.
- By hand, in a scratch `REPO_CLEAN_HOME`, against this session's real transcript:
  - `fold.py list`, then `read` until there is no "more" line; confirm the question answers
    appear.
  - `done`, a Stop, then `list` shows 0.
- Ask before committing.
