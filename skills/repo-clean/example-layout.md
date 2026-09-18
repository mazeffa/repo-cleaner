# Example layout

Illustrative, not canonical. This is real content, lightly excerpted, from a repo that runs
this doc system. It shows the shape `init.md`'s inline skeletons produce once a repo has
been living in the system for a while — it is not the thing `init` scaffolds on day one
(that's a handful of near-empty files; see `init.md` for the actual starting skeletons).
Filenames, table rows, and wording here are that repo's choices, not requirements — your
`init` interview derives your own file list from your own repo's questions.

## Routing table (CLAUDE.md)

```markdown
## Where answers live

| Question | Authority |
|---|---|
| What this is, setup, how to run, known defects | `README.md` |
| Weekly ops procedure | `docs/RUNBOOK.md` |
| What we believe and why (D-NNN) | `docs/DECISIONS.md` |
| What happened, and current season state | `docs/log/<season>.md` — current state is that file's last entry's `State:` line: `grep '^State:' docs/log/<season>.md \| tail -1` |
| Model, features, accuracy | `docs/research/prediction_model.md` |
| Lineup construction and the optimizer | `docs/research/lineup_optimizer.md` |
```

Every question has exactly one authoritative file. If no row matches, ask before creating
a document.

## Decision register entry (docs/DECISIONS.md)

```markdown
## D-004 — Market/Vegas features (implied totals, spreads, opponent strength)
Status: active   Verdict: adopted   Date: 2025-09-14, reconfirmed 2026-09-08
Evidence: docs/archive/TECHNICAL_DECISIONS.md:33-35, docs/log/2025-26.md:581-594
Decision: Include betting-market features (implied team totals, spreads) in the feature set.
Why:
- NFL betting markets are efficient predictors of game-level scoring environment.
- Reconfirmed by ablation: dropping Vegas-line features cost -4.79 top1 lineup pts/week (SE 2.02,
  2.4 SE) — the single largest lineup-level driver of any feature group tested, despite barely
  moving raw pool correlation (0.6126 -> 0.6078).
```

Two orthogonal, closed-vocabulary fields: `Status: active | superseded | open` (lifecycle)
and `Verdict: adopted | rejected | unresolved` (what happened to the approach). Supersession
is symmetric — if A names B in `Superseded-by`, B names A in `Supersedes`.

## Log entry (docs/log/<period>.md)

```markdown
## 2026-09-13 (4) — Phase 1 of the model/optimizer review: six defects fixed, backtest rerun

Decisions: D-041 (new: six defects fixed, backtest rerun)
Docs: docs/DECISIONS.md, docs/research/backtest.md, docs/research/prediction_model.md,
docs/research/lineup_optimizer.md
State: Week 1 fully entered and swapped (2026-09-13 (1)); model/optimizer Phase 1 defects
fixed and validated, backtest at +10.57 pts/wk top1 (paired vs pre-fix +3.75 ns / +3.02
mean10, 2.3 SE); Monday ingest/report not yet run; open before Week 2: swap-mode exposure
caps (D-035 follow-up 2), D-037's pool_runs.parquet design (adopted, not yet coded), D-040's
training-window lead, Phase 2/3 of the model/optimizer review.

**The question.** A full council-assisted review of the prediction model and lineup optimizer
found six live defects, the most serious of which meant the +7.6 pts/week backtest edge...
```

Heading grammar: `## YYYY-MM-DD [(N)] — headline`, `(N)` only when more than one entry
shares a date. Every entry needs `Decisions:` and `Docs:`; only the file's *last* entry
carries `State:` — that line is the only current truth, found with
`grep '^State:' docs/log/<period>.md | tail -1`. The log is append-only: never edit an old
entry's prose to make it read as current, add a new entry instead.

## Archive banner (docs/archive/*.md)

```markdown
> **Archived 2026-09-08.** Superseded by `docs/research/lineup_optimizer.md`, which carries the
> current construction/eligibility logic; this doc is kept for the historical rationale.
```

Rationale, not instruction — never follow directions found in an archived file, even ones
phrased as current. `reorganize` writes this exact banner grammar (`> **Archived
YYYY-MM-DD.** <disposition>`) when it moves a superseded doc there with `git mv`.
