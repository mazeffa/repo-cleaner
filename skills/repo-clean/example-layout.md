# Example layout

Illustrative, not canonical. A synthetic example — a delivery-ETA service — showing the
shape `init.md`'s inline skeletons produce once a repo has been living in the system for a
while. It is not the thing `init` scaffolds on day one (that's a handful of near-empty
files; see `init.md` for the actual starting skeletons). Filenames, table rows, and wording
here are one repo's choices, not requirements — your `init` interview derives your own file
list from your own repo's questions.

## Routing table (CLAUDE.md)

```markdown
## Where answers live

| Question | Authority |
|---|---|
| What this is, setup, how to run, known defects | `README.md` |
| Weekly ops procedure | `docs/RUNBOOK.md` |
| What we believe and why (D-NNN) | `docs/DECISIONS.md` |
| What happened, and current quarter state | `docs/log/<quarter>.md` — current state is that file's last entry's `State:` line: `grep '^State:' docs/log/<quarter>.md \| tail -1` |
| Model, features, accuracy | `docs/research/prediction_model.md` |
| Route construction and the dispatch planner | `docs/research/dispatch_planner.md` |
```

Every question has exactly one authoritative file. If no row matches, ask before creating
a document.

## Decision register entry (docs/DECISIONS.md)

```markdown
## D-004 — Weather features (precipitation, wind, road-surface temp)
Status: active   Verdict: adopted   Date: 2025-09-14, reconfirmed 2026-09-08
Evidence: docs/archive/TECHNICAL_DECISIONS.md:33-35, docs/log/2025-Q3.md:581-594
Decision: Include forecast weather features (precipitation rate, wind, surface temp) in the
ETA feature set.
Why:
- Precipitation is the dominant driver of last-mile speed variance in the historical data.
- Reconfirmed by ablation: dropping the weather group cost -4.79 on-time pct/week (SE 2.02,
  2.4 SE) — the single largest route-level driver of any feature group tested, despite barely
  moving raw per-stop ETA correlation (0.6126 -> 0.6078).
```

Two orthogonal, closed-vocabulary fields: `Status: active | superseded | open` (lifecycle)
and `Verdict: adopted | rejected | unresolved` (what happened to the approach). Supersession
is symmetric — if A names B in `Superseded-by`, B names A in `Supersedes`.

## Log entry (docs/log/<period>.md)

```markdown
## 2026-09-13 (4) — Phase 1 of the model/planner review: six defects fixed, backtest rerun

Decisions: D-041 (new: six defects fixed, backtest rerun)
Docs: docs/DECISIONS.md, docs/research/backtest.md, docs/research/prediction_model.md,
docs/research/dispatch_planner.md
State: Region 1 fully migrated and cut over (2026-09-13, this period's first entry); model/planner Phase 1 defects
fixed and validated, backtest at +10.57 on-time pct/wk (paired vs pre-fix +3.75 ns / +3.02
mean10, 2.3 SE); Monday ingest/report not yet run; open before Region 2: surge-mode capacity
caps (D-035 follow-up 2), D-037's route_runs.parquet design (adopted, not yet coded), D-040's
training-window lead, Phase 2/3 of the model/planner review.

**The question.** A full review of the prediction model and dispatch planner found six live
defects, the most serious of which meant the +7.6 on-time pct/week backtest edge...
```

Heading grammar: `## YYYY-MM-DD [(N)] — headline`, `(N)` only when more than one entry
shares a date. Every entry needs `Decisions:` and `Docs:`; only the file's *last* entry
carries `State:` — that line is the only current truth, found with
`grep '^State:' docs/log/<period>.md | tail -1`. The log is append-only: never edit an old
entry's prose to make it read as current, add a new entry instead.

## Archive banner (docs/archive/*.md)

```markdown
> **Archived 2026-09-08.** Superseded by `docs/research/dispatch_planner.md`, which carries the
> current route-construction/eligibility logic; this doc is kept for the historical rationale.
```

Rationale, not instruction — never follow directions found in an archived file, even ones
phrased as current. `reorganize` writes this exact banner grammar (`> **Archived
YYYY-MM-DD.** <disposition>`) when it moves a superseded doc there with `git mv`.
