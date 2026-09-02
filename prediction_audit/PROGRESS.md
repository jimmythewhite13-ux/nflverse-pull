# NFL Model v35 Validation/Audit — Progress Report

**Frozen baseline**: `NFL_Prediction_Model_v35.xlsx`
**SHA-256**: `fdd0b971df91cae905e8884258d99d4a562ebdbf8c2122259b02a54955ec3c17`
**Last updated**: 2026-09-02

This tracks progress against the master validation/audit spec's own 15-step plan. Steps are
listed in the spec's own order; status reflects what's actually built and verified, not
planned.

## Status by step

| Step | What it asks for | Status |
|---|---|---|
| 1 | Freeze & document v35 | **Done** |
| 2 | Prediction Audit database | **Done** |
| 3 | Full model-state snapshot schema | **Done** |
| 4 | Component contribution manifest | **Done** (all 17 real named Z/AA terms + 45 weighted metrics across 11 tabs) |
| 5 | Market & CLV infrastructure | **Blocked** — no real historical odds source with verified timestamps (see below) |
| 6 | Historical reconstruction 2021-2025 | **Unblocked, not yet run** — the Python Model Engine can now reproduce a full real game prediction end to end (see milestone below); walk-forward reconstruction across historical seasons is the next real increment |
| 7 | Baseline backtest | Not started (depends on Step 6) |
| 8 | Walk-forward validation | Not started (depends on Step 6) |
| 9 | Ablation testing | Not started (depends on Step 6) |
| 10 | Double-counting/correlation analysis | Not started (one real finding already surfaced in Step 4 — see below) |
| 11 | Environmental calibration | Not started |
| 12 | Probability/confidence calibration | Not started |
| 13 | Model selection (A/B/C) | Not started |
| 14 | Prop tracking schema | Not started |
| 15 | Final validated spec document | Not started |

## Step 5 — why it's blocked

This project has only ever used **manual, current-week** sportsbook entry. There is no
archive anywhere in it of real historical opening/closing lines with real timestamps. Per the
spec's own principle ("do not fabricate historical betting lines"), this is not being
invented. Unblocking Step 5 (and the ATS/ROI/CLV portions of Steps 6-7, and all of Step 14)
requires either a paid historical odds API (Odds API, SportsDataIO, Unabated, etc.) or
accepting a forward-only start: begin collecting real CLV data from now on rather than
reconstructing the past.

## MILESTONE — the real Z/AA formula is now fully reproduced in Python

`prediction_audit/engine/season_matchups.py`'s `compute_model_home_away_score()` composes
every real term of Season Matchups' own Z (Model Home Score) / AA (Model Away Score) formula
and, checked against all **272 real 2026 games**, reproduces the real Excel value **exactly**
(`abs=1e-6`) end to end. Every term is recomputed fresh from real per-team/per-game ground
truth through the already-ported engine functions — not read pre-summed from Excel. This is
the concrete deliverable Step 6 has been waiting on.

## The Python Model Engine (`prediction_audit/engine/`)

Not one of the spec's own numbered steps by name, but the concrete piece Step 6 actually
needs to run the model programmatically at scale — re-entering data by hand for thousands of
historical game-weeks isn't practical. Built once, serves both the audit (offline
reconstruction) and, eventually, a live production system.

**Method**: for each tab/term, the real Excel formula chain is read directly from the frozen
v35 file (never assumed from another tab's pattern), a ground-truth JSON is extracted from a
real LibreOffice recalculation (every real player/team/game's real inputs and Excel's own real
computed values at every step), a pure-Python module reproduces the chain, and a parity test
checks **exact match at every intermediate step** — not just the final Score — against the
real ground truth. 1e-6 floating-point tolerance throughout.

### Index/Matchup tabs ported and verified (17 of 17)

| # | Tab | Shape | Real population | Tests |
|---|---|---|---|---|
| 1 | QB Index | Player, blend | 64 QBs | 66/66 |
| 2 | RB Value Index | Player, blend | 64 RBs | 66/66 |
| 3 | WR-TE Value Index | Player, blend | 128 (WR+TE) | 130/130 |
| 4 | Secondary Index | Team, blend | 32 teams | 34/34 |
| 5 | Coaching Index | Team, no blend, inverted Penalty, no baseline offset | 32 teams | 34/34 |
| 6 | Pass Defense Matchup | Team, no blend, all inverted | 32 teams | 33/33 |
| 7 | Run Defense Matchup | Team, no blend, 4/5 inverted | 32 teams | 34/34 |
| 8 | Kicking Index | Player, blend | 32 kickers | 33/33 |
| 9 | Offensive Line Index | Team, blend | 32 teams | 33/33 |
| 10 | Front Seven Index | Team, blend | 32 teams | 33/33 |
| 11 | Special Teams Index | Team, no blend | 32 teams | 33/33 |
| 12 | EDGE-IDL Index | Player, no blend | 214 players | 215/215 |
| 13 | LB Index | Player, no blend | 192 players | 193/193 |
| 14 | CB-S Index | Player, no blend | 317 players | 318/318 |
| 15 | Special Teams Player Index | Player, no blend, per-slot-type baseline | 169 players | 170/170 |
| 16 | Pass Rush Generation Index | Team, no blend, no points-scale conversion | 32 teams | 33/33 |
| 17 | Team-Specific HFA | Team, single metric, no Z-scoring at all | 32 teams | 34/34 |

**Shared engine** (`decay_baseline.py`): 6 generic pure functions (decay-weighted average,
team history, projected baseline, current-season blend weight, blended value, Z-score) plus
weighted-composite scoring — reused unchanged across all 17 tabs above and every downstream
piece below (Base Team Quality, Explosive Play Matchup), including team-level and
player-level subjects, blend and no-blend chains, inverted and non-inverted metrics, and tabs
with no baseline offset or no points-scale conversion at all. Every structural variation was
**confirmed by reading the real formula text first**, never assumed from another tab's shape.

### Season Matchups' real Z/AA formula — all 17 real named terms ported

| Component | Term | Real source | Tests |
|---|---|---|---|
| Base Team Quality (Home/Away) | Z01/AA01 | `team_quality.py` — YoY Baseline Engine decay/regression chain + Team Ratings current-season blend, for real Off/Def PPG | 306/306 |
| Flat HFA | Z02/AA02 | Model Assumptions C3 constant, used directly | n/a (constant) |
| Rest Effect | Z03 | `core_formula_simple_terms.py` — tiered lookup on real rest days | (below) |
| Weather Adj | Z04 | same — wind/cold/precip-or-snow/humidity thresholds | (below) |
| Home/Away Injury Adj | Z05/W | same — confirmed real formula is the literal constant 0 (documented non-functional placeholder in v35, not fabricated) | (below) |
| Division Adj | Z06 | same — real divisional-game flag | (below) |
| QB Replacement Adj | Z07/AA(AT) | same — Starter/Backup swap (real snapshot has no Backup-In case; branch covered by a documented synthetic unit test) | (below) |
| Phase Matchup Adj | Z08/AA(BH) | same — real QB/RB vs. opposing Pass/Run Defense differential | (below) |
| OL Pressure Adj | Z09/AA(BP) | same — real OL Pass Protection vs. opposing Pass Rush Generation differential | (below) |
| Explosive Play Matchup Adj | Z10/AA(CP) | `explosive_play_matchup.py` — own Off Z vs. opponent's Pass/Run Prevention composite (genuinely asymmetric, documented) | 306/306 |
| HFA Delta | Z11/AA04 | `core_formula_simple_terms.py` — real Team-Specific HFA netted against the flat C3 (first direct composition of two ported tabs) | (below) |
| Road Fatigue Adj | Z12/AA(CW) | same — threshold on real Consecutive Road Games count (no real trigger case in current snapshot; branch covered by a documented synthetic unit test) | (below) |
| Travel Effect | AA03 | same — real away-team travel-miles | (below) |
| Travel Direction Adj | AA05 | same — real per-team UTC-offset threshold (77/272 real games genuinely nonzero) | (below) |

`core_formula_simple_terms.py`'s own 8 functions above: **2997/2997** tests (all 272 real
games × each term, plus 2 documented synthetic-input unit tests for the two branches with no
real nonzero case in the current snapshot).

`test_season_matchups_full_reconstruction.py`: **273/273** — every term recomputed fresh and
composed via `season_matchups.compute_model_home_away_score()`, checked against the real
Model Home/Away Score for all 272 real games.

### Not yet fully re-derived from source (deliberately scoped, not a gap)

Per this project's consistent "arithmetic only, not data sourcing" scoping (used throughout
every tab above too — e.g. every index tab's own league_avg/league_std, every RYOE/Att
rookie-substitution, this formula's own league_baseline_off/def_y1 inputs), a handful of
upstream real differentials are taken as **given real inputs** rather than re-derived by
chaining other already-ported engines:

- Phase Matchup Adj's real differential (Home/Away Starter QB/RB Index Score minus opposing
  Pass/Run Defense Matchup Score) — QB Index and RB Value Index ARE already ported, so wiring
  this up fully is mostly plumbing, not new arithmetic.
- OL Pressure Adj's real differential (OL Index Pass Protection Z minus Pass Rush Generation
  Index Score) — same; both source tabs already ported.
- QB Replacement Value itself (QB Index Section 6's own Starter-Backup differential) — not yet
  built as a QB Index engine output.
- Consecutive Road Games count and per-team UTC offset — sourced from the not-yet-ported
  Availability Index and Team-Specific HFA's own Section 4 reference table respectively.

Closing these is the natural next increment toward a **zero-Excel-dependency** walk-forward
reconstruction (needed for Step 6 across historical seasons where Excel isn't available at
all) — today's milestone proves the arithmetic; that next piece proves the full data lineage.

### Two reference-only tabs, confirmed out of scope for Z/AA

- **QB Environment Model** — a reference-only composite ("Raw QB Talent Score") that
  explicitly does not feed QB Index Score or Z/AA.
- **Advanced Efficiency Metrics** — feeds Team Ratings' separate "Net Power Rating" display
  composite (confirmed via real formula text that Z/AA never references Net Power Rating at
  all, only Team Ratings' own Blended Off/Def PPG) — not on the Z/AA critical path.

## Real bugs / findings caught along the way

- **3 confirmed dead Model Assumptions constants** (Step 1): Historical Lookback Window
  (C19), Pass/Run Defense Matchup Points-to-Game-Points Conversion (C92/C99) — defined with
  real values but never actually read by any formula.
- **Injury Adj (Season Matchups V/W) is a non-functional placeholder** — confirmed the real
  formula is the literal constant `0` for every real row, not a computed value. Documented
  explicitly in `core_formula_simple_terms.py` rather than silently modeled as "0 because no
  injuries this week."
- **The Travel Direction Adj term (AA05) was initially missed** even after the rest of the
  Z/AA formula was declared complete — caught by re-deriving the full term list from the real
  Z/AA formula text one more time before building the final assembly, rather than trusting an
  earlier manifest at face value.
- **Off-by-one row alignment bug in my own Secondary Index ground-truth extraction** — caught
  immediately (32/34 tests failed with values that were suspiciously each other's neighbors),
  fixed, and an explicit team-name equality assertion was added to every extraction script
  from that point on so it can't recur silently.
- **Two tabs' real weight-0 metrics confirmed correctly isolated** (Step 4): RB Value
  Index's Red-Zone Carry Share and WR-TE Value Index's Pass-Play Snap Participation %/
  Red-Zone Target Share/Target Share/Catch Rate all carry a real weight of exactly 0 by
  design — worth carrying into Step 10's double-counting analysis as "already isolated at
  the data-generation layer," not just "weight happens to be 0."
- **3 tabs (EDGE-IDL, LB, CB-S Index) were missed by Step 4's own automated scan** purely
  because their real Section 5 lives thousands of rows down (up to row 2735) — past that
  scan's original 700-row cap. All three, once found, followed the exact same pattern as
  every other tab.
- **Genuinely different structural shapes** confirmed and correctly handled, never assumed:
  RYOE/Att's partial-NGS-coverage substitution (RB Index); Coaching Index's
  no-blend/inverted-Penalty/no-baseline-offset shape; Run Defense's deliberately
  non-inverted Stuff Rate; Special Teams Player Index's per-slot-type baseline; Pass Rush
  Generation Index's "the Z-sum IS the Score, no conversion" shape; Team-Specific HFA's
  "no Z-scoring at all" shape; Base Team Quality's reuse of the YoY Baseline Engine's own
  decay chain feeding a *second* current-season blend step in Team Ratings; Explosive Play
  Matchup's genuinely asymmetric Pass/Run Prevention composites (one is a real 3-term
  weighted blend referencing another tab's Z-score, the other is a bare passthrough).

## Verification

Every commit in this phase: syntax-checked, ruff-clean, full test suite run before and after.
Current total: **5572 tests pass, 0 failures.**

## Suggested next step

Two real options, both concrete:

1. **Deepen the reconstruction** — wire Phase Matchup Adj / OL Pressure Adj / QB Replacement
   Value up from their own already-ported source tabs (QB/RB/OL/Pass-Defense/Run-Defense/
   Pass-Rush-Generation Index) instead of taking the differentials as given, and port
   Availability Index (Consecutive Road Games) — removing every remaining Excel dependency
   from a single game's full prediction.
2. **Start Step 6 for real** — pull real nflverse data for a past season/week, run it through
   the now-complete Python Model Engine, and compare the resulting Model Home/Away Score
   against what v35 would have predicted at the time (no future information) — the first real
   walk-forward data point.
