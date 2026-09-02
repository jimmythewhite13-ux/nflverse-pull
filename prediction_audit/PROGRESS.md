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
| 4 | Component contribution manifest | **Done** (core formula + 45 weighted metrics across 11 tabs; full catalog across all tabs not yet exhaustive) |
| 5 | Market & CLV infrastructure | **Blocked** — no real historical odds source with verified timestamps (see below) |
| 6 | Historical reconstruction 2021-2025 | **Not started** — depends on the Python Model Engine (in progress below) being complete enough to run walk-forward |
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

## The Python Model Engine (`prediction_audit/engine/`)

Not one of the spec's own numbered steps by name, but the concrete piece Step 6 actually
needs to run the model programmatically at scale — re-entering data by hand for thousands of
historical game-weeks isn't practical. Built once, serves both the audit (offline
reconstruction) and, eventually, a live production system.

**Method**: for each tab, the real Excel formula chain is read directly from the frozen v35
file (never assumed from another tab's pattern), a ground-truth JSON is extracted from a real
LibreOffice recalculation (every real player/team's real inputs and Excel's own real computed
values at every step), a pure-Python module reproduces the chain, and a parity test checks
**exact match at every intermediate step** — not just the final Score — against the real
ground truth. 1e-6 floating-point tolerance throughout.

### Tabs ported and verified (16 of ~19)

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

**Shared engine** (`decay_baseline.py`): 6 generic pure functions (decay-weighted average,
team history, projected baseline, current-season blend weight, blended value, Z-score,
weighted composite score) — reused unchanged across all 16 tabs above, including team-level
and player-level subjects, blend and no-blend chains, inverted and non-inverted metrics, and
tabs with no baseline offset or no points-scale conversion at all. Every structural variation
was **confirmed by reading the real formula text first**, never assumed from another tab's
shape.

### Not yet ported (3 tabs + the core formula)

- **Explosive Play Matchup** — genuinely more complex: cross-references Pass Defense
  Matchup's and Run Defense Matchup's own real Section 5 Z-scores directly (tabs already
  ported above), rather than computing everything locally, plus a two-composite
  (Pass Prevention / Run Prevention) structure with a documented asymmetry.
- **QB Environment Model** — a reference-only composite ("Raw QB Talent Score") that
  explicitly does not feed QB Index Score.
- **Advanced Efficiency Metrics** — team-level EPA/Success Rate/NY/A composite, not yet
  investigated in this pass.
- **The core Z/AA formula itself (Season Matchups)** — where every one of the 16 ported
  Scores actually feeds into a real game prediction. This is the natural next piece: with
  16 of ~19 tabs already provably correct, wiring them into the real Z/AA chain is the
  remaining work to reproduce a full end-to-end prediction in Python.

## Real bugs / findings caught along the way

- **3 confirmed dead Model Assumptions constants** (Step 1): Historical Lookback Window
  (C19), Pass/Run Defense Matchup Points-to-Game-Points Conversion (C92/C99) — defined with
  real values but never actually read by any formula.
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
- **6 genuinely different structural shapes** confirmed and correctly handled, never
  assumed: RYOE/Att's partial-NGS-coverage substitution (RB Index), Coaching Index's
  no-blend/inverted-Penalty/no-baseline-offset shape, Run Defense's deliberately
  non-inverted Stuff Rate, Special Teams Player Index's per-slot-type baseline (one metric,
  three different populations to score against), Pass Rush Generation Index's "the Z-sum IS
  the Score, no conversion" shape.

## Verification

Every commit in this phase: syntax-checked, ruff-clean, full test suite run before and after.
Current total: **1656 tests pass, 0 failures.**

## Suggested next step

Wire the 16 already-ported tabs into a real Python reproduction of Season Matchups' own Z/AA
formula (documented component-by-component in `manifests/v35_core_formula_components.csv`),
and prove it reproduces a real game's Model Home/Away Score exactly. That closes the loop from
"every position/team score is provably correct" to "the actual game prediction is provably
correct" — the last piece needed before Step 6's walk-forward reconstruction becomes
meaningful.
