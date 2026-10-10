# repo-clean 0.10.0 — one release: every known fix plus the cleanup

## Context

repo-clean is the plugin that keeps each project's docs current so Claude can pick a project
back up cold. Its whole value rests on one thing: when a session starts, the tool prints the
project's current state and next step from the log. An LLM council scored the current release
(0.9.0) 4/10 for robustness, 5/10 for elegance and 4/10 for simplicity. Two agent debates
then checked every complaint against the code and agreed what to change
(`debates/2-2026-10-10-repo-clean-plan-opus-sonnet.md`). The council reviewed the resulting
plan and its fixes are folded in here.

Earlier drafts split this into two releases. That split had no technical reason, would have
meant editing the same files twice, and could not reach the 9/10 goal. This is one release.

Term used below: **fold-in** = Claude reading the transcripts of earlier sessions and writing
what happened into the project's docs (one log entry, plus any decisions).

## What a user will notice

- Session start shows the plugin version under the project's state, so an out-of-date install
  is visible (this machine ran a months-old version unnoticed).
- The doc check runs when docs change by any means. Today it only runs when Claude edits a doc
  with its edit tool, so a doc changed by a script or command is never checked at the end of
  a turn.
- If the checker crashes or runs out of time, the session is not blocked over it. The problem
  is printed at the next session start instead. Today a timeout blocks as if the docs were
  wrong, and a missing checker is recorded as "docs are fine".
- Session start and the checker read the log the same way. Today they can disagree about
  what the current state is.
- Fold-in reads every earlier session to the end (today it can read only the start of a long
  one), keeps your answers to Claude's questions, never re-reads what it already wrote up, and
  can't be marked finished after reading only part of the material.
- If no Python is found, every hook says so instead of silently doing nothing.
- Opening a project never runs code that lives inside that project.
- `reorganize`'s undo only puts back the files it moved itself. Today it runs
  `git reset --hard`, which can wipe unrelated uncommitted work.
- Pointing the checker at a folder that isn't a project is an error, not a silent pass.
- Removed: per-project checker add-on files, the old pre-marker project layout, and the
  `--selfcheck`, `--version` and `--init-config` flags. Two checker rules (archive banner
  paths, research-doc Status/Date) are dropped as not worth enforcing (see step 7).

## Judgment calls made (owner asked me to choose)

1. **An earlier session whose transcript is deleted or unreadable** is written into the docs
   as "this session happened; its details were lost", and the tool stops asking about it. A
   garbled transcript won't fix itself, and asking at every start teaches people to ignore
   the prompt.
2. **When the doc check can't work out whether docs changed** (an internal error), it runs
   the check anyway rather than skipping it.
3. **Two windows writing up the same project at once:** no lock file. The checker already
   catches the result: two log entries that both claim to be current.
4. **The `banned-headers` rule** follows the written decision (D-016(c): a "Next Steps"
   heading is invalid everywhere). Its code currently skips `DECISIONS.md`; that skip goes.
   This repo has no such heading, so nothing here starts failing.
5. **Kept, despite the council:** the `<!-- check-docs: ignore RULE -->` comment (the only
   way out of a rule that misfires, short of rewriting true content), `maintain --check`
   (an existing decision, D-004), the one-time "not set up here" notice, and the "projects
   below" line for sessions opened above several projects.

## Build order (tests run after every step)

### Step 0 — Record the plan in the repo
Replace `plan.md` with this plan.

### Step 1 — Checker: remove what the hooks would otherwise have to work around
File: `skills/repo-clean/scripts/check_docs.py`
- Delete the per-project add-on support: `local_module_dir`, `load_local_module`,
  `run_local_check`, `LOCAL_STARTER`, the `--init-config` flag, `CONFIG_VERSION`.
- Delete `git_root`. With no `--root`, walk up from the current folder to the nearest
  `.repo-clean` marker; none found → print "no repo-clean home at or above X" and exit 2.
  `--root` given but not a project → exit 2 too (today exit 0).
- `_is_home`: the marker only.
- Delete `CORE_VERSION`, `core_digest` and the `--version` flag (nothing calls it; the version
  is printed at session start from `plugin.json`).
- Delete `NO_ROUTE_MARKER` (deprecated; the `check-docs: ignore routing-coverage` comment
  does the same job). Keep `SUPPRESS_RE`/`line_ignored`.
- Delete `hashlib`, `importlib.util`, `subprocess` imports once unused.
- Update the module docstring (rule list, suppression layers, no add-on file).

### Step 2 — Shared hook code
File: `hooks/_lib.py`
- One module-level `sys.path.insert(0, str(PLUGIN_ROOT / "skills" / "repo-clean" /
  "scripts"))` beside `PLUGIN_ROOT`, outside any `try`, so every hook can `import check_docs`.
- `checker_path`: always the plugin's own checker (delete the "project's own copy" branch).
- `run_checker(root, timeout=25)` always returns `(code, text)`: missing checker →
  `(2, "checker not found: <path>")`; timeout → `(124, "checker timed out")`; empty stdout →
  stderr.
- `_write_json`: write a temp file in the same folder, then `os.replace` (no half-written
  records after a crash).
- `find_home(cwd)` returns just the path; only the marker counts. `find_homes_nearby` drops the
  `docs/log` glob. Delete `migrate_already_offered`.
- `add_file`: when the record has no `checked_at`, set it to now (so a project reached from a
  parent folder also gets the "changed by any means" check from its first edit on).
- Delete the hooks' own log parser: `_field_span`, `last_field`, `last_state_line`,
  `STATE_RE`, `NEXT_RE`, `FIELD_START_RE`.

### Step 3 — End-of-turn check (Stop)
File: `hooks/stop.py`
- New `newest_mtime(home)`: newest modification time across
  `check_docs.docs_plus_log(check_docs.Ctx(home, dict(check_docs.CONFIG)))` (reuses the
  checker's own definition of "a doc", which includes the log). Any error → `float("inf")`
  (run the check).
- Replace the check block (`stop.py:38-44`) with one block:
  - run when `dirty`, or when `checked_at` exists and `newest_mtime(home) > checked_at`;
  - only if not already continuing because of this hook, and at least 2 s remain of a 27 s
    budget taken from the top of `main` (Stop's hook timeout is 30 s);
  - take `started = time.time()` before the run;
  - exit 0 → clear `dirty`, `checked_at = started`;
  - exit 1 → block with the findings;
  - 2 or 124 → no block; `dirty` and `checked_at` stay, so it is retried.
- Update `find_home` callers for the new return shape.

### Step 4 — Session start
Files: `hooks/session_start.py`, `skills/repo-clean/scripts/check_docs.py`
- New `check_docs.current_fields(root) -> dict`: the last-entry loop already inside
  `check_diary_grammar` (`read_doc` → `split_entries(text, LOG_HEADING_RE)` over each period
  file → last entry → `parse_fields`), lifted out. `check_diary_grammar` calls it too.
- `session_start.py` prints `State:`/`Next:` from `current_fields`. If the import fails, it
  prints `repo-clean: checker import failed: <error>` and continues.
- Then prints `repo-clean <version>` from `PLUGIN_ROOT/.claude-plugin/plugin.json`; on a read
  error, `repo-clean: version unknown (<error>)`.
- Before its own checker run, write `checked_at = now` into this session's record for the home,
  only if absent, using `session_id` from the hook input. So problems that already existed are
  shown at start, not used to block this session's turns.
- Delete the migrate hint and the legacy-home branch.

### Step 5 — Hook launcher
Files: new `hooks/run.sh`, `hooks/hooks.json`
- `run.sh <hook> <plugin root>`: try `py -3`, then `python`, then `python3`, each checked with
  `-c 'import sys; sys.exit(sys.version_info < (3, 8))'`. `exec` the first that works on
  `"$2/hooks/$1.py"`. If none works, print "repo-clean: no Python 3.8+ found on PATH; hooks
  disabled" (stdout for session_start, stderr for the other two) and exit 0. Bash builtins
  only.
- `hooks.json`: each of the three commands becomes
  `bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" <hook> "${CLAUDE_PLUGIN_ROOT}"`. Timeouts unchanged.

### Step 6 — Fold-in
Files: `hooks/fold.py`, `skills/repo-clean/maintain.md`
- Commands become `list HOME`, `read HOME [--from N]`, `done HOME`; Claude only passes the
  project folder.
- `list`: prints the waiting sessions; saves each record's `last_stop` as `listed_stop`.
- `read`: every listed session, oldest first, each under a header line.
  - Only transcript entries newer than the record's `folded_stop` (none recorded → all).
    An entry with no `timestamp` counts as new.
  - Keeps today's content (user words, Claude words, edited paths, via `extract`). Adds
    answers to `AskUserQuestion`/`ExitPlanMode` as `[user answer]`.
  - Pages at ~20,000 characters, ending a partial page with the exact `--from N` command.
  - A gone or unreadable transcript prints `[session <id>: … — detail lost]` and goes on.
  - Sets `read_complete` on a session's record once its last item is printed. Exits 1 only
    if every listed session is gone or unreadable.
- `done`: refuses, naming the sessions, unless every listed session has `read_complete`.
  Then copies `listed_stop` → `folded_stop`, removes the staging fields, and flags its own
  session (`CLAUDE_CODE_SESSION_ID`) as today. Drop the `id@float` arguments.
- `maintain.md` steps 1 and 7: the three commands; `read` until no "more" line; the log entry
  names sessions whose detail was lost; `--check` reads but never runs `done`, and `list`
  writes nothing under `--check`.

### Step 7 — Checker rules: banned-headers fix and the two dropped rules
File: `skills/repo-clean/scripts/check_docs.py`
- `check_banned_headers`: delete the `DECISIONS.md` skip (`:492,494-495`); docstring
  "anywhere".
- Delete `check_archive_banner_paths`, `BANNER_WORDS`, `check_research_fields`, the
  `research_dir` config key (check `Ctx.archive_dir` for other users before deleting it).
  Keep `"research"` in `routing_exempt_topdirs`.
- The test that decided this (agreed in debate 2): a rule stays if breaking it leaves a doc
  Claude trusts saying something false or ambiguous. A bad archive banner path or a missing
  research `Date:` doesn't do that, and neither rule ever caught a real problem. The research
  `Status:`/`Date:` convention stays, unenforced.

### Step 8 — One test suite
Files: `hooks/selftest.py`, `skills/repo-clean/scripts/check_docs.py`
- Move `_selfcheck`'s fixture into `selftest.py` as `test_checker_rules()`. It imports
  `check_docs` through the `_lib` path insert, the same path the hooks use. It drops the cases
  for removed features (add-on file, `git_root`, digest, `--selfcheck` parsing, banner and
  research rules) and adds "a Next Steps heading in `docs/DECISIONS.md` is a finding". Delete
  `--selfcheck` and `_selfcheck` from the checker.
- Update existing tests:
  - fold-in moves to `list`/`read HOME`/`done HOME`;
  - `find_home` returns a path; the marker only;
  - remove the legacy and migrate checks;
  - the no-home checker test expects exit 2;
  - `test_stop_broken_checker` and `test_plugin_core` now expect "no block" (the hooks never
    run a project's copy).
- New tests. Hooks run as separate processes, so a fake checker is a stub `check_docs.py`
  in a `make_scratch_repo` copy, and `run_hook` gains an optional `hooks_dir`. For the
  "changed by any means" cases, age every fixture file 60 s, set `checked_at` 30 s back,
  then change one file with `Path.write_text`. "Check did not run" cases use
  `make_home(..., broken=True)` and expect exit 0. The cases:
  - **Launcher (`run.sh`).** No Python on PATH: session_start prints the line on stdout,
    stop prints it on stderr, both exit 0. Find `bash` with `shutil.which` first.
  - **Stop with a failing checker.**
    - A stub that exits 2: Stop exits 0; `dirty` and `checked_at` are unchanged.
    - A timeout (patch `_lib.subprocess.run` in process, restore in `finally`):
      `run_checker` returns 124.
    - At session start, a 2 or a 124 is printed.
  - **Stop when docs change outside the edit tool.**
    - A broken home, README rewritten: Stop exits 2, and exits 2 again on the next turn.
    - A second `State:` written into the log: Stop exits 2.
    - A routed file outside `docs/`: in that test, add a routing row and `guide/init.md`
      before aging, then break the file. Stop exits 2.
    - In each of these, after a clean run, assert that `checked_at` moved.
  - **Stop when nothing changed.**
    - Docs older than the session, no edit: exit 0.
    - A record with neither `checked_at` nor `dirty`: exit 0.
  - **A project reached from a parent folder.** A non-doc edit, then a doc changed by
    command: Stop exits 2.
  - **The checker can't be imported.** A stub that raises `ImportError` on import:
    - a doc changed by command: the check still runs, and Stop exits 2;
    - session start prints "checker import failed".
  - **Records.** A corrupt record: hooks exit 0. A record write leaves valid JSON.
  - **Fold-in.**
    - One unreadable transcript among several: `read` continues. All unreadable: exit 1.
    - A question answer appears. `--from` pages.
    - After `done` and a new Stop, `read` shows only the new entries.
    - An entry with no timestamp is shown.
    - `done` after a partial read refuses; after the full read, it succeeds.
  - **Session start.**
    - A log with a fenced `State:` and `State: a  Next: b` on one line prints `State: a`
      and `Next: b`, then a `repo-clean \d+\.\d+\.\d+` line.

### Step 9 — Wording, version, and records
- `hooks/post_tool_use.py`, `hooks/fold.py` docstrings; `skills/repo-clean/SKILL.md`:
  - remove `--migrate` from the description and `argument-hint`;
  - Hooks section: the launcher, the version line, checking docs changed by any means;
  - Checker section: drop the removed flags; describe the new `--root` default.
- `skills/repo-clean/init.md`: delete step 0 (`--migrate`) and the `check_docs_local.py`
  advice.
- `skills/repo-clean/reorganize.md` steps 6–7: undo only what it recorded in step 1:
  `git restore -- <each source it moved or rewrote>` (keeps staged work), then delete each
  destination it created including the new `docs/archive/` copies, and on any failure print
  the remaining commands. Remove `git reset --hard` everywhere.
- `README.md`:
  - remove the `--selfcheck`/`--init-config` lines;
  - "What the checker does not tell you": add "a doc changed by another window or a `git pull`
    mid-session is checked at your next turn's end and blocks once per turn until fixed";
  - "a session opened in one project that edits only a nested project is recorded in both";
  - archive banners and research `Status:`/`Date:` are no longer checked.
- `.claude-plugin/plugin.json`: version 0.10.0; description "fold earlier sessions into it"
  instead of "maintain it during work". `marketplace.json` unchanged except if it carries a
  version (it doesn't).
- `docs/DECISIONS.md`, in this repo's style (a new entry restates and supersedes; links both
  ways):
  - D-022 "Never run project code": supersedes D-013. It restates D-013 without the
    `check_docs_local.py` allowance, and says restoring the tool's own edits during
    `reorganize` is not one of the git actions D-021(1) rules out.
  - D-023 "Marker only": supersedes D-018, restating (a)/(b) without (c).
  - D-024 "Checker rule set": supersedes D-005. It states the keep/drop test once, with one
    line per kept rule (8 rules).
  - D-017's rule list becomes a pointer to D-024.
  - Mark D-005, D-013 and D-018 `superseded` with `Superseded-by`.
- `docs/DEFECTS.md`: a "Fixed in 0.10.0" section with one `Was:`/`Fix:` entry per bug fixed:
  - long sessions read partially;
  - question answers dropped;
  - sessions written up twice;
  - fold-in stuck on one unreadable transcript;
  - `done` after a partial read;
  - a checker failure recorded as clean;
  - a timeout or internal error blocking the session;
  - docs changed by command never checked;
  - the two log readers disagreeing;
  - no version shown (README's claim false);
  - half-written records;
  - reorganize's `git reset --hard`;
  - a pass when there is no project;
  - `banned-headers` skipping `DECISIONS.md`;
  - opening a project running its code.
- `docs/log/2026.md`: one entry for this release. Its `State:` says built, not committed, and
  the installed version.
- `CLAUDE.md`: "release 0.9.0" → 0.10.0. Remove the sentence about the checker's built-in
  self-test, and point to `python hooks/selftest.py` as the one test command.

## Verification

1. `python hooks/selftest.py` → `selftest ok` (run after every step; at the end, with every
   case above).
2. `python skills/repo-clean/scripts/check_docs.py` → exit 0 in this repo. From a folder with
   no marker above it → exit 2.
3. Each of these finds hits in the 0.9.0 files (read via `git show 34afc13:<path>`) and none
   after the change:
   - `grep -rn "_field_span\|FIELD_START_RE\|STATE_RE\|NEXT_RE" hooks/`
   - `grep -n "base in (root\|migrate\|is_legacy" hooks/*.py`
   - `grep -n "core_digest\|CORE_VERSION\|CONFIG_VERSION\|load_local_module\|NO_ROUTE_MARKER\|git_root\|_selfcheck\|init_config\|research-fields\|archive-banner-paths" skills/repo-clean/scripts/check_docs.py`
   - `grep -rn -- "--selfcheck\|--version\|--init-config\|--migrate" README.md skills/ CLAUDE.md`
   - every `hooks/hooks.json` command calls `hooks/run.sh`
4. By hand, with a scratch `REPO_CLEAN_HOME` and a real transcript from this machine:
   - `fold.py list`, then `read` until there is no "more" line; question answers appear;
   - `done`; a Stop; `list` shows nothing waiting.
5. After the owner reinstalls (`/plugin marketplace update repo-clean`,
   `/plugin update repo-clean`), the only test under the real hook runner:
   - opening this repo prints `repo-clean 0.10.0` under State/Next;
   - an edit that breaks a doc link blocks at turn end;
   - the session record shows the edit.
6. Council re-grade of the built code against the three axes.
7. Nothing is committed without the owner's yes.
