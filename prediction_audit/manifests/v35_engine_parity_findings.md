# Python Model Engine: QB Index Parity Findings

First fully-wired tab of the "Python Model Engine" the validation spec's own roadmap ends
with -- and the piece Step 6 (walk-forward historical reconstruction) needs to actually run
the model programmatically at scale, since re-entering data by hand for thousands of
historical game-weeks isn't practical.

## Scope, deliberately narrow

`prediction_audit/engine/decay_baseline.py` -- 6 shared, generic, pure functions
(`decay_weighted_average`, `team_history`, `projected_baseline`, `blend_weight`,
`blended_value`, `z_score`, `weighted_composite_score`) implementing the exact arithmetic
shape every position-index tab's own Section 3/4/5 Excel formulas already use. Reusable
across every other tab (RB, WR-TE, Kicking, OL, Front Seven, Secondary, ...) -- confirmed via
Step 4's own extraction that they all share this same structure.

`prediction_audit/engine/qb_index.py` -- wires those generic functions into QB Index's own
real 3-metric chain (EPA/Play, CPOE, ANY/A; Pure Y/A excluded, matching its own real weight
of 0 in QB Index Score).

Deliberately scoped to ARITHMETIC ONLY, not data sourcing: `QBHistory` takes already-resolved
real Y-1/Y-2/Y-3 values as input, however they were resolved (real historical data, or
Section 2B's own real rookie-substitution logic) -- this module does not re-implement rookie
substitution in this first pass. Isolates "does the calculation logic match Excel" from "does
the data pull match Excel" as two genuinely separate, independently provable questions.

## Parity result: exact match, every intermediate value, all 64 real QBs

Ground truth (`v35_qb_index_ground_truth.json`) extracted from a real LibreOffice
recalculation of the frozen v35 baseline -- every real current-roster QB's real Y-1/Y-2/Y-3
inputs, real league baselines, real games-played/current-season blend inputs, and Excel's own
real computed values at every step.

`tests/test_qb_index_parity.py` recomputes the full chain in pure Python for all 64 real QBs
and checks EXACT match (1e-6 tolerance) against Excel's own real numbers at every step, not
just the final Score: Projected Baseline (per metric) -> Blend Weight -> Blended value (per
metric) -> Z-score (per metric) -> Weighted Z-Sum -> QB Index Score.

**Result: 66/66 pass (64 QBs x full chain + 2 fixture sanity checks).** Zero mismatches at
any step for any real player.

## Next
Same pattern applied to RB Value Index, WR-TE Value Index, and the remaining position tabs
Step 4 already catalogued -- each is a smaller increment now that the shared
decay_baseline.py functions exist; the real work per tab is building that tab's own
ground-truth extraction (mirroring seed_v35_demo.py's own real-cell-reading pattern) and its
own thin wrapper module (mirroring qb_index.py's own shape). Then the core Z/AA formula
itself, which is where every position tab's own Score actually feeds in.
