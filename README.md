# repo-clean

A Claude Code plugin that keeps a repo's docs from rotting: one question, one
authoritative file, tracked in a CLAUDE.md routing table, a `D-NNN` decision
register, an append-only work log, and a stdlib checker gated by a git
pre-commit hook.

## Install

```
/plugin marketplace add C:\claude\repo-clean
/plugin install repo-clean@repo-clean
```

## Use

```
/repo-clean init         # scaffold the doc system in a repo that doesn't have one
/repo-clean maintain      # session-end routine: route changed facts to their owner file
/repo-clean reorganize    # migrate an existing messy docs tree into the system
/repo-clean audit         # read-only report: what's unrouted, stale, or duplicated
```

See `skills/repo-clean/SKILL.md` for the routing logic and principles, and
`skills/repo-clean/example-layout.md` for a worked example pulled from a real
repo using this system.

## What gets installed into your repo

`init` (or `maintain`/`reorganize` afterward) copies `scripts/check_docs.py`
to `scripts/tools/check_docs.py` and `scripts/pre-commit` to
`scripts/hooks/pre-commit`, then runs `git config core.hooksPath scripts/hooks`.
Re-syncing the checker core later is `cp <skill>/scripts/check_docs.py
scripts/tools/check_docs.py` — it never touches your `check_docs_local.py`.
