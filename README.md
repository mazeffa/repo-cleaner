# repo-clean

A Claude Code plugin that keeps a repo's docs from rotting: one question, one
authoritative file, tracked in a CLAUDE.md routing table, a `D-NNN` decision
register, an append-only work log, and a stdlib checker. A Stop hook forces the
log entry and a clean checker run every session that changed files; a git
pre-commit hook is a backstop where git exists. No git required.

## Install

```
/plugin marketplace add mazeffa/repo-cleaner
/plugin install repo-clean@repo-clean
```

Pushed a change? Users pick it up with `/plugin marketplace update repo-clean`
followed by `/plugin update repo-clean` — and only if `plugin.json`'s version
was bumped, since the install cache is keyed on it.

To set it up for a whole team, commit this to `.claude/settings.json` instead;
anyone who trusts the folder gets it with no install step:

```json
{
  "extraKnownMarketplaces": {
    "repo-clean": {
      "source": { "source": "github", "repo": "mazeffa/repo-cleaner" }
    }
  },
  "enabledPlugins": { "repo-clean@repo-clean": true }
}
```

## Use

```
/repo-clean init             # scaffold the doc system in a repo that doesn't have one
/repo-clean maintain         # route changed facts to their owner file, then run the checker
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
- whether a doc's claims are still true, beyond what a stale `Date:` hints at.

Those need reading, which is what `maintain --check` step 6 is for. Treat a
green run as "nothing is malformed", not "the docs are correct" — a checker
that looks more authoritative than it is does more harm than no checker.

## What gets installed into your repo

`init` copies `skills/repo-clean/scripts/check_docs.py` to
`scripts/tools/check_docs.py` as a fallback for machines without the plugin. If
the repo has `.git`, it also copies `skills/repo-clean/scripts/pre-commit` to
`scripts/hooks/pre-commit` and runs `git config core.hooksPath scripts/hooks`.
That pre-commit — and the Stop hook — run the newest installed plugin core,
falling back to the vendored copy only when the plugin cache is absent (D-010).
`maintain`/`reorganize` never install anything. The SessionStart hook already
reports drift between the fallback copy and whatever actually runs, once per
drift state, every session; `maintain` step 7 is the manual check for repos
without hooks installed, and prints the re-sync command. Re-syncing the
fallback copy is `cp <skill>/scripts/check_docs.py
scripts/tools/check_docs.py` — it never touches your `check_docs_local.py`.

You can also run the checker directly, without a session:

```
python scripts/tools/check_docs.py            # check the repo, exit 1 on findings
python scripts/tools/check_docs.py --root DIR # check another repo
python scripts/tools/check_docs.py --selfcheck
python scripts/tools/check_docs.py --init-config
```

## This repo uses its own system

See `CLAUDE.md` for the routing table, `docs/DECISIONS.md` for what was decided
and why, and `docs/log/` for what happened.
