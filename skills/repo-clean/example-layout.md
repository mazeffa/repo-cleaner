# Example layout

Illustrative, not canonical. A synthetic example — a delivery-ETA service — showing the
shape `init.md`'s inline skeletons produce once a repo has been living in the system for a
while. It is not the thing `init` scaffolds on day one (that's a handful of near-empty
files; see `init.md` for the actual starting skeletons and the fixed file set every home
gets). Extra rows here, like the runbook, are one repo's choices on top of that set.

## Routing table (CLAUDE.md)

```markdown
## Where answers live

| Question | Authority |
|---|---|
| What this is, setup, how to run | `README.md` |
| Weekly ops procedure | `docs/RUNBOOK.md` |
| What to do, and what's been done (bugs, tasks, ideas) | `docs/WORK.md` |
| What we decided, and why (D-NNN) | `docs/DECISIONS.md` |
| What happened | `docs/log/<year>.md` — the last entry; each entry is true as of its date |
| Model, features, accuracy | `docs/research/prediction_model.md` |
| Route construction and the dispatch planner | `docs/research/dispatch_planner.md` |
```

Rules: `SKILL.md` Principles.

## Work list (docs/WORK.md)

```markdown
| ID | Item | Type | Status | Added | Closed |
|---|---|---|---|---|---|
| W-12 | Holiday weeks double-count returned stops in the backtest | bug | done | 2026-09-02 | 2026-09-13 |
| W-14 | Run the Monday ingest and report on the fixed model | task | open | 2026-09-13 | |
| W-15 | Try live traffic speeds as a feature | idea | open | 2026-09-13 | |
| W-16 | Port the planner to the new routing API | task | dropped | 2026-08-20 | 2026-09-08 |
```

Grammar: `SKILL.md` Vocabulary.

## Decision register entry (docs/DECISIONS.md)

```markdown
## D-004 — Weather features (precipitation, wind, road-surface temp)
Status: active   Date: 2025-09-14, reconfirmed 2026-09-08
Evidence: docs/archive/TECHNICAL_DECISIONS.md:33-35, docs/log/2025.md:581-594
Decision: Include forecast weather features (precipitation rate, wind, surface temp) in the
ETA feature set.
Why:
- Precipitation is the dominant driver of last-mile speed variance in the historical data.
- Reconfirmed by ablation: dropping the weather group cost -4.79 on-time pct/week (SE 2.02,
  2.4 SE) — the single largest route-level driver of any feature group tested, despite barely
  moving raw per-stop ETA correlation (0.6126 -> 0.6078).
```

Grammar: `SKILL.md` Vocabulary.

## Log entry (docs/log/<year>.md)

```markdown
## 2026-09-13 (4) — Phase 1 of the model/planner review: six defects fixed, backtest rerun

Decisions: D-041 (new: six defects fixed, backtest rerun)
Docs: docs/DECISIONS.md, docs/research/backtest.md, docs/research/prediction_model.md,
docs/research/dispatch_planner.md

Left off: Phase 1 defects fixed and validated, backtest at +10.57 on-time pct/wk (paired vs
pre-fix +3.75 ns / +3.02 mean10, 2.3 SE); the Monday ingest and report on the fixed model is
W-14.

**The question.** A full review of the prediction model and dispatch planner found six live
defects, the most serious of which meant the +7.6 on-time pct/week backtest edge...
```

Grammar and rules: `SKILL.md` Vocabulary and Principles.

## Archive banner (docs/archive/*.md)

```markdown
> **Archived 2026-09-08.** Superseded by `docs/research/dispatch_planner.md`, which carries the
> current route-construction/eligibility logic; this doc is kept for the historical rationale.
```

Grammar and rules: `SKILL.md` Vocabulary and Principles; `reorganize` writes this banner.
