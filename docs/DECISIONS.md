# Decision register

This file is authoritative for **what we believe and why**.

## Open questions

Every `Status: open` entry below, in one place.

| ID | Question | Revisit |
|---|---|---|
| D-006 | Is a question-ownership system worth building beyond a structural linter? | When the routing eval exists |

## Fields

- **Status: `active` | `superseded` | `open`** — lifecycle.
- **Verdict: `adopted` | `rejected` | `unresolved`** — what happened to the approach.

Supersession is symmetric: if A names B in `Superseded-by`, B names A in `Supersedes`.

## D-001 — Adopt the repo-clean doc system in this repo
Status: active   Verdict: adopted   Date: 2026-09-18
Decision: Track decisions here, route questions through CLAUDE.md, log work in
docs/log/2026.md, gate commits on scripts/tools/check_docs.py.
Why: The plugin did not use its own system, so every design decision lived only in chat
and nothing tested whether the system is pleasant to live with.

## D-002 — Drop the session-end checker gate
Status: superseded   Verdict: adopted   Date: 2026-09-18
Supersedes: D-003
Superseded-by: D-008
Decision: Remove all "before ending a session, run the checker" language. The pre-commit
hook is the only gate.
Why: No event tells a model a session is ending, so the instruction never fired. A Stop
hook would only inject a message, not enforce anything, and would not fire on Ctrl-C or a
killed terminal. The pre-commit hook already fires when docs enter history, with scope
bounded to the commit and room to fix.

## D-003 — Session-end gate as the primary enforcement point
Status: superseded   Verdict: rejected   Date: 2026-09-18
Superseded-by: D-002
Decision: (Original design.) The skill instructed a session-end checker run.
Why: Recorded so the reasoning is not rediscovered. It was never enforceable.

## D-004 — Fold `audit` into `maintain --check`
Status: active   Verdict: adopted   Date: 2026-09-18
Decision: Delete audit.md; `maintain --check` is the read-only mode.
Why: audit.md duplicated maintain.md's routing analysis with writes disabled. Two prose
paths saying almost the same thing drift apart, which is the failure this system exists to
prevent.

## D-005 — Research docs carry Status:/Date:
Status: active   Verdict: adopted   Date: 2026-09-18
Decision: `docs/research/*.md` must carry `Status:` and `Date:`, checked by the
research-fields rule. A superseded one must name what replaced it.
Why: Research was the only doc type with no lifecycle metadata and no checker rule, while
being rewritten in place — the type most likely to go stale silently.

## D-006 — Scope beyond a structural linter
Status: open   Verdict: unresolved   Date: 2026-09-18
Revisit: When the routing eval exists
Decision: Undecided. Three rounds of external review converged on "this enforces shape and
cannot touch content", and recommended shipping a linter plus an AGENTS.md template rather
than a governance system.
Why: The alternative design — humans author the question inventory, agents select from it
rather than writing their own — is the only proposal that stops the agent being corrected
from authoring the artifact used to check it. Untested either way.

## D-007 — Log known defects in docs/DEFECTS.md
Status: active   Verdict: adopted   Date: 2026-09-18
Decision: A new routed file, `docs/DEFECTS.md`, owns "what is broken and its status".
Why: An adversarial pass found 22 defects and there was no routing row that owned them, so
they existed only in a chat transcript — the exact failure this system exists to prevent,
in this repo. A README section was the alternative; rejected because the list churns as
fixes land and 22 reproductions do not belong in an install guide.

## D-008 — Hooks are primary, git hook is a backstop
Status: active   Verdict: adopted   Date: 2026-09-18
Supersedes: D-002
Decision: A SessionStart/PostToolUse/Stop/PreCompact hook set (see Hooks in
`skills/repo-clean/SKILL.md`) forces setup, logging, and a clean checker run every session
that changed files, independent of git. The pre-commit hook still runs where `.git` exists,
as a backstop, not the only gate.
Why: D-002's reasoning held for a session-end instruction, not for an actual hook: Stop
fires reliably on a normal turn end and can block with `exit 2`, and PreCompact protects
against the case D-002 couldn't address at all — losing the record when context compacts.
Making git optional was also agreed: this is an agent memory/logging system, not a
git-dependent workflow tool.


## D-009 — This repo's own docs ship public, as the worked example
Status: active   Verdict: adopted   Date: 2026-09-19
Decision: `docs/DECISIONS.md`, `docs/DEFECTS.md`, and `docs/log/` stay tracked and public.
Only generated review transcripts (`.council/`) and bytecode are ignored.
Why: The plugin's claim is that it runs on itself; the defect list and log are the only
evidence a visitor can check. The cost is ~26KB of unused files in each user's plugin
cache, which is not worth a pluginignore. Identity and private-project content were
scrubbed on 2026-09-18, so nothing in them is sensitive.

## D-010 — Plugin core is the authority; the vendored copy is a fallback
Status: active   Verdict: adopted   Date: 2026-09-19
Decision: The installed `pre-commit` and the Stop hook both run the newest cached plugin
core; the vendored `scripts/tools/check_docs.py` stays in git as the fallback for
machines without the plugin; this plugin's own repo runs its working-tree copy.
Why: Re-syncing means a hook overwriting a tracked repo file, which `SKILL.md`'s Never
list forbids and which would dirty `git status` on every plugin update. `local_module_dir()`
already resolves a repo's `check_docs_local.py` when the core runs from outside the repo, so
`--root <repo>` from the plugin cache picks up the repo's own rules. With nothing vendored
as authority, there is nothing to sync and no drift to report.
Named costs: a plugin update enforces new rules on the next commit unannounced
(`--no-verify` is the escape hatch); the fallback copy goes stale silently and enforces an
old ruleset wherever the plugin is absent; "newest cached" can differ from the loaded
plugin after a downgrade, chosen so the two gates (pre-commit, Stop hook) never split.
Two clarifications so nobody "fixes" them later: (a) the vendored copy is a fallback but
not optional — `session_start.py` treats a missing `scripts/tools/check_docs.py` as "not
set up here", and `running_core()` falls back to it, so deleting it breaks both; (b) drift
is measured against what the remedy copies from: a plugin-resolving repo compares its
fallback to the newest cached core (the thing that runs), a vendored-only repo compares to
the loaded plugin's copy (the thing maintain step 7's `cp` sources from).
