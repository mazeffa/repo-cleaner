# Debate: Plan to bring repo-clean to 9+/10 on robustness, elegance and simplicity

**Created:** 2026-10-10
**Agent 1:** Opus
**Agent 2:** Fable
**Agent 3:** Sonnet
**Agent 4:** Muse Spark 1.2
**Max Rounds:** 2
**Status:** OPEN

## Context

repo-clean is a Claude Code plugin (this repo, release 0.9.0, commit `34afc13`) that keeps a
project's docs authoritative so Claude can resume work. D-017 is the measure: someone opens a
project untouched for months and is working within a minute from what the SessionStart hook
prints (the log's last `State:`/`Next:`). Pieces: three hooks (`hooks/session_start.py`,
`hooks/post_tool_use.py`, `hooks/stop.py`, wired in `hooks/hooks.json`), a fold-in helper
(`hooks/fold.py`) Claude runs per `skills/repo-clean/maintain.md`, shared code in
`hooks/_lib.py`, and a stdlib checker `skills/repo-clean/scripts/check_docs.py` (1353 lines:
~930 checker + ~420 embedded `--selfcheck` fixture, 10 rules).

An LLM council (kimi-k3, deepseek-v4.1-flash, glm-5.3, muse-spark-1.2; chairman fable-5.1)
graded 0.9.0: **Robustness 4/10, Elegance 5/10, Simplicity 4/10**. A separate, earlier
three-model review produced `plan.md` (release 0.9.1, not yet implemented). This debate merges
both into one plan whose target is 9+/10 on every axis.

### Evidence

Council claims, checked against the code by Agent 1 before this debate:

| # | Claim | Verified? | Evidence |
|---|---|---|---|
| C1 | Missing checker is recorded as "clean" | TRUE | `hooks/stop.py:40` `if not result or result[0] == 0: rec["dirty"] = False`; `run_checker` returns `None` when `checker_path` finds nothing (`hooks/_lib.py:151-155`) |
| C2 | Checker timeout blocks Stop as a finding | TRUE | `hooks/_lib.py:162` returns `(1, "checker timed out")`; stop.py blocks on any nonzero |
| C3 | Bash-made doc edits (sed, heredoc, scripts) never set `dirty` | TRUE | PostToolUse matcher is `Edit\|Write\|MultiEdit\|NotebookEdit` only (`hooks/hooks.json`) |
| C4 | Stop/PostToolUse are silent when no Python is found; `python3` probed first (Windows Store alias risk) | TRUE | `hooks/hooks.json:10,23,35` — only SessionStart echoes; the others `exit 0` |
| C5 | DEF-33: `fold.py done` needs `CLAUDE_CODE_SESSION_ID` to mark its own session folded | TRUE | `hooks/fold.py:92-97`, consumed at `hooks/stop.py:36` |
| C6 | Log `State:`/`Next:` parsed by two engines | TRUE | `hooks/_lib.py:169-196` (`_field_span`, `last_field`) vs `check_docs.py:126` `parse_fields` / `:160` `split_entries` |
| C7 | Concurrent windows corrupt each other's session records | **FALSE as stated** | each session writes its own `<home key>/<session>.json`; the real race is `fold.py done` (session X) vs session Y's own Stop, worst case a re-fold. Non-atomic `write_text` (`_lib.py:58-60`) is still real |
| C8 | `core_digest` causes CRLF mismatch → exit 2 | **FALSE** | `core_digest` (`check_docs.py:68`) is only printed by `--version`, never compared |
| C9 | State/Next should print before the checker runs | **ALREADY DONE** | `session_start.py` flushes before `run_checker` |
| C10 | Home paths hash inconsistently | **MOSTLY FALSE** | `_home_dir` (`_lib.py:47`) normalizes before hashing, so one home → one folder |

Found by Agent 1 while preparing this debate (not in the council's input):

- **E1 — the installed plugin is 0.5.0, not 0.8.0.** `~/.claude/plugins/installed_plugins.json`
  → `repo-clean@repo-clean` `version: 0.5.0`, installed from marketplace source
  `github: mazeffa/repo-cleaner` (`known_marketplaces.json`, last updated 2026-09-19). This
  repo is 0.9.0. The log's current `State:` line says "the plugin cache is still 0.8.0" —
  wrong. README says the Azure DevOps clone is the install source — the owner's own machine
  does not match.
- **E2 — README claims something no hook does.** README "Install": "the version the plugin
  reports at session start is how you tell a stale install from a current one."
  `hooks/session_start.py` (0.9.0) prints no version. A stale install is therefore invisible.
- **E3 — suppression comments are unused.** `<!-- check-docs: ignore ... -->` and
  `<!-- no-route -->`: 0 uses in this repo's living docs.
- **E4 — the security issue.** `_lib.checker_path` (`_lib.py:140`) prefers
  `<home>/skills/repo-clean/scripts/check_docs.py` if it exists, so opening a project runs
  that project's Python. `plan.md` §3 removes this.

Added by Agent 1 after a second pass over the code [A1-R1]:

- **E5 — the two log parsers already disagree.** `_lib.last_field` (`_lib.py:182-193`) reads raw
  lines, so a `State:` line inside a fenced code block in the log counts. The checker reads
  through `read_doc` (`check_docs.py:106-123`), which blanks fences, so it does not. Also,
  `parse_fields` (`check_docs.py:137`) splits `State: a  Next: b` written on one line into two
  fields. `_lib.NEXT_RE = ^Next:` (`_lib.py:40`) only matches at column 0, so SessionStart
  prints the whole line as State and no Next. Same log, different answers: this is a
  correctness bug, not just a style point, and it backs P6. [A1-R1]
- **E6 — Stop's missing-Python branch can't happen alone.** All three prologues run the same
  probe (`python3 -c pass`, then `python -c pass`) in the same environment
  (`hooks/hooks.json:10,23,35`). If Stop finds no Python, SessionStart found none either and
  already echoed `repo-clean: no python3/python found on PATH; hooks disabled`. So C4's
  "silent" risk amounts to the probe order alone. [A1-R1]
- **E7 — suppression is an escape hatch for wedge-by-repetition.** When the checker exits
  nonzero, `rec["dirty"]` stays True (`stop.py:40-44`). `stop_hook_active` only stops the
  *second* block in a turn (`stop.py:31`), so a rule that misfires in a user's repo blocks
  once on every turn until the doc is "fixed". `check-docs: ignore <rule>`
  (`check_docs.py:183,190`, used at `:341,455,474,497,663,683`) is the only way out that
  leaves the doc's content alone. E3 counts uses in *this* repo only, not the ~30 users'
  repos. [A1-R1]

Agent 2's independent verification of the above [A2-R1]:

- C1 verified: `_lib.py:153-155` returns `None` when `checker_path` is `None`; `stop.py:40`
  treats `None` as clean. C2 verified: `_lib.py:161-162`, `stop.py:40-44`. C3 verified:
  `hooks.json:18`. C4 verified: `hooks.json:23,35` `else exit 0`. C6 verified at the lines
  cited. C7 verified: `save_session` (`_lib.py:67-69`) writes `<home key>/<session_id>.json`;
  only `fold.py done` (`fold.py:87-98`) writes another session's record. [A2-R1]
- E5 verified by code trace (executing a reproduction script was refused by a permission
  prompt this round, so this is a trace, not a run): `STATE_RE = ^State:\s*(.*)$`
  (`_lib.py:39`) matched against raw `splitlines()` output (`_lib.py:188-190`), with `found`
  overwritten on every match (`:192`), so a fenced `State: fenced` after the real one is what
  SessionStart prints. `NEXT_RE` (`_lib.py:40`) never matches `State: a  Next: b`, so no
  `Next:` prints; `parse_fields` (`check_docs.py:137,151-155`) returns `{State: "a", Next:
  "b"}` for the same body. Same log, two answers. [A2-R1]
- E6 verified: the three probe strings at `hooks.json:10,23,35` are byte-identical up to the
  `else` branch. E7 verified: `stop.py:31` and `:38-44`; `line_ignored` callers at the six
  lines cited. [A2-R1]
- E1 **not verified**: reading `known_marketplaces.json` and `installed_plugins.json` was
  refused by a permission prompt for Agent 2 too (both via Read and via `cat`). Agent 3 must
  read them or P2's stale-install half stays unshipped. [A2-R1]
- **E8 — `--version` has no caller.** `grep -rn -- --version` across the living docs: only
  `skills/repo-clean/SKILL.md:130` (describes the flag). `maintain.md` does not call it;
  `docs/DEFECTS.md:245` records that step 7 "hashes both checkers directly, so it also works"
  without `--version`. The remaining hits are history (`DEFECTS.md:239-240`,
  `docs/log/2026.md:205-243`). Supports P7 going further (delete the flag). [A2-R1]
- **E9 — `exec` in P1 changes exit-code pass-through for two hooks.** Today SessionStart and
  PostToolUse end in `; exit 0` (`hooks.json:10,23`), Stop does not (`:35`). With `exec $py`
  all three pass the Python exit code through. A traceback in `session_start.py` or
  `post_tool_use.py` then exits 1, which Claude Code treats as non-blocking and shows on
  stderr, instead of exiting 0 silently. More visible, never blocking: acceptable, but P1
  should say so. [A2-R1]
- **E10 — the 10 rules.** `GENERIC_RULES` (`check_docs.py:696-707`): decisions-integrity,
  log-fields-resolve, outside-repo-paths, paths-exist, banned-headers, diary-grammar,
  archive-banner-paths, open-questions-sync, routing-coverage, research-fields. `banned-headers`
  bans only `^#+.*\bNext Steps\b` (`CONFIG["banned_header_re"]`, `check_docs.py:94`). [A2-R1]

### plan.md summary (0.9.1, already agreed with the owner)

§1 fold-in becomes `list HOME` / `read HOME [--from N]` / `done HOME`; `read` pages at ~20k
chars, prints only entries newer than `folded_stop`, adds AskUserQuestion/ExitPlanMode answers;
`list` writes a `folding.json` lock (owner = `CLAUDE_CODE_SESSION_ID`, 1 h); `_write_json`
becomes temp-file + `os.replace`. §2 Stop blocks only on checker exit 1; timeout/exit 2 leave
`dirty` set; shared deadline across homes. §3 never run project code: checker always from the
plugin; delete `check_docs_local.py` support, `--init-config`, `CONFIG_VERSION`. §4 marker-only
homes; delete legacy layout + migrate hint; checker with no `--root` walks up to a marker and
exits 2 if none. §5 reorganize rollback uses `git restore -- <paths>`, no `git reset --hard`.
§6 wording fixes, version bump. §7 selftest cases. §8 D-022 (never run project code), D-023
(marker only), DEFECTS entries, log entry.
**plan.md "Not doing":** dropping the edit hook, recording only sessions with edits, subagent
side chains, pruning old records, **merging the two field parsers**, **shrinking the rest of
the checker**.

### Relevant Files
- `hooks/_lib.py` — registry, `find_home`, `run_checker`, `last_field`
- `hooks/stop.py`, `hooks/session_start.py`, `hooks/post_tool_use.py`, `hooks/hooks.json`
- `hooks/fold.py`, `hooks/selftest.py` (389 lines, run by hand)
- `skills/repo-clean/scripts/check_docs.py`
- `skills/repo-clean/maintain.md`, `skills/repo-clean/reorganize.md`
- `plan.md`, `docs/DECISIONS.md` (D-013, D-015, D-017, D-018, D-021), `README.md`

### Constraints
- Stdlib Python only. No PowerShell anywhere (D-021(10)). Windows 11 + Git Bash; ~30 users.
- The tool never commits, stages, stashes or changes git settings (D-021(1)).
- D-017 is the test for every rule: it stays only if breaking it would make the model
  hallucinate or redo work.
- Plugin install cache is keyed on `plugin.json` version; an un-bumped version = stale hooks.
- One question, one authoritative file; no new markdown files without a routing-table row.
- **Agent 4 (Muse) cannot read the repo** — it sees only this file. Its role is critic and
  rubric grader: attack the design, score each axis each round. Any code claim it makes must be
  verified by Agent 1–3 before it is accepted.

---

## Assumptions

- [A1-R1] Assumption: the 9/10 bar can be made checkable (Success Criteria below), so the
  debate argues about tests, not taste. Basis: each council deduction maps to a specific
  mechanism (C1–C6, E1–E4).
- [A1-R1] Assumption: two releases are acceptable — 0.9.1 (correctness/robustness, plan.md plus
  additions) and 0.10.0 (simplification/elegance, needs a new D-NNN because it reverses plan.md's
  "Not doing" items). Basis: plan.md is already agreed; mixing deletions into it raises risk.
- [A1-R1] Assumption: hooks may import from `check_docs.py` (same plugin, same version,
  `PLUGIN_ROOT/skills/repo-clean/scripts`). Basis: `_lib.PLUGIN_ROOT` already resolves it
  (`_lib.py:19`); after plan.md §3 no project copy is ever used.
- [A1-R1] Basis checked: importing `check_docs` has no side effects. Lines 60-191 define only
  constants, `CONFIG`, compiled regexes and functions; `main` sits behind `__main__`. One
  correction: `PLUGIN_ROOT` is at `_lib.py:20`, not `:19`. If the import fails (e.g. a
  half-updated cache), SessionStart must still print something: it catches the ImportError
  and prints `repo-clean: checker import failed: <error>`. That degrades to "no State shown",
  which is no worse than today when the log is missing.
- [A2-R1] Verified the whole module, not just lines 60-191: top level of `check_docs.py:55-812`
  is imports, constants, `CONFIG`, functions, `class Ctx` (`:194`), `GENERIC_RULES` (`:696`),
  `LOCAL_STARTER` (`:780`, a string); the only call at import time is none — `main` is invoked
  solely under `if __name__ == "__main__"` (last two lines of the file). Safe to import.
  After plan.md §3 and P7, the `hashlib`, `importlib.util` and `subprocess` imports
  (`:56-57,60`) have no user left; delete them in the same change, not as a separate cleanup.
- [A1-R1] Assumption: for a local-path marketplace, `known_marketplaces.json[...].installLocation`
  is the user's clone, so `git pull` updates its `plugin.json` while the cache stays old.
  Basis: README install flow; **not verified on a team machine** — the owner's machine uses a
  GitHub source (E1).
- [A1-R1] Re-check: reading `known_marketplaces.json` this round was refused by a permission
  prompt, so E1 and this assumption rest on Agent 1's earlier read alone. Agent 2 or 3 should
  re-read both plugin JSON files before P2's stale-install half is accepted. The file format is
  undocumented third-party behaviour, so P2 must skip silently on any read or key error
  (guardrail: degrade to "same as before").
- [A2-R1] Refused for Agent 2 as well (Read and `cat`, both prompts). Still unverified; passes
  to Agent 3. Until then P2 ships the version line only.
- [A1-R1] Assumption: the 30-day transcript retention and transcript JSONL shape are stable
  enough that `fold.py read` exiting nonzero is rare. Basis: D-021(2); selftest covers today's
  shape only.
- [A1-R1] Assumption (new): no user repo relies on `<!-- no-route -->`. Basis: the code marks it
  `# deprecated; routing-coverage only, still honored` (`check_docs.py:182`), and
  `check-docs: ignore routing-coverage` does the same job (`check_docs.py:663`). Unverified
  across the ~30 users' repos. Fallback: if someone still uses it, that doc gets one
  routing-coverage finding with an obvious fix (change the comment).
- [A1-R1] Assumption (new): a Stop-time checker run triggered by mtime (P3) is cheap enough for
  the 30 s Stop budget. Basis: `run_checker` already gives it 25 s (`_lib.py:159`) and it
  already runs on every SessionStart. Stat-ing `CLAUDE.md`, `README.md` and `docs/**/*.md`
  adds one directory walk.
- [A2-R1] Assumption (new, for P3): file mtime is fine enough to order "checker ran" before
  "doc edited". Basis: NTFS stores 100 ns; FAT/exFAT and some network shares store 2 s.
  Fallback: `dirty` from PostToolUse stays, so an Edit-tool change is caught regardless of
  mtime granularity. A Bash edit on a coarse-mtime volume within 2 s of the checker run is
  missed, which is today's behaviour for every Bash edit — no worse.

---

## Success Criteria

Robustness (target 9+):
- [ ] ~~Every failure path is visible at the next SessionStart and none wedges Stop —
  `python hooks/selftest.py` has one case each for: no Python on PATH, checker exit 2,
  checker timeout, corrupt session JSON, unreadable transcript, expired transcript, stale
  install version → each prints a `repo-clean:` line at SessionStart; Stop exits 2 only for
  checker exit 1 → `selftest ok`~~ [A1-R1]
- [ ] [A1-R1] Every failure path shows up at the next SessionStart and none wedges Stop.
  `python hooks/selftest.py` → `selftest ok`, with one case each for:
  (a) `hooks/run.sh session_start` with PATH holding no Python → prints `repo-clean: no Python 3.8+ found`;
  (b) checker exit 2 → Stop exits 0, `dirty` still True;
  (c) checker timeout → Stop exits 0, `dirty` still True;
  (d) corrupt session JSON → hooks exit 0;
  (e) unreadable transcript → `fold.py read` prints `[session <id>: unreadable` and goes on;
  (f) every listed transcript expired → `read` exits 1;
  (g) a plugin.json version mismatch in a fake `known_marketplaces.json` → SessionStart prints `repo-clean: installed`.
  Stop exits 2 only when the checker exits 1.
- [ ] [A2-R1] Case (a) is only passable if `run.sh` calls no external command: with PATH
  stripped, `$(dirname "$0")` in P1's sketch fails (`dirname` is `/usr/bin/dirname` in Git
  Bash, not a builtin). See the P1 correction. Case (d) already holds today
  (`_lib._read_json`, `_lib.py:51-55`, returns `{}` on any exception); keep it as a regression
  case.
- [ ] No project code runs — `grep -n "base in (root" hooks/_lib.py` → no hits
- [ ] Records are written atomically — `grep -n "write_text" hooks/_lib.py` → only on a temp path followed by `os.replace`
- [ ] A doc edited via Bash is checked by Stop — selftest case: `.md` changed with no PostToolUse event → Stop runs the checker
- [ ] [A1-R1] No regression from P3. Selftest case: a session that edits nothing, in a home
  whose docs are older than its SessionStart → Stop does not run the checker.
- [ ] [A2-R1] No regression from P3, second case: a record that has neither `checked_at` nor
  `dirty` (a home reached from above by editing a non-`.md` file, `_lib.add_file`
  `_lib.py:84-88`) → Stop does not run the checker. In the Bash-edit case, seed `checked_at`
  10 s in the past before writing the file so mtime granularity can't flake the test.
- [ ] SessionStart prints the running plugin version — selftest asserts the line

Elegance (target 9+):
- [ ] One log-field parser — `grep -n "_field_span\|FIELD_START_RE" hooks/` → no hits
- [ ] [A1-R1] The parsers agree (E5). Selftest case: a log whose last entry has a `State:` inside a
  ``` fence plus `State: a  Next: b` on one line → SessionStart prints `State: a` and
  `Next: b`, the same values `check_docs.parse_fields` returns.
- [ ] ~~One writer of `folded_stop` — `grep -n "folded_stop\s*=" hooks/*.py` → only `fold.py`~~ [A1-R1]
- [ ] [A1-R1] Struck: no proposal item implements it, and it conflicts with DEF-33.
  `stop.py:36-37` (`if rec.pop("fold_pending"): rec["folded_stop"] = rec["last_stop"]`) has to
  be in Stop: the folding session's own last Stop comes after `fold.py done` runs, so `done`
  can't know its timestamp. Replacement criterion: `grep -n "folding.json" hooks/` → no hits
  (P5: no lock).
- [ ] One home predicate — `find_home`, `find_homes_nearby`, `check_docs._is_home` all test only `.repo-clean`
- [ ] One hook prologue — `hooks/hooks.json` commands each call one shared `hooks/run.sh <hook>`

Simplicity (target 9+):
- [ ] ~~`check_docs.py` checker code (excluding the selfcheck fixture) ≤ 600 lines — `wc -l` after moving the fixture~~ [A1-R1]
- [ ] [A1-R1] Struck: 600 is a guess that would force rule deletions to hit a number. Arithmetic:
  ~930 checker lines, minus the local-module code (`check_docs.py:724-807`, ~85), minus
  `CORE_VERSION`/`core_digest` (`:64-79`, ~16), minus `NO_ROUTE_MARKER` handling (~8),
  leaves ~820. Getting to 600 means cutting about four rules whatever P10 concludes.
  Replacement: every top-level function in `check_docs.py` has a caller (P8/P9 leave no dead
  code), and the line count after P7–P10 is recorded in the log entry, not used as a gate.
- [ ] ~~No unused surface — `grep -n "SUPPRESS_RE\|core_digest\|CONFIG_VERSION\|load_local_module\|NO_ROUTE_MARKER" skills/repo-clean/scripts/check_docs.py` → no hits~~ [A1-R1]
- [ ] [A1-R1] No unused surface: `grep -n "core_digest\|CORE_VERSION\|CONFIG_VERSION\|load_local_module\|NO_ROUTE_MARKER" skills/repo-clean/scripts/check_docs.py` → no hits. `SUPPRESS_RE` stays (E7).
- [ ] [A2-R1] Add `git_root\|--version\|--selfcheck\|--init-config` to that grep (plan.md §3/§4
  delete `git_root` and `--init-config`; P7 as revised deletes `--version`; P9 deletes
  `--selfcheck`). Also `grep -rn -- "--selfcheck\|--version\|--init-config" README.md
  skills/` → no hits, so the docs stop describing flags that no longer exist (today:
  `README.md:76,84`, `SKILL.md:123,130`).
- [ ] Each surviving checker rule has a one-line D-017 justification in the new D-NNN
- [ ] ~~`python skills/repo-clean/scripts/check_docs.py` → exit 0; `--selfcheck` → ok~~ [A2-R1]
- [ ] [A2-R1] `python skills/repo-clean/scripts/check_docs.py` → exit 0. The `--selfcheck` half
  is struck because P9 (accepted below) deletes the flag; its fixture runs inside
  `python hooks/selftest.py → selftest ok`, already listed under Robustness.

Independent re-grade:
- [ ] The council (same four models, tier high) re-grades the converged plan → each axis ≥ 9. (Subjective; recorded, not a blocker if every criterion above passes.)

---

## Proposal

STATUS: OPEN

### Release 0.9.1 = plan.md §1–8, plus these additions [A1-R1]

**P1. One hook prologue; never silent without Python** [A1-R1]
Now: three copy-pasted bash prologues (`hooks/hooks.json:10,23,35`) probe `python3` then
`python`; Stop and PostToolUse exit 0 silently if neither works.
~~Should: one `hooks/run.sh <hook>` probing `py -3`, then `python`, then `python3`, each with
`-c 'import sys; sys.exit(sys.version_info < (3, 8))'`. On failure every hook writes the UTC
time to `$HOME/.claude/repo-clean/python-missing`; the SessionStart branch also echoes it. When
Python is found, `session_start.py` prints and deletes that marker if present.~~ [A1-R1]
Should (revised after E6) [A1-R1]: one `hooks/run.sh <hook>` probes `py -3`, then `python`,
then `python3`, each with `-c 'import sys; sys.exit(sys.version_info < (3, 8))'`, and
`exec`s the first that passes, so the exit code (Stop's 2) passes through. If none passes, it
prints `repo-clean: no Python 3.8+ found on PATH; hooks disabled` only for `session_start`
and exits 0. Dropped the `python-missing` marker file: SessionStart runs the same probe in the
same environment, so it already reports the failure (E6). The marker would cover only "Python
present at SessionStart, gone by Stop", which has never been seen (guardrail: unobserved edge
case). Sketch:
```bash
#!/usr/bin/env bash
for py in "py -3" python python3; do
  if $py -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
    exec $py "$(dirname "$0")/$1.py"
  fi
done
[ "$1" = session_start ] && echo 'repo-clean: no Python 3.8+ found on PATH; hooks disabled'
exit 0
```
`hooks.json` commands become `bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" stop` (etc.).
[A2-R1] Accepted, with one correction and one note. Correction: the `exec` line must read
`exec $py "${0%/*}/$1.py"`; `dirname` is an external binary, so the sketch as written cannot
pass Success Criterion (a), which strips PATH, and in real use it would print the "no Python"
line whenever `/usr/bin` is missing from PATH even though Python was found. `${0%/*}`, `[`
and `echo` are bash builtins. Note (E9): with `exec`, SessionStart and PostToolUse lose
today's trailing `; exit 0` (`hooks.json:10,23`), so a Python traceback in either exits 1
instead of 0. Claude Code does not block on exit 1; it shows stderr. That makes a broken
hook visible rather than silent, which is the robustness this debate wants, so no guard is
added back. Verified the probe handles the Store alias already: `python3 -c pass` against the
Windows Store stub exits nonzero, so today's `if` falls through to `python` (`hooks.json:10`);
P1 only changes the order and adds the 3.8 floor.

**P2. SessionStart prints the running version and flags a stale install** [A1-R1]
Now: no version printed (E2); owner's machine runs 0.5.0 unnoticed (E1).
Should: first line `repo-clean <version from PLUGIN_ROOT/.claude-plugin/plugin.json>`. Then,
if `~/.claude/plugins/known_marketplaces.json` has a `repo-clean` entry whose `installLocation`
holds a `plugin.json` with a different version, print
`repo-clean: installed <a>, your clone has <b> — run /plugin marketplace update repo-clean and /plugin update repo-clean`.
Stdlib JSON read, no network. Any read error → skip silently (it is a hint, not a gate).
[A1-R1] Order matters for D-017: the version line comes *after* `State:`/`Next:`, not first, so
the resume information stays at the top of the hook output. The stale-install comparison can
ship only if Agent 2/3 confirm the `known_marketplaces.json` keys (see Assumptions). Without
that, ship the version line alone: it fixes E2 by itself and makes README's claim true.
[A2-R1] Accepted as split. The version line is one `json.loads` of
`PLUGIN_ROOT / ".claude-plugin" / "plugin.json"` (`PLUGIN_ROOT` at `_lib.py:20`; the file
exists with `"version": "0.9.0"`), wrapped in the same try/except-print-nothing shape as
`_read_json`. The stale-install half stays out of 0.9.1 unless Agent 3 reads the two plugin
JSON files this round and pastes the keys; Agent 2 could not (Assumptions). If it does ship,
it is one more `_read_json` plus one `!=`, nothing else.

**P3. Doc edits made outside Edit/Write still get checked** [A1-R1]
Now: `dirty` is set only by PostToolUse (C3).
Should: Stop also runs the checker for a touched home when the newest mtime among
`CLAUDE.md`, `README.md` and `docs/**/*.md` is later than `rec["checked_at"]` (set after
every checker run). PostToolUse stays — it is how a session opened above several homes is
credited to the right one (D-021(5)).
[A1-R1] Missing piece: a new session's record has no `checked_at`, so on the first Stop
every doc is "newer" and Stop runs the checker. It would then block on findings that existed
before the session (`stop.py:26-29` counts the opened-in home as touched even with no
edits). Fix: `session_start.py` writes `checked_at = time.time()` into this session's record
right after its own `run_checker` call (`session_start.py:64`), and only if the key is
absent, so resume/compact don't reset the baseline. This doesn't put the session on the
un-folded list: `unfolded_sessions` needs `last_stop > folded_stop` (`_lib.py:100`), and a
record with no `last_stop` reads 0 > 0, which is false. Known effect: if a `git pull` during
the session changes a doc, Stop checks it too. That's a real finding in this home, and
`stop_hook_active` still stops a second block in the same turn.
[A2-R1] Verified `_lib.py:100` (`rec.get("last_stop", 0) > rec.get("folded_stop", 0)`) and
`stop.py:24-29`. Accepted with one addition: the seed only covers the home SessionStart
found (`session_start.py:31`); a home reached from above gets its record from
`post_tool_use` → `add_file` (`_lib.py:84-88`), which never writes `checked_at`. For that
record Agent 1's rule reads "every doc is newer" again and the first Stop blocks on
pre-session findings. Rule, final form:
`run = rec.get("dirty") or ("checked_at" in rec and newest_mtime(home) > rec["checked_at"])`.
A record with no `checked_at` degrades to today's `dirty`-only behaviour. Second known
effect, stated so nobody is surprised: SessionStart now writes a record for the opened-in
home, so a session opened in home A that edits only inside a nested home B is recorded in
both (today: B only, `stop.py:24`). A's fold-in then reads a transcript about B. Nested
homes are the D-018 "homes below" case and rare; accepting it beats a second mechanism.

**P4. An unreadable or expired transcript can't nag forever** [A1-R1]
Now: `read` exits 1 → maintain.md says stop → `done` never runs → the session is listed at
every startup.
Should: in plan.md §1's multi-session `read`, an unreadable session prints
`[session <id>: unreadable — record detail lost]` and `read` continues; exit 1 only when every
listed session is unreadable. `done` covers all listed sessions; the log entry records which
lost detail.
[A1-R1] Evidence that today's code dead-ends: `fold.py:100-103` (transcript missing) and
`:106-109` ("recognized nothing … stop and tell the user") both `return 1` for the single
transcript being read, with no way to go on.
[A2-R1] Verified `fold.py:100-109`: both branches `return 1` before any item prints
(`:110-111`). Accepted; plan.md §1 already lists "A transcript that is gone prints 'detail
lost'" and "exits 1 only if a transcript that exists yields nothing", so P4 is a one-clause
tightening of that text (unreadable, not only gone), not new design.

**P5. The `folding.json` lock must not depend on DEF-33's env var** [A1-R1]
Now (plan.md §1): lock owner = `CLAUDE_CODE_SESSION_ID`. Without it, owner is empty and "belongs
to another session" is undecidable.
~~Should: owner = `CLAUDE_CODE_SESSION_ID` or, if unset, no lock is written and `list` prints
one line saying concurrent fold-ins are not detected. Open question for the debate: is the lock
worth having at all? Two windows folding at once produce two log entries, which the checker's
"State: only on the last entry" rule already flags.~~ [A1-R1]
Should (revised; answers my own open question) [A1-R1]: **drop the lock from plan.md §1.**
A concurrent fold-in is already detected and costs little:
(1) Two log entries both carrying `State:` trip the existing rule at `check_docs.py:578`
("only the last entry holds current state; delete it"), and Stop blocks the second window
until the entries are merged.
(2) The only registry race is `done` against another session's Stop (C7), and its worst case
is one session listed again for a re-fold. Once `_write_json` uses `os.replace` there is no
torn record.
Dropping the lock removes `folding.json`, the owner check, the 1 h expiry, and P5's dependency
on DEF-33.
[A2-R1] Accepted. Verified (1): `check_docs.py:573-579` loops over `all_entries[:-1]` and
reports any earlier entry whose `State`/`Next` is non-empty; the folding window's own Edit
of the log sets `dirty` (`_lib.py:86-87`), so its Stop runs the checker and blocks (exit 1).
Verified (2): plan.md §1's `listed_stop → folded_stop` copy in `done` is idempotent, so two
windows running `list`/`done` in any interleaving leave `folded_stop` at a value each saw;
a Stop between them only makes `last_stop` newer, which re-lists correctly. Also removes
plan.md §7's "second `list` from another session ID within the hour exits 1" test case.

### Release 0.10.0 = simplification, under a new D-024 [A1-R1]

**P6. One log parser.** Delete `_lib._field_span`, `last_field`, `last_state_line`,
`STATE_RE`, `NEXT_RE`, `FIELD_START_RE` (`_lib.py:39-41,166-197`). `session_start.py` imports
`check_docs.parse_fields`/`split_entries` from `PLUGIN_ROOT` and prints the last entry's
`State:`/`Next:`. Reverses plan.md "Not doing: merging the two field parsers".
[A1-R1] Moved from "elegance" to "correctness" by E5: the two parsers give different answers
for fenced and same-line fields today. Because of that, I'd consider moving P6 into 0.9.1;
I'm leaving it in 0.10.0 for now because it reverses an agreed plan.md item. To use the
checker's real entry heading regex and `read_doc`, `session_start.py` should call one new
function `check_docs.current_fields(root) -> dict`, the same code the `diary-grammar` last-entry
check uses at `check_docs.py:572`. It should not re-do the entry splitting itself.
[A2-R1] Accepted; E5 verified by trace above. `current_fields` is the loop at
`check_docs.py:558-569` (`read_doc` → `split_entries(text, LOG_HEADING_RE)` → last entry →
`parse_fields(body)`) lifted into one function that `check_diary_grammar` then calls too, so
the checker and SessionStart cannot drift again. Net: ~32 lines deleted from `_lib.py`, one
~10-line function added to `check_docs.py`, one import plus a try/except in
`session_start.py`. Vote on the parking-lot question: move P6 into 0.9.1. It is the smallest
correctness fix on this list and the import path it needs is the one P2 and P9 use anyway;
the owner's "Not doing" was written before E5 showed the parsers return different values.

**P7. One version number.** Delete `CORE_VERSION`, `core_digest` (`check_docs.py:64-79`);
`--version` prints `plugin.json`'s version. With P2 in place, the digest guards nothing.
~~`--version` prints `plugin.json`'s version.~~ [A2-R1]
[A2-R1] Delete `--version` outright (parser line `check_docs.py:857`, branch `:879-881`,
`SKILL.md:130`). E8: nothing calls it; `maintain.md` step 7 hashes the checkers directly
(`DEFECTS.md:245`). Re-pointing it at `plugin.json` would add a `parents[3]` path lookup to
the checker to serve a flag with no caller, while P2 already prints the same number where
people see it. Smaller diff, one version printed in one place.

**P8. Delete unused surface.** ~~`SUPPRESS_RE`, `line_ignored`, `NO_ROUTE_MARKER`
(`check_docs.py:182-191`; E3: zero uses) and their selfcheck cases.~~ [A1-R1]
[A1-R1] Revised: delete only `NO_ROUTE_MARKER` (`check_docs.py:182,661,668`) and its selfcheck
cases. The code itself marks it "deprecated", and `check-docs: ignore routing-coverage` does
the same job. Keep `SUPPRESS_RE`/`line_ignored`: E3 measured this repo, not users' repos.
Without it, a rule that misfires blocks Stop once per turn in that repo with no way out
except editing true content (E7).
[A2-R1] Accepted. Verified the three `NO_ROUTE_MARKER` sites (`:182` definition, `:661`
skip, `:668` message text) and that `:663` keeps routing-coverage suppressible without it.
E7 verified at `stop.py:31,38-44`.

**P9. Move the selfcheck fixture out of the checker** into `hooks/selftest.py` (which already
drives everything else), leaving `--selfcheck` as a thin call or deleting it.
[A1-R1] Pick one: delete `--selfcheck`. CLAUDE.md already tells contributors to run
`python hooks/selftest.py` by hand. Two entry points for one test suite is the duplication
this debate is trying to remove. Update the Success Criteria line that runs `--selfcheck`
when this is accepted.
[A2-R1] Accepted (Success Criteria updated above). One condition so the move pays for itself:
`selftest.py` imports `check_docs` through the same `PLUGIN_ROOT/skills/repo-clean/scripts`
path `session_start.py` uses under P2/P6, so the suite exercises the one import path the
hooks depend on. `selftest.py` already has `sys.path.insert(0, HOOKS_DIR)`
(`selftest.py:21`); this is one more insert. The fixture's local-module cases
(`check_docs.py:1114-1270`, `load_local_module` at `:1123,1177,1247,1267`) are deleted by
plan.md §3 before the move, so what moves is smaller than today's ~420 lines. Also delete
`README.md:76,84` and `SKILL.md:123`, which tell users to run `--selfcheck`.

**P10. Re-justify every rule under D-017.** Each of the 10 rules gets one line in D-024 naming
the hallucination or redone work it prevents; a rule with no such line is deleted. Agent 1's
first pass — keep: `diary-grammar`, `decisions-integrity`, `log-fields-resolve`,
`routing-coverage`, `paths-exist`, `outside-repo-paths` (scoped per D-016(a)); unsure:
`open-questions-sync`, `research-fields`, `archive-banner-paths`, `banned-headers`.
[A2-R1] Move `banned-headers` to keep. It bans exactly one thing, a `Next Steps` header
(`check_docs.py:94`, E10): a doc carrying its own "Next Steps" is a second `Next:` that
competes with the log's, and the model resuming per D-017 may follow the stale one. That is
the redo-work case in one line. The other three stay "unsure" from me too: I read each
(`:582-601`, `:604-619`, `:671-693`) and can describe what they check, but have no incident
where their absence caused a hallucination, so by P10's own rule the line in D-024 is the
owner's to write or the rule goes. No evidence either way; not for this debate to invent.

**P11. Keep, contrary to the council:** `setup_already_offered`/`offered.json` (without it every
non-home folder nags every session) and the "homes below" listing.
[A2-R1] Verified: `session_start.py:41-42` prints the setup offer for any cwd with no home
and no homes below, gated only by `setup_already_offered` (`_lib.py:203-211`). Keep.

### Fix the docs now [A1-R1]
The log's current `State:` line says the cache is 0.8.0; it is 0.5.0 (E1). Fold this into the
0.9.1 log entry.
[A1-R1] Confirmed the wrong line is live: this session's SessionStart output printed
"State: 0.9.0 built with the review fixes, not committed or pushed … the plugin cache is still
0.8.0 and runs its old hooks here". Whether the cache really holds 0.5.0 still depends on E1's
earlier read (see Assumptions).
[A2-R1] This session's SessionStart printed a different, already-corrected line: "State: 0.9.0
is committed as `34afc13`; the installed plugin is still 0.5.0." So the log was edited since
Agent 1's turn (git status shows `docs/log/2026.md` modified, uncommitted). The remaining
work here is to commit that log change with the 0.9.1 entry, and E1's 0.5.0 figure still
rests on Agent 1's earlier read.

---

## Plan

PLAN_STATUS: PENDING

### Changes

| # | File | What to change | Why |
|---|------|----------------|-----|
| | | | |

### Order of Operations
1. {step}

### Verification
{Maps back to Success Criteria.}

---

## Parking Lot

- [A1-R1] `.council/logs/` was written into this repo by the council MCP server; decide whether to gitignore it.
- [A1-R1] Marketplace source on the owner's machine is GitHub `mazeffa/repo-cleaner`, not the Azure DevOps clone README describes — decide which is canonical.
- [A1-R1] `python-missing` marker (dropped from P1). Defensive — no evidence that Python goes missing between SessionStart and Stop. Defer unless observed.
- [A1-R1] Move P6 into 0.9.1 because of E5. Needs the owner's call, since plan.md says "Not doing: merging the two field parsers".
- [A2-R1] `</dev/null` on the `run.sh` probe so a probe can never drain the hook's stdin JSON. `python -c` does not read stdin; no evidence this occurs. Defer unless observed.
- [A2-R1] Replacing `dirty` entirely with the P3 mtime test (one mechanism instead of two). Blocked by the coarse-mtime assumption above; keep both until a flaky `dirty` is observed.
- [A2-R1] `debates/` is untracked in this repo and has no routing-table row in CLAUDE.md; decide whether it is committed and routed, or gitignored like `.council/logs/`.

---

## Dispute Log

| Round | Agent | Section | What Changed | Why | Status |
|-------|-------|---------|--------------|-----|--------|
| R1 | Opus | P1 | Dropped `python-missing` marker; `run.sh` `exec`s so Stop's exit 2 passes through | E6: SessionStart runs the same probe and already reports it (`hooks.json:10`); marker covered an unobserved case | CLOSED |
| R1 | Opus | P3 | SessionStart seeds `checked_at` if absent | Without it the first Stop of every session runs the checker and blocks on findings that predate the session (`stop.py:26-29`) | CLOSED |
| R1 | Opus | P5 | Drop the `folding.json` lock entirely | Concurrent fold-ins already caught by `check_docs.py:578`; registry race worst case is a re-fold (C7) | CLOSED |
| R1 | Opus | P8 | Keep `SUPPRESS_RE`; delete only `NO_ROUTE_MARKER` | E7: suppression is the only exit from per-turn Stop blocks on a misfiring rule; E3 measured only this repo | CLOSED |
| R1 | Opus | P6 | Added E5 (parsers disagree on fenced and same-line fields); `session_start` calls one `check_docs.current_fields` | Correctness bug today, not just elegance (`_lib.py:40,182-193` vs `check_docs.py:106-123,137`) | CLOSED |
| R1 | Opus | Success Criteria | Struck "one writer of `folded_stop`" and "≤ 600 lines"; listed the robustness cases; added P3/P6 regression cases | `stop.py:36-37` is needed for DEF-33; 600 would force ~4 rule deletions (~820 lines after P7–P9 cuts) | CLOSED |
| R1 | Opus | P9 | Pick: delete `--selfcheck`, `hooks/selftest.py` is the one suite | Two entry points for one suite | CLOSED |
| R1 | Opus | Assumptions | `known_marketplaces.json` re-read refused this round; P2's stale-install half needs another agent's confirmation | Evidence rule: unverified third-party format | OPEN |
| R1 | Fable | Context | Verified C1–C7, E5 (by trace), E6, E7 at the cited lines; closed the seven Opus rows above on that basis (A3/A4 may reopen any with evidence) | Guardrail: accepting requires independent verification; evidence inline under "Agent 2's independent verification" | CLOSED |
| R1 | Fable | Context | Added E8 (`--version` has no caller), E9 (`exec` drops `; exit 0` on SessionStart/PostToolUse), E10 (the 10 rules; `banned-headers` = `Next Steps` only) | grep across living docs; `hooks.json:10,23,35`; `check_docs.py:94,696-707` | OPEN |
| R1 | Fable | Assumptions | Both plugin JSON reads refused for Agent 2 too; E1 and P2's stale-install half pass to Agent 3 | Still unverified | OPEN |
| R1 | Fable | P1 / Success Criteria (a) | `exec $py "${0%/*}/$1.py"` instead of `$(dirname "$0")` | `dirname` is external in Git Bash; criterion (a) strips PATH, so the sketch as written fails its own test | OPEN |
| R1 | Fable | P3 | Missing `checked_at` → `dirty` only, no mtime test; second regression case added to Success Criteria; nested-home double-record effect stated | Homes reached from above get records from `add_file` (`_lib.py:84-88`) with no `checked_at`; Opus's rule would block their first Stop on pre-session findings | OPEN |
| R1 | Fable | P7 | Delete `--version` instead of re-pointing it at `plugin.json` | E8: no caller; P2 prints the version where it is read | OPEN |
| R1 | Fable | P9 | Accept, plus: `selftest.py` imports `check_docs` via the same `PLUGIN_ROOT` path the hooks use; delete `README.md:76,84`, `SKILL.md:123` | One import path, exercised by the suite; docs stop describing a deleted flag | OPEN |
| R1 | Fable | Success Criteria | Struck `--selfcheck → ok`; widened the no-unused-surface grep to `git_root`, `--version`, `--selfcheck`, `--init-config` and the docs | P9/P7/plan.md §3–4 delete them | OPEN |
| R1 | Fable | P10 | `banned-headers` → keep | `check_docs.py:94`: a `Next Steps` header is a second `Next:` the resuming model may follow | OPEN |
| R1 | Fable | Fix the docs now | The live `State:` already says 0.5.0 (uncommitted edit to `docs/log/2026.md`) | This session's SessionStart output; `git status` | OPEN |

**Status values:** `OPEN` = unresolved, needs further debate. `CLOSED` = all agents agree (accepted, conceded, or resolved). `PARKED` = deferred, not blocking convergence.
