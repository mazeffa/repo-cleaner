# Decision register

This file is authoritative for **what we believe and why**.

## Open questions

Every `Status: open` entry below, in one place.

| ID | Question | Revisit |
|---|---|---|

## Fields

- **Status: `active` | `superseded` | `open`** — lifecycle.
- **Verdict: `adopted` | `rejected` | `unresolved`** — what happened to the approach.

Supersession is symmetric: if A names B in `Superseded-by`, B names A in `Supersedes`.

## D-001 — Adopt the repo-clean doc system in this repo
Status: active   Verdict: adopted   Date: 2026-09-18
Decision: Track decisions here, route questions through CLAUDE.md, log work in
docs/log/2026.md, and run the repo-clean checker from this repo's own
`skills/repo-clean/scripts/check_docs.py` working-tree copy (D-015). How the checker is
enforced is D-021's; commits are not gated.
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
Status: superseded   Verdict: adopted   Date: 2026-09-18
Superseded-by: D-024
Decision: `docs/research/*.md` must carry `Status:` and `Date:`, checked by the
research-fields rule. A superseded one must name what replaced it.
Why: Research was the only doc type with no lifecycle metadata and no checker rule, while
being rewritten in place — the type most likely to go stale silently.

## D-006 — Scope beyond a structural linter
Status: superseded   Verdict: unresolved   Date: 2026-09-18
Superseded-by: D-017
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
Status: superseded   Verdict: adopted   Date: 2026-09-18
Supersedes: D-002
Superseded-by: D-014
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
Status: superseded   Verdict: adopted   Date: 2026-09-19
Superseded-by: D-011
Decision: `docs/DECISIONS.md`, `docs/DEFECTS.md`, and `docs/log/` stay tracked and public.
Only generated review transcripts (`.council/`) and bytecode are ignored.
Why: The plugin's claim is that it runs on itself; the defect list and log are the only
evidence a visitor can check. The cost is ~26KB of unused files in each user's plugin
cache, which is not worth a pluginignore. Identity and private-project content were
scrubbed on 2026-09-18, so nothing in them is sensitive.

## D-010 — Plugin core is the authority; the vendored copy is a fallback
Status: superseded   Verdict: adopted   Date: 2026-09-19
Superseded-by: D-015
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

## D-011 — USAP internal fork; public release is out of scope
Status: active   Verdict: adopted   Date: 2026-09-19
Supersedes: D-009
Decision: This repo is the USAP data team's internal tool, hosted in Azure DevOps under
`Data_Science/_git/repo-clean`. It is not published and has no external users. The rule set
is forked freely to fit the team's work; no rule has to be defensible for the general
open-source case.
Why: Every design question so far had two answers — one for a public plugin serving unknown
repos, one for a known team of thirty doing known work. Holding both made each rule an
argument about hypothetical users. With the audience fixed, the rule set answers to one
group of people whose work we can see.

## D-012 — Home is a declared folder, not the git repo
Status: superseded   Verdict: adopted   Date: 2026-09-19
Superseded-by: D-018
Decision: The unit the system governs is a **home**: a folder the user declares at `init`.
`init` proposes the repo root and asks the user to confirm or enter a different path. The
answer is stored as a marker file inside the home (superseded by D-018: the marker's exact
shape and how a session finds it without a scan), so it travels with the project through
git and nobody on the team answers twice. There is no registry of homes and no scan for
them. Nesting is blocked: `init` refuses inside an existing home. When a session opens
inside a repo that contains homes but not inside one of them, the session-start hook names
the declared home and tells the user to reopen there.
Why: The team works in repos that hold many independent projects; a repo-wide doc system
would put fifty unrelated projects in one log. Asking once and storing the answer in the
folder is simpler than either a root registry, which goes stale when someone adds a project
and forgets the line, or a scan, which costs a walk of the tree to answer a question the
user can answer directly.

## D-013 — One fixed file set, owned by the data team
Status: superseded   Verdict: adopted   Date: 2026-09-19
Superseded-by: D-022
Decision: Every home gets the same file set with the same names and the same roles. The set
is defined by this repo's source, and changing it is a pull request here; data team
leadership owns it and the senior technical staff shape it. There is no per-user or
per-machine template layer. `init` run against a folder that already has docs offers the
user a choice: adopt the existing files into the routing table as they are, or convert them
into the standard set. Adopting means the tracker's current State and Next steps are lifted
into the new log's first entry, and the tracker itself is archived with a banner — not left
in place alongside the new files, which would give the same job two homes. Where a project
genuinely does not fit, the tool asks and the user decides case by case; the exception is
recorded in that project's register and escalated by talking to each other, not by any
mechanism in the tool. A local `check_docs_local.py` is allowed anywhere; the rule against
writing one in a production repo is held by people, not the tool, and a project that needs
one records why in its own register — the same exception path as above. A local config may
not disable `diary-grammar`: a config can map any rule id to `None`, and that rule is the one
enforcing the `State:` line D-017 is measured by. Policy only for now — a two-line guard in
`run_generic_rules` is a later decision if it needs teeth, and the same goes for enforcing
the production rule.
Why: The point of the standard is that any of the thirty can open any project cold and know
where everything is. Every configuration knob is a way for two people to end up different,
so the default is the standard rather than a starting point. Because the senior staff hold
commit rights here, "shipped in the plugin" and "owned by the team" are the same thing, and
no separate governed template artifact is needed.

## D-014 — Session end forces the log; standard conflicts nag
Status: superseded   Verdict: adopted   Date: 2026-09-19
Supersedes: D-008
Superseded-by: D-021
Decision: The session-end hook is the primary gate and it forces exactly one thing: the log
entry for this session exists and carries a real `State:` and `Next:`. Claude cannot hand
the turn back without it. A finding about the project's files not matching the standard does
not block; it is reported at the end of every session until a human resolves it, with no
give-up after three tries. The git pre-commit hook is kept, and checks only the homes a
commit actually touches rather than the whole repo. Every member of the team works in a
repo, so it fires in the normal case, not a fringe one. A home with no `.git` is unenforced
for structure beyond that: findings are reported at every session start and nothing more —
that is what this decision asks for, not a gap to file as a bug.
Why: Two failures were being treated as one. A missing log entry is always the model's
fault and the model can always fix it, so forcing it costs nothing and buys the continuity
the whole system exists for. A structural conflict can be a call the model should not make
alone, and blocking on it either wedges the turn or trains everyone to ignore the gate —
persistent reporting keeps it visible without pretending the model can settle it.

## D-015 — One checker, in the plugin
Status: active   Verdict: adopted   Date: 2026-09-19
Supersedes: D-010
Decision: The checker exists once, in this repo. No copy is vendored into a target project.
The drift detection, the version-and-digest reporting, and the re-sync instructions that
existed only to manage two copies are removed. The session-start hook's "is this set up
here" test keys on the home marker rather than on a vendored script's presence.
Why: Two copies of the same file is a versioning problem invented to serve machines without
the plugin installed, and the team is being given the plugin — by manual pull now, by group
policy later. Removing the second copy removes the drift machinery with it. Version skew
between machines is real until the policy push lands, and the tool reporting its own version
at session start is enough to make a stale install visible.

## D-016 — Rule set adjusted for analytics work
Status: active   Verdict: adopted   Date: 2026-09-19
Decision: Three changes. (a) The outside-path rule flags only paths under a user's home
directory; lakehouse URLs, database server names, and corporate network shares are allowed,
because everyone on the team can reach them. (b) Link resolution applies only to links
pointing at documentation; links to data files and generated outputs are not checked. (c)
Next steps are a `Next:` field on the current log entry and nowhere else — the banned-heading
rule is replaced by this, so a next-steps heading is invalid everywhere and the field is the
only place the information lives.
Why: The original rules assumed software documentation in a self-contained repo. Analytics
work is defined by what it points at outside itself, so a blanket ban on external paths
fires on nearly every project while catching nothing real — a home-directory path is the
only kind nobody else can reach. Broken links between documents send the model to a file
that is not there and it invents what was in it; a missing dated output file is routine.
Next steps in an undated file rot unnoticed, but the log entry carries a date, so the same
information expires visibly.

## D-017 — Continuity is what this is measured by
Status: active   Verdict: adopted   Date: 2026-09-19
Supersedes: D-006
Decision: The system is measured by one outcome: someone opens a project they have not
touched in months and is working within a minute, reading nothing but what the tool prints.
That makes the current log entry and the session-start line that prints it the load-bearing
part, and everything else supporting. A rule stays only if breaking it would make the model
hallucinate or redo work. Which checker rules pass that test is D-024's list.
"Contradictions between files" named in an earlier
draft of this decision is not a checker rule; it is the manual pass in `maintain.md` step 6.
Why: D-006 asked whether this is more than a structural linter and could not be settled
without knowing who it serves. With the audience fixed to the data team (D-011), the answer
is that nobody here wants tidy documents; they want to resume work without repeating it.
That gives every arguable rule a test it either passes or does not, which is what D-006 was
missing.

## D-018 — Finding the home
Status: superseded   Verdict: adopted   Date: 2026-09-19
Supersedes: D-012
Superseded-by: D-023
Decision: Same belief as D-012 on the unit, nesting, and no registry, with three changes.
(a) The marker `.repo-clean` is an empty file; its presence is the whole declaration. (b)
The hooks find the home by walking up from the working directory to the nearest marker.
When none is found, the session-start hook globs two levels down for homes (markers, and
pre-marker homes per (c)) and names the ones with un-folded work, so a session opened at a
repo root folds in per home (D-021). (c) A folder with
`CLAUDE.md` and `docs/log/` but no marker is a pre-marker home: the hooks treat it as a home
and print one line telling the user to run `/repo-clean init --migrate`, which writes the
marker and deletes the vendored checker.
Why: D-012's "no scan" cannot deliver D-012's "name the declared home"; a two-level glob
under one folder is not the tree walk D-012 rejected. Without (c), every existing install
goes silent on upgrade.

## D-019 — Enhancements are open decisions
Status: active   Verdict: adopted   Date: 2026-09-19
Decision: A wanted improvement not yet taken up is a decision entry with exactly
`Status: open   Verdict: unresolved` and a `Revisit:` line, listed in the Open-questions
table. No enhancement tracker file; `docs/DEFECTS.md` holds only what is broken.
Why: The table already exists and `open-questions-sync` already checks it; DEF-23's own
text said an idea like this should be "deferred to a decision entry".

## D-020 — Routed authorities outside the checked set
Status: active   Verdict: adopted   Date: 2026-09-20
Decision: Every `.md` a `CLAUDE.md` routing row names is a living doc and is checked like
any file under the docs dir. Decided 2026-09-28; built in 0.9.0.
Why: `living_docs()` was the `living_roots` (CLAUDE.md, README.md) plus every `.md` under
the docs dir. The first real adoption routes `shared/README.md`, `org_chart.md` and
`presentations/<name>/README.md` outside that set: the row's target was existence-checked,
but nothing read the file, so a dead link or a contradiction in a routed authority was
invisible. A file the table calls authoritative is one the model will trust, so it is one
the checker reads. Rejected: (a) leave it — the table is the contract; (c) let a home widen
`living_roots` in its own config, which is the per-home knob D-013 rules out.

## D-021 — Fold-in from transcripts; no commit hook
Status: superseded   Verdict: adopted   Date: 2026-09-28
Supersedes: D-014
Superseded-by: D-025
Decision: Replaces D-014's session-end design. Built in 0.9.0.
(1) Git is storage. No commit hook, no `core.hooksPath`, nothing keyed on a repo; the unit
is the home (D-018). `init` and `reorganize` never commit, stash, stage or change git
settings, including `.gitignore`.
(2) The raw record is Claude Code's own session transcript, kept 30 days by default and
never truncated by compaction. The tool writes no notes of its own to have a record.
(3) Fold-in — Claude reading earlier sessions and writing what happened into the docs,
following the `maintain` procedure — is the one act that writes the docs: one log entry,
current state and next steps, the decisions and caveats it is sure of, the rest raised. It
owns the log write, including a year rollover: it writes to the current year's file,
creates it when missing, and removes the previous file's last `State:`/`Next:` lines.
(4) Three triggers, all inside a live session: the user asks; the user says the session is
over; a new session starts (startup only, not resume, clear or compact). At startup, if the
home has un-folded sessions, fold-in proceeds unless the user says "not now". The current
session is never folded at its own start, and a session whose transcript changed after its
last fold-in counts as un-folded again. The phrases are words, not hooks; the session-start
line lists them so the team learns them.
(5) The end-of-response hook records every session, edits or not: session id, transcript
path, and the home of each edited file, resolved from the file's path. A session with no
edits is recorded against the home it opened in. No model and no log write.
(6) Doc problems stop the user at every chance. When a markdown doc in a touched home
changed, the end-of-response hook runs the checker and blocks on a finding, guarded so it
cannot loop; session start also runs the checker and prints any finding for Claude to raise
first. An edit to code or data triggers no checker run.
(7) Fold-in reads the user's words, Claude's words, edited file paths and the user's answers
to questions and plan prompts. It opens tool or query output only when it needs a specific
fact that lives there, never in bulk, so patient data in query results is not pulled in by
default. It reads every listed session to the end, only what is newer than that session's
last fold-in, and is not marked finished until it has. If a transcript has expired or the
reader recognizes nothing in it, fold-in records that the session happened and its detail
was lost, and goes on; when every listed session is lost it stops and says so.
(8) `init` forces the D-013 file set on every home, with current state kept in the log's
last entry; that entry may point to another file for longer detail.
(9) A session opened above several homes prints one line: the count of homes with un-folded
work, the first three names, then "and N more". `init` checks every `@` reference in
`CLAUDE.md` points to a real file.
(10) No PowerShell in the plugin, in any file, for any reason, including as a fallback
shell. A machine with no Git Bash runs no hooks and cannot say so; every team machine that
runs Claude Code has Git Bash.
Why: D-014 was checked against how the team works — many independent projects per repo,
several Claude windows open at once per project, git used as storage only — and was wrong
three ways: the commit hook adds nothing and breaks on multi-project repos, the
end-of-response check ran on any edit though it can only find things in markdown, and the
log was written when Claude has the least perspective, producing stubs. The audience is
thirty people who log when asked and volunteer nothing. A short note every fifth response
was considered and dropped: with the transcript as the record it adds noise and no
information.

## D-022 — Never run project code; one fixed file set
Status: active   Verdict: adopted   Date: 2026-10-10
Supersedes: D-013
Decision: Restates D-013 without its add-on allowance. (1) The plugin never runs code that
lives in a project. The hooks and the checker run only the checker shipped with the plugin;
there is no per-project `check_docs_local.py`, no config override, and opening a project
executes nothing from it. (2) Every home gets the same file set with the same names and the
same roles. The set is defined by this repo's source, and changing it is a pull request here;
data team leadership owns it and the senior technical staff shape it. There is no per-user or
per-machine template layer. `init` run against a folder that already has docs offers the user
a choice: adopt the existing files into the routing table as they are, or convert them into
the standard set. Adopting means the tracker's current State and Next steps are lifted into
the new log's first entry, and the tracker itself is archived with a banner — not left in
place alongside the new files, which would give the same job two homes. Where a project
genuinely does not fit, the tool asks and the user decides case by case; the exception is
recorded in that project's register. The one in-text escape from a rule that misfires is the
`<!-- check-docs: ignore RULE -->` comment on the line. (3) Undoing `reorganize`'s own
edits (`git restore` of the files it moved or rewrote, deleting the copies it created) is not
one of the git actions D-021(1) rules out; `git reset --hard` is never used.
Why: Code in a project is code the project's last editor chose, and running it because a
session opened there is a way for a repo to run anything on a teammate's machine. The add-on
file was also the only thing that could widen or disable a rule, so it was the one way two
people's checkers could differ — the thing D-013 existed to prevent — and no home ever
needed one. The rest is D-013's reasoning unchanged: the point of the standard is that any
of the thirty can open any project cold and know where everything is. `reorganize` once
rolled back with `git reset --hard`, which erases unrelated uncommitted work.

## D-023 — Marker only
Status: active   Verdict: adopted   Date: 2026-10-10
Supersedes: D-018
Decision: Same belief as D-018 (a) and (b), without (c). (a) The marker `.repo-clean` is an
empty file; its presence is the whole declaration. (b) The hooks and the checker find the
home by walking up from the working directory (the checker: from the current folder when
`--root` is not given) to the nearest marker. When none is found, the session-start hook
globs two levels down for marked homes and names the ones with un-folded work, so a session
opened at a repo root folds in per home (D-021); the checker exits 2, since nothing was
checked. A folder with `CLAUDE.md` and `docs/log/` but no marker is not a home, and there is
no `--migrate`.
Why: (c) existed so installs from before the marker kept working on upgrade. That window is
over, and every code path keeping it alive — a legacy flag on `find_home`, a one-time hint, a
`--migrate` step in `init` — was a second definition of "home" the hooks and the checker had
to agree on.

## D-024 — Checker rule set
Status: active   Verdict: adopted   Date: 2026-10-10
Supersedes: D-005
Decision: A checker rule stays only if breaking it leaves a doc that Claude trusts saying
something false or ambiguous. Eight rules pass: `decisions-integrity` (a register that
misnames its own supersession has Claude following a replaced decision), `log-fields-resolve`
(a log entry naming a decision or doc that is not there sends Claude to invent it),
`outside-repo-paths` (a path nobody else can open), `paths-exist` (a link to a missing `.md`),
`banned-headers` (a next-steps heading is an undated copy of `Next:`, D-016(c), in every
file including the register), `diary-grammar` (`State:`/`Next:` only on the last entry — the
line D-017 is measured by), `open-questions-sync` (an open decision missing from the table is
never revisited), and `routing-coverage` (a doc no row names is not found). Two are dropped:
`archive-banner-paths` and `research-fields`. A bad archive banner path or a missing research
`Date:` leaves nothing Claude trusts saying something false, and neither rule ever caught a
real problem. The archive banner and the research `Status:`/`Date:` header stay as
conventions, unenforced. This supersedes D-005, which required the research header by rule.
Why: D-017 set the test and applied it by rule id; this applies it again to the rules built
since, and writes the list in one place (the checker's docstring points here), so a rule's
presence is always a decision rather than an accident. Each dropped rule cost code, a config
key and a selftest fixture to guard against a failure nobody had had.

## D-025 — Capture by request; the one hook only reads
Status: active   Verdict: adopted   Date: 2026-10-10
Supersedes: D-021
Decision: Keeps D-021 (1) git is storage, (3) one act writes the docs, (8) the fixed file
set, and (10) no PowerShell, as written there. Replaces the rest:
(a) One hook, SessionStart. It prints the last log entry's heading, how many days old that
entry is, its `State:` and `Next:`, the plugin version, and any checker finding. It records
nothing except offered.json, the folders already offered setup, so the offer fires once. A
headless turn in a new folder can use that offer up; accepted. It never blocks. There is no
end-of-response hook and no edit hook. SessionStart also runs in headless claude -p turns and
prints there; the cost is accepted, and the fix belongs to the callers.
(b) `maintain` writes the log from the current conversation when the user asks ("log this",
"/repo-clean maintain") or says the session is over. Nothing starts it at session start.
(c) No session record and no code that reads transcripts. Claude Code's own transcript, kept
30 days by default in the user's Claude projects folder, is where a session nobody logged can
still be read by hand.
(d) Doc findings are reported at session start and by `maintain`'s checker step; a doc edited
in ordinary work is unchecked until one of those runs.
(e) Opened above several homes, the hook prints one line naming them: the first three, then
"and N more".
(f) Scaffold text in homes set up earlier is point-in-time and is not rewritten; the log is
the truth. The plugin never writes outside the target repo.
(g) The old session-registry folder in the user's Claude settings area is dead and never read.
Why: debate 3 and the LLM council, 2026-10-10. D-021(4) put a fold-in ahead of the first
minute D-017 measures, and its queue grew by one with every automated session: the
session-start line told each headless debate turn to fold in before other work. The
turn-end block D-021(6) added was never seen working under the real runner. The capture
machinery (three hook files, the session registry, about 400 test lines) was the only state
two sessions had to agree on.
