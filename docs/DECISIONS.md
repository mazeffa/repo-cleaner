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
Status: active   Verdict: adopted   Date: 2026-09-18
Supersedes: D-003
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
