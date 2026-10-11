# repo-clean

A Claude Code plugin that keeps a project's docs from rotting: one question, one
authoritative file, tracked in a CLAUDE.md routing table, a `D-NNN` decision
register, an append-only work log, and a stdlib checker. One session
hook prints the last log entry, what's open, and any checker finding at session start;
`/repo-clean maintain` writes a session's work into the docs when asked. Nothing touches git.

This is the USAP data team's internal fork, developed on GitHub and deployed from Azure
DevOps. It is not published and has no external users; the rule set answers to this team's
work rather than the general case. See `docs/DECISIONS.md` D-011 for why, and its
`Status: active` entries for the current design.

## Install

### Development (GitHub)

```
/plugin marketplace add https://github.com/mazeffa/repo-cleaner
/plugin install repo-clean@repo-clean
```

Updates: `/plugin marketplace update repo-clean` then `/plugin update repo-clean`. These pull
only a pushed commit whose `plugin.json` version was bumped.

### Production (Azure DevOps, at deploy)

Clone the repo, then point Claude Code at your local copy:

```
git clone https://usap-edw.visualstudio.com/Data_Science/_git/repo-clean
/plugin marketplace add <path to your clone>
/plugin install repo-clean@repo-clean
```

Picking up a change is `git pull` in the clone, then
`/plugin marketplace update repo-clean` and `/plugin update repo-clean` — and only
if `plugin.json`'s version was bumped, since the install cache is keyed on it.

Distribution today is each person pulling. Group policy will push it later; until
then, the version the plugin reports at session start is how you tell a stale
install from a current one.

## Use

```
/repo-clean init             # scaffold the doc system in a repo that doesn't have one
/repo-clean maintain         # log this session's work into the docs, then check
/repo-clean maintain --check # the same analysis, read-only: report and change nothing
/repo-clean reorganize       # migrate an existing messy docs tree into the system
```

See `skills/repo-clean/SKILL.md` for the routing logic and principles, and
`skills/repo-clean/example-layout.md` for an illustrative worked example.

## What the checker does not tell you

The checker verifies **shape**, not **content**. Exit 0 means your docs are
well-formed — it does not mean they are right. Specifically, it cannot tell:

- whether a fact was written to the file that actually owns it;
- whether two docs (or a doc and the code) state the same fact in different
  words — it checks structure, not meaning, so paraphrased duplication and
  restated code constants both pass;
- whether a doc's claims are still true, beyond what a stale `Date:` hints at;
- whether a script or data path named in a doc still exists: `paths-exist` checks only
  `.md` paths (D-027(5)), so a decision naming a deleted `.py` or `.R` file passes;
- whether an archive banner cites a real path or a research doc carries `Status:`/`Date:` —
  both conventions stay, but nothing enforces them (D-027(7)).

Those need reading, which is what `maintain --check` step 6 is for. Treat a
green run as "nothing is malformed", not "the docs are correct" — a checker
that looks more authoritative than it is does more harm than no checker.

## What gets installed into your repo

Only the doc files themselves and an empty `.repo-clean` marker. The checker exists once, in
the plugin (D-015) — no copy is vendored into your repo — and the hook runs the one shipped
with the same plugin version as themselves. Nothing is installed into git: no commit hook,
no `core.hooksPath`, no `.gitignore` (D-027(1)). A project set up by an older release may still
have `scripts/hooks/pre-commit`; it is no longer used, and you can delete it and run
`git config --unset core.hooksPath`.

You can also run the checker directly, without a session, from wherever the plugin cache
put it (`--root`, its default and the exit codes: `skills/repo-clean/SKILL.md`, "Checker"):

```
python <plugin-cache>/skills/repo-clean/scripts/check_docs.py --root DIR
```

This repo's own commands use its working-tree copy directly:

```
python skills/repo-clean/scripts/check_docs.py
python hooks/selftest.py
```

## This repo uses its own system

See `CLAUDE.md` for the routing table, `docs/DECISIONS.md` for what was decided
and why, and `docs/log/` for what happened.
