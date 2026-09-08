# Step 1 Findings: NFL Model v35 Audit

**Baseline**: `NFL_Prediction_Model_v35.xlsx`
**SHA-256**: `fdd0b971df91cae905e8884258d99d4a562ebdbf8c2122259b02a54955ec3c17`
**Inspected**: 2026-09-01
**Sheets**: 31 (see `v35_worksheet_inventory.csv`)
**Real tunable Model Assumptions constants**: 153 (see `v35_model_assumptions_manifest.csv`)

## Confirmed dead/disconnected constants (real finding, not extraction noise)

Traced by grepping every `scripts/*.py` file for each constant's cell reference, then
manually confirming any non-match by reading the defining script -- these three are
genuinely never read by any formula in v35, not a false negative of the automated pass:

| Row | Label | Value | Why it's dead |
|---|---|---|---|
| C19 | Historical Lookback Window (years) | (documents "3") | Every build script hardcodes its own `HISTORICAL_YEARS = [2023, 2024, 2025]` Python literal, independent of this cell. Changing C19 in Excel has zero effect on which years get pulled. |
| C92 | Pass Defense Matchup Points-to-Game-Points Conversion | 0.10 | Vestigial -- Pass Defense Matchup is "NOT wired into Team Ratings" (its own docstring); its real downstream consumer, the Defensive Matchup Engine, uses its own separate conversion constants instead. |
| C99 | Run Defense Matchup Points-to-Game-Points Conversion | 0.10 | Same as C92, for Run Defense Matchup. |

Five other constants initially flagged by the automated pass (C162-C165, Coaching Index's
weight cells) were false negatives of the grep-based method -- confirmed genuinely active by
tracing `build_coaching_index.py`'s own `weight_cell` string-splicing pattern, which builds
the `$C$162`-style reference across two separate f-string lines rather than as one literal
substring.

## Known limitation carried into this baseline

v35 has a real, now-independently-confirmed bug (fixed in v36, NOT in this frozen baseline):
`build_defensive_matchup_wiring.py`'s `RB_SEC5_RANGE` was hardcoded to `(335, 398)` while RB
Value Index's real Section 5 range had drifted to `(337, 400)` from real roster churn --
silently excluding the real last 2 RB players (including a real Washington Commanders
starter with real volume) from every Run Matchup Differential lookup. Document as a known
limitation of v35 specifically; do not silently work around it while v35 is the frozen
baseline.

## Next
Extend the manifest from "every tunable constant" to "every named contribution term feeding
Z/AA and each position Score" (the spec's own Step 4 requirement) -- larger effort, proposed
as the next concrete piece.
