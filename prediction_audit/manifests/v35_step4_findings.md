# Step 4 Findings: Full Component Contribution Manifest

Extends Step 1's core-formula manifest (`v35_core_formula_components.csv`, Season Matchups'
own Z/AA) to every position/matchup tab's own weighted composite.

## Mechanically extracted: 45 real weighted-metric components across 11 worksheets

`v35_all_weighted_components.csv` -- QB Index, RB Value Index, WR-TE Value Index, Kicking
Index, Offensive Line Index, Front Seven Index, Secondary Index, Special Teams Index, Pass
Defense Matchup, Run Defense Matchup, Coaching Index. Each row: the real metric name, its
real Z-score column, the real Model Assumptions coefficient cell/value/label/note it's
weighted by, and the real weighted-sum formula it was parsed from -- not hand-typed, parsed
directly from each tab's own "Section 5" weighted-composite formula via regex, then
cross-referenced against Step 1's own Model Assumptions manifest.

Real, useful pattern visible directly in the data: multiple tabs (RB Value Index, WR-TE
Value Index) carry real metrics with a coefficient of exactly 0 by design (Red-Zone Carry
Share, Pass-Play Snap Participation %, Red-Zone Target Share, Target Share, Catch Rate) --
genuinely computed and decay-weighted every run, but deliberately excluded from the scored
composite, existing only to feed Player Prop Projections. Worth flagging for Step 10
(double-counting analysis): these are correctly isolated already, at the data-generation
layer, not just a hopeful "weight is 0 so it's fine" assumption -- confirmed real weight=0 in
this extraction.

## 5 sheets NOT covered by this pass -- genuinely different structure, not an extraction bug

Confirmed by direct inspection, not assumed:

| Worksheet | Why it doesn't fit the pattern |
|---|---|
| Advanced Efficiency Metrics | Composite column is literally named "Weighted Efficiency Adjustment (pts)", not "...Z-Score Sum" -- same underlying pattern, different header text. |
| QB Environment Model | "Weighted Talent Z-Sum" feeds a "Raw QB Talent Score" that is explicitly NOT the QB Index Score -- a separate, reference-only composite that feeds Effective QB Rating, per that tab's own docstring. |
| Special Teams Player Index | No weighted composite at all -- a single "Z-Score" column, one metric, no Model Assumptions coefficient to extract. |
| Explosive Play Matchup | Computes two separate phase composites (Pass Prevention, Run Prevention), not one shared weighted-sum column. |
| Pass Rush Generation Index | Similarly its own single "Pass Rush Generation Score (Z)", different shape. |

Not extracted mechanically in this pass; would need individual review if a complete
Component_ID catalog (matching the spec's own field list exactly) is required before Step 9's
ablation testing begins.

## Next
The parity-tested Python port (already proposed) starts from QB Index -- the first tab in
the dependency chain with a full, provable 3-Yr decay-weighted-regression -> current-season-
blend -> Z-score -> weighted-composite chain, and the one most other tabs' own patterns
mirror structurally.
