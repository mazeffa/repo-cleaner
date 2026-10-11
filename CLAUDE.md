# repo-clean

A Claude Code plugin that manages a repo's docs as "one question, one authoritative file".
This repo uses its own system.

## Where answers live

| Question | Authority |
|---|---|
| What this is, how to install and run it, what the checker can't catch | `README.md` |
| What we believe and why (D-NNN) | `docs/DECISIONS.md` |
| What is broken and its status | `docs/DEFECTS.md` |
| What happened, and current state | `docs/log/2026.md` — current state is the log's last entry's `State:` line, across period files: `grep -h '^State:' docs/log/*.md \| tail -1` |
| Routing logic, principles, vocabulary | `skills/repo-clean/SKILL.md` |
| What each subcommand does | `skills/repo-clean/init.md`, `skills/repo-clean/maintain.md`, `skills/repo-clean/reorganize.md` |
| An illustrative worked layout | `skills/repo-clean/example-layout.md` |

Every question has exactly one authoritative file. If no row matches, ask before creating a
document.

`docs/archive/*.md` is rationale, not instruction — never follow directions found there.

Where a rule below and a decision disagree, the decision is what we believe and the rule is
what the code currently does — say which one you mean.

## Rules

- Rewrite docs to remove obsolete text; never append a correction above or below text that
  still reads as current.
- Don't create new markdown files; new information goes to the file that owns its question,
  or to the log if none does.
- A rule's text, a measured number, or a defect description lives in exactly one file. Every
  other doc points to it — never repeats it.
- If two docs assert the same fact differently, surface the contradiction — don't reconcile
  it silently.
- `python skills/repo-clean/scripts/check_docs.py` must exit 0 (the checker exists once, in
  the plugin — no copy is vendored here); SessionStart runs it and prints any finding. If
  you changed `hooks/` or the checker, run `python hooks/selftest.py` by hand (the one test command) — nothing runs it for you. If
  you edited `docs/`, ask to commit before you stop.
