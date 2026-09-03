# NFL Model v35 Validation/Audit — Progress Report

**Frozen baseline**: `NFL_Prediction_Model_v35.xlsx`
**SHA-256**: `fdd0b971df91cae905e8884258d99d4a562ebdbf8c2122259b02a54955ec3c17`
**Last updated**: 2026-09-03 (Step 6 DONE; Step 7 rerun with real Model Assumptions constants -- MAE 10.68pts, 64.3% winner-pick, 78.6% closing-line agreement)

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
| 5 | Market & CLV infrastructure | **Unblocked, real data flowing** — real historical/current market lines now ingested (see below); true timestamped CLV movement remains forward-only |
| 6 | Historical reconstruction 2021-2025 | **Done** — every real Z/AA component has a real, verified walk-forward resolver, AND `resolve_historical_model_home_away_score()` composes all of them into one real end-to-end historical Model Score, verified live twice against real, non-hand-picked past games (see below). 2 real, documented gaps remain (Travel Effect, Travel Direction Adj — no real geographic/timezone source extracted yet), both default to their real Excel blank-guard value (0.0) |
| 7 | Baseline backtest | **Real constants applied** — `backtest_step7_real_constants.py` reruns Step 7 with the REAL Model Assumptions weights/conversions (extracted live from the frozen v35 workbook, not approximated) + real per-season league stats for every tab: real MAE=10.68 pts, real winner-pick accuracy=64.3%, real closing-line agreement=78.6% (one real week — see below) |
| 8 | Walk-forward validation | Not started (depends on Step 6) |
| 9 | Ablation testing | Not started (depends on Step 6) |
| 10 | Double-counting/correlation analysis | Not started (one real finding already surfaced in Step 4 — see below) |
| 11 | Environmental calibration | Not started |
| 12 | Probability/confidence calibration | Not started |
| 13 | Model selection (A/B/C) | Not started |
| 14 | Prop tracking schema | Not started |
| 15 | Final validated spec document | Not started |

## Step 5 — real solution found and implemented

Previously documented as blocked: this project has only ever used manual, current-week
sportsbook entry, with no archive of real historical opening/closing lines with real
timestamps, and the spec's own "do not fabricate historical betting lines" principle ruled out
inventing one.

**Real unblock**: `nfl_data_py.import_schedules()` — already a project dependency, wrapped by
`src/nflverse_pull/pull.py`'s own `fetch_schedules()` — pulls `http://www.habitatring.com/games.csv`,
the free, publicly-documented historical NFL odds dataset maintained by the nflverse community
(originally Lee Sharpe's `nfldata` repo), used throughout the public NFL-analytics ecosystem.
Verified live: real `spread_line`/`total_line` are 0% null for every regular-season game,
every season 1999-2025; real moneylines are 0% null from 2010 on. The in-progress 2026 season
already carries real lines for its near-term weeks (future weeks correctly null — not a gap).

Built `prediction_audit/market_data.py` (fetch + pure-transform, same split convention as
`pull.py`) and `prediction_audit/ingest_step5_market_lines.py`, which populated the real audit
database with:
- **272 real `prediction_runs`/`predictions`** (model_version=`v35.0`,
  data_version=`python_model_engine_full_reconstruction_2026`) — the Python Model Engine's own
  fully-verified real Model Home/Away Score (see the reconstruction milestone above) plus the
  real Excel Win Probability, for every real 2026 game.
- **224 real `market_lines` rows** (112 games × spread + total, `line_stage='prediction_time'`,
  `market_data_status='VERIFIED'`, real source documented) for every game that currently has a
  real posted line; the other 160 (future weeks) correctly have no row rather than a
  fabricated placeholder.

**What this does NOT solve**: true timestamped open-to-close CLV movement. This dataset
carries one real line per game (the closing number, per its documented real-world usage), not
a full bet-placement-to-close timestamp history. The `v_clv` view still requires a real
`'closing'`-stage line to compute anything — this project can now capture that for real, going
forward, by re-running the ingestion close to each game's kickoff (a paid odds API remains the
only way to backfill true historical CLV for past seasons).

**Real finding along the way**: v35's own manually-entered "Market Spread (DK, Home)" column
(Market Comparison & Confidence) is confirmed to be a **flat placeholder** — literally `-2.5`
for every real Week 1 game and `0` for every real Week 2 game, not real per-game DK data. The
newly-ingested external source is real, per-game, and verified; this flags the workbook's own
manual entry as unreliable for market comparison, not something to build further analysis on.

**Sign convention verified** (for future work building a model-vs-market edge comparison):
the real `spread_line` field uses "positive = home favored," the same convention this
project's own `projected_margin` (home − away) already uses — no sign flip needed when
comparing them directly.

## MILESTONE — the real Z/AA formula is fully reproduced in Python, zero Excel dependency

`prediction_audit/engine/season_matchups.py`'s `compute_model_home_away_score()` composes
every real term of Season Matchups' own Z (Model Home Score) / AA (Model Away Score) formula
and, checked against all **272 real 2026 games**, reproduces the real Excel value **exactly**
(`abs=1e-6`) end to end.

That first pass (`test_season_matchups_full_reconstruction.py`) still took Phase Matchup Adj,
OL Pressure Adj, and QB Replacement Adj's real differentials as given ground-truth inputs. A
second pass (`test_season_matchups_zero_excel_reconstruction.py`) closes that gap: those
differentials are now recomputed fully from their own already-ported source engines -- QB
Index, RB Value Index, QB Environment Model, Effective QB Rating, Offensive Line Index, Pass
Defense Matchup, Run Defense Matchup, Pass Rush Generation Index -- composed together for the
first time, and checked against the same real *intermediate* Excel values (not just the final
adjustment). Real finding along the way: Washington Commanders' own real RB Value Index
Section 5 rows sit 2 rows past Season Matchups' own stale hardcoded lookup range in the frozen
v35 baseline -- the same "RB Section 5 stale-range bug" already documented and fixed in v36,
surfacing here in a different real lookup. Expected, documented, not a bug in this
reconstruction (see the findings list below).

The only real inputs still taken as given are genuine roster/data-resolution facts, not Z/AA
arithmetic: which QB/RB is the real Starter vs Backup, the real Backup-In flag, per-team real
Consecutive Road Games counts and UTC offsets (both confirmed to be real static/externally-
computed reference facts in v35 itself, not live formulas -- see below), and a real team
pass-rate share. This is the concrete deliverable Step 6 has been waiting on.

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
| 18 | QB Environment Model | Player, no blend, composes with QB Index's own Z-scores | 64 QBs | 66/66 |

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

### Phase Matchup Adj, OL Pressure Adj, QB Replacement Adj -- now fully re-derived from source

Previously documented here as "not yet fully re-derived" -- closed in the zero-Excel-dependency
milestone above. `effective_qb_rating.py` composes QB Environment Model's own Adjusted Baseline
with an OL-Pressure-scaled modifier (reusing the same BK/BN differential Z09/AA's own OL
Pressure Adj uses directly -- read twice for two different purposes, not circular) and a
Weather-on-Passing modifier; `qb_index.py`'s own `replacement_value_index_points()`/
`replacement_value_game_points()` compute QB Replacement Value from QB Index's own real
Starter/Backup scores. All composed and checked against the real intermediate Excel values for
all 272 games in `test_season_matchups_zero_excel_reconstruction.py`.

### Still taken as given real inputs (confirmed genuinely out of "arithmetic" scope, not a gap)

Per this project's consistent "arithmetic only, not data sourcing" scoping (used throughout
every tab above too — e.g. every index tab's own league_avg/league_std, every RYOE/Att
rookie-substitution, this formula's own league_baseline_off/def_y1 inputs):

- Which QB/RB is the real Starter vs Backup for each team, and the real Backup-In flag --
  roster/depth-chart facts, not Z/AA arithmetic.
- **Consecutive Road Games count and per-team UTC offset -- confirmed to be real static/
  externally-computed reference facts, not live Excel formulas at all.** Investigated while
  scoping this section further: Availability Index's own real Section 2b header states
  Consecutive Road Games is "a real, Python-computed count... not a live formula (no clean
  single-cell Excel formula exists for 'the N most recent rows')" -- it's pasted in as a value
  by that tab's own build script, not derived from a cell formula. Team-Specific HFA's own
  Section 4 UTC Offset table is explicitly labeled "public, unchanging facts." Neither has any
  further Z/AA arithmetic to port; both are correctly scoped as given inputs, same as every
  other tab's own league_baseline_y1.
- The real team pass-rate share Effective QB Rating's Weather-on-Passing modifier needs -- a
  real data-aggregation ratio (SUMIFS over QB Environment Model + RB Value Index), not Z/AA
  arithmetic.

### One reference-only tab; one previously-mis-scoped tab, now corrected

- **Advanced Efficiency Metrics** — feeds Team Ratings' separate "Net Power Rating" display
  composite (confirmed via real formula text that Z/AA never references Net Power Rating at
  all, only Team Ratings' own Blended Off/Def PPG) — not on the Z/AA critical path. Confirmed
  genuinely out of scope.
- **QB Environment Model — CORRECTION, this tab is NOT out of scope.** Earlier documented here
  as "reference-only... does not feed QB Index Score or Z/AA." That was wrong, caught while
  investigating the Phase Matchup Adj differential more closely (see above): QB Environment
  Model's own real Adjusted Baseline output DOES feed Z/AA, via the real Effective QB Rating
  chain. It does NOT feed QB Index Score itself (that half of the original claim holds) — the
  error was claiming it doesn't reach Z/AA at all. Left here as a direct correction rather than
  silently editing the earlier claim away.

## Market Comparison & Confidence -- Parts A and B fully ported

With the real Model Home/Away Score fully reproducible, this tab converts that into what a
user actually looks at: a win probability and a confidence read.

- **Win Probability (Home)** (`market_comparison.win_probability_home()`) -- a real standard
  logistic transform of the real Model Margin, with a real tunable calibration constant
  (C171 = 10.5 pts per logit in v35). 272/272 real games, exact match.
- **Confidence Composite** (`confidence_composite.py`) -- 4 real components (Sample Size,
  QB/Override Certainty, OL Center Continuity, Matchup Agreement), weighted-summed into a real
  0-1 composite and bucketed into a real tier. Matchup Agreement compares 3 real Net Home
  Advantage differentials against the overall Model Spread's real sign, replicating Excel's own
  `SIGN()` semantics exactly. The other 3 components read real roster facts (games played,
  Backup-In status, QB Index's own real Manual Roster Override table -- currently empty for
  every team, OL Index's own real starting-Center rookie status -- genuinely true for 2 of 32
  real teams). 272/272 real games, exact match (tier is an exact string match too).
- **Net Home Advantage columns** (`net_home_advantage.py`) -- Rest/Injury/QB-Repl/HFA-Delta/
  Road-Fatigue/Travel-Direction, each a real subtraction or negation of a term already proven
  correct elsewhere (Phase/OL-Pressure/Explosive-Play's own Net Home Advantage are the same
  family and already covered by Confidence Composite's own inputs). 272/272 real games.
- **Model WP -> ML** (`market_comparison.model_win_probability_to_moneyline()`) -- the real
  American-odds conversion of the model's own real win probability. 272/272 real games.

**Deliberately not ported, and why (a real stopping point, not an oversight):**
- **Moneyline Edge system** (Raw/De-Vigged Implied Probability, Moneyline Edge) -- Season
  Matchups' own real Home/Away Moneyline input cells are confirmed **blank for every one of
  the 272 real 2026 games** (no manual entry was ever made). Unlike several earlier terms with
  a documented zero-coverage *branch*, this whole system has zero real Excel-computed value at
  any level to verify against -- porting it would mean building untestable machinery, not
  closing a gap.
- **Kalshi/Polymarket contract prices and edges** -- confirmed blank for the same reason
  (manual entry only, never filled in), and separately carry a real, active legal-availability
  caveat per this tab's own opening disclaimer (event-contract sports markets under unresolved
  dispute in multiple US states as of mid-2026).
- **The Explanation Engine's own Primary/Secondary/Risk text-label selection** (Same-Side/
  Opposite-Side classification feeding a ranked, formatted string like `"Rest: +2.3 pts"`) --
  real and tractable, but a labeling/ranking system over already-computed values, not new
  predictive arithmetic. Lower value relative to the effort remaining, given everything above
  it is now complete.

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
  weighted blend referencing another tab's Z-score, the other is a bare passthrough);
  QB Environment Model's own Talent Score blending 2 locally-computed Z-scores with 3
  live-referenced from QB Index; Confidence Composite's Matchup Agreement replicating Excel's
  own real `SIGN()` semantics (`SIGN(0)=0`) rather than a naive `>0` check.
- **Washington Commanders' real Starter RB lookup hits the same "RB Section 5 stale-range
  bug" already fixed in v36** -- their real RB Value Index Section 5 rows sit 2 rows past
  Season Matchups' own stale hardcoded lookup range, in all 17 of their real 2026 games. v35 is
  deliberately frozen for this whole audit, so this is an expected, already-documented
  limitation of the baseline, confirmed again in a new real lookup while building the
  zero-Excel-dependency reconstruction -- not a bug in that reconstruction, which correctly
  computes Washington's own real (non-blank) value using RB Value Index's real, wider range.
- **v35's own "Market Spread (DK, Home)" column is a flat placeholder**, and its real
  Home/Away Moneyline input cells are blank for every one of the 272 real 2026 games -- neither
  was ever really populated with per-game manual entry, confirmed while sourcing Step 5's real
  external market data and porting Market Comparison & Confidence's own Moneyline system.

## Step 6 — component layer complete: every real Z/AA term has a real walk-forward resolver

**All 16 real components of the Z/AA formula now resolve for an arbitrary real historical
target** (`prediction_audit/historical/`), each verified live against real, non-adjacent
targets (not one cherry-picked game) with real, plausible values:

| # | Component | Shape | Real finding along the way |
|---|---|---|---|
| 1 | Base Team Quality | Team, blend | — |
| 2 | Rest Effect / Division Adj | Direct arithmetic | — |
| 3 | Weather Adj | Direct arithmetic | Honestly partial — no real snow/precip/humidity source |
| 4 | Team-Specific HFA | Team, no blend | Franchise-relocation abbreviation fix (OAK/SD/STL) |
| 5 | QB Index | Player, blend | Live workbook's "Current Season" is a manual input, not auto-computed |
| 6 | RB Value Index | Player, blend | Real NGS null-team-abbr rows filtered |
| 7 | Kicking Index | Player, no blend | — |
| 8 | Front Seven Index | Team, blend | — |
| 9 | Secondary Index | Team, blend | — |
| 10 | EDGE-IDL Index | Player, no blend | 4-source real data join (pbp+snaps+crosswalk+rosters) |
| 11 | LB Index | Player, no blend | Real Tackles+TFL merge |
| 12 | CB-S Index | Player, no blend | — |
| 13 | WR-TE Value Index | Player, blend | New real role convention (no prior precedent); real NGS null-team-abbr fix again |
| 14 | Special Teams Player Index | Player, no blend | Real small-population guard (KR: only 1 real qualifying player 2021-2023) |
| 15 | OL Index | Team, blend | Real FTN-coverage constraint (targets before 2025 can't resolve all 3 metrics) |
| 16 | Pass/Run Defense Matchup, Pass Rush Generation, Coaching Index, QB Environment Model, Explosive Play Matchup | Team, no blend | Coaching Index is coach-keyed, not team-keyed; QB Environment Model composes the QB Index resolver directly; Explosive Play Matchup composes Pass+Run Defense Matchup |

**What's NOT yet done**: composing all 16 into one real end-to-end historical GAME prediction
— i.e., a `resolve_historical_model_home_away_score(season, week, home_team, away_team)`
mirroring `season_matchups.py`'s own real `compute_model_home_away_score()`, but sourced from
this historical layer instead of the frozen 2026 Excel snapshot. Each component is proven
correct in isolation; wiring them together (including the Phase Matchup Adj / OL Pressure Adj
/ QB Replacement Adj cross-references between indices, and Effective QB Rating's own
OL-modifier/weather-modifier composite) is real, mostly-plumbing integration work, not new
data-resolution problems — every real data source it needs already exists in this layer.

### Per-tab detail

`prediction_audit/historical/` is the real historical data-resolution layer Step 6 needs,
started this session. Confirmed live: the raw per-team/per-season data most of these terms
need is **already free and already flowing** through this project's own existing code
(`nflverse_pull.pull`'s `fetch_schedules()`/`transform_to_team_season()`/
`compute_team_season_home_away_splits()`, built for the live 2026 pipeline but genuinely
reusable for any historical season) — Step 6 did not need a from-scratch historical data
pipeline for these terms, just week-aware wrappers around what already existed.

**Real terms with a working historical walk-forward, verified against real, non-adjacent
targets (not just one cherry-picked game):**
- **Base Team Quality** (`team_ppg.py` + `walk_forward.py`) — real Y1/Y2/Y3 (3 full prior
  seasons) + real current-season-so-far PPG, with a strict `through_week` no-future-information
  guard (`week < target_week`, never `<=`).
- **Rest Effect** and **Division Adj** (`game_context.py`) — nflverse's own real per-game
  `home_rest`/`away_rest`/`div_game` fields, 0% null every season, wired directly into the
  already-proven arithmetic. No caveats.
- **Weather Adj** (`game_context.py`) — real but honestly PARTIAL: nflverse has real
  `roof`/`temp`/`wind` but no `snow_flag`/`precip_flag`/`humidity` field at all for any
  historical season (those are the live pipeline's own manually-entered current-week-only
  inputs). The wind/cold-threshold portion is computed for real; snow/precip/humidity are
  excluded outright, not defaulted to "none" (returns `None`, not a fabricated `0.0`, for a
  real outdoor game where nflverse's own temp/wind happen to be null too — ~21-25% of such
  games in 2021-2023).
- **Team-Specific HFA** (`team_hfa.py`) — real Y1/Y2/Y3 raw HFA (Home Margin − Away Margin) via
  `compute_team_season_home_away_splits()`; no current-season blend exists for this tab, so no
  `through_week` logic is needed here at all. Verified against 2 real non-adjacent targets
  (2024 New Orleans Saints: 4.24; 2022 Seattle Seahawks: 3.26), both plausible against the real
  ~4.18 2025 league-wide average confirmed when this tab was first ported.

**Real finding along the way**: a 2022-target walk-forward needs Y2=2020 data, which still
uses nflverse's real pre-relocation abbreviations (`OAK` before the 2020 Raiders move, etc.) —
running the demo against that target raised a real "no mapping" error rather than silently
using stale/wrong data. Fixed with `relocations.py`, which normalizes `OAK`→`LV`, `SD`→`LAC`,
`STL`→`LA` at the raw-abbreviation level (real franchise continuity) before any downstream
processing, so every consumer — this package's own functions and nflverse_pull's shared ones
alike — works unchanged.

**QB Index** (`qb_index_historical.py`) — the first real player-level index made walk-forward-
capable, and the template for the rest. Reuses `nflverse_pull.qb_stats`'s own already-real,
already-parameterized `compute_team_season_qb_stats`/`compute_qb_roles` (built for the live
pipeline, works unchanged for any historical years). Two real findings from reading the live
pipeline's own code before building this: (1) QB Index's "Current Season" cells are real
MANUAL inputs in the live workbook (hand-typed weekly), not auto-computed from pbp at all — a
walk-forward target has no user to type that in, so it's computed for real from historical pbp
restricted to weeks before the target instead; (2) Section 4's real league avg/std must be
computed over the BLENDED metric (post current-season blend), not the pre-blend baseline, per
`current_season_blend.py`'s own docstring — `resolve_qb_index_league_stats()` runs every real
league-wide qualifying Starter/Backup through the full decay→blend chain before averaging.
Real historical Starter/Backup resolution reuses `compute_qb_roles()`'s own real dropback-
ranking method — confirmed via `build_qb_index.py`'s own docstring to be this project's OWN
documented historical-proxy fallback, not a new invention — applied to the target season's own
real dropbacks-so-far. Verified live (2024 week 10): real league-wide EPA/CPOE/ANY-A avg/std
all in plausible real NFL ranges, feeding real per-team scores (New Orleans Saints
starter=54.46, Atlanta Falcons starter=53.84) both near the real 50-point baseline as expected.

**RB Value Index** (`rb_index_historical.py`) — second player-level index, following QB
Index's exact pattern but more involved: 5 real metrics instead of 3, two needing extra real
data sources beyond pbp (real NGS rushing data for RYOE/Att; real red-zone-carry pbp
aggregation for Red-Zone Carry Share, whose real weight is 0 — included for completeness, not
because it affects any real score). Real finding: real NGS rushing data has a small number of
season-aggregate rows (7/149 in 2021) with a null `team_abbr`, among them several real notable
backs (Najee Harris, Nick Chubb, Jonathan Taylor) — filtered out in this module rather than
touching the shared `nflverse_pull` function, so that player-season's RYOE correctly becomes
unresolvable via the real never-fabricate path instead of crashing. RYOE/Att's own real v35
rookie-substitution logic is explicitly NOT replicated (a real missing RYOE season raises, same
as any other missing metric). Verified live (2024 week 10) on BOTH real code paths: Baltimore
Ravens' real starter (Derrick Henry, score=65.93) resolves successfully; several other real
2024 starters (young backs without 3 full real prior qualifying seasons — Atlanta's, San
Francisco's) correctly raise rather than fabricate a substitute for missing rookie-era history
— a real, expected limitation (young feature backs are common in the NFL), not a bug.

**Kicking Index** (`kicking_index_historical.py`) — third player-level index, and the
simplest yet: a single real role per team (K1 — no Starter/Backup binary; there's no second
roster kicker to swap in, per `build_kicking_index.py`'s own docstring), real league baseline
over ALL qualifying rows (no Role filter needed, unlike QB/RB), all 3 real metrics from one
already-real function (`compute_team_season_kicking_stats`). No pre-existing role-ranking
helper exists for kickers in this project, so this module defines its own — same real
volume-ranking spirit as QB/RB (most real FG Attempts-so-far this season = K1). Verified live
(2024 week 10): real league-wide FG%/XP%/FG%OE all in plausible real NFL ranges; Pittsburgh's
real K1 (Chris Boswell, a real elite kicker that season) resolves to score=63.01, a real
above-average result consistent with his real form.

**Front Seven Index** (`front_seven_historical.py`) and **Secondary Index**
(`secondary_index_historical.py`) — fourth and fifth indices made walk-forward-capable, and
simpler than any player-level one: both TEAM-level (like Base Team Quality/Team-Specific HFA),
so no role resolution is needed at all. Each reuses one already-real, already-parameterized
`nflverse_pull.defense_stats` function (`compute_team_season_front7_stats`/
`compute_team_season_secondary_stats`) — a full-season team rate stat with no per-player
qualifying threshold. Verified live (2024 week 10): real league-wide stats in plausible real
NFL ranges for both (sack rate avg=7.1%, TFL rate avg=2.8%, QB hit rate avg=15.4%; INT rate
avg=2.0%, PBU rate avg=11.4%); every real team tested resolved cleanly with no missing-data
errors — team-level stats have none of the rookie/partial-history coverage gaps player-level
indices hit.

**Real finding, OL Index scoped as harder than the others**: checked OL Index's own real data
source (`nflverse_pull.oline_stats`) before starting it — 2 of its 3 real metrics need PFR
data (fine, covers 2021+), but the third (Sack-Free Rate, Fault-Adjusted) needs real FTN
charting data, which **`nfl_data_py.import_ftn_data` raises "Data not available before
2022"** — verified live. This means OL Index walk-forward targets before season 2025 (needing
Y-3 ≥ 2022) can't resolve all 3 metrics for real — a genuine, real scoping constraint, not yet
worked around (deferred rather than silently dropping the third metric or fabricating a
substitute for pre-2022 years).

**EDGE-IDL, LB, and CB-S Index** (`edge_idl_index_historical.py`/`lb_index_historical.py`/
`cb_s_index_historical.py`) — 6th/7th/8th indices, the first defensive PLAYER-level ones.
Genuinely simpler than QB/RB/Kicking in one respect: none of these 3 tabs has a current-season
blend step (confirmed when each was first ported), so no `through_week`/partial-season logic
is needed — just real Y1/Y2/Y3 (3 full real prior seasons) + a real league baseline/avg/std.
Real data assembly needs 4 real sources joined together per tab, via
`nflverse_pull.defense_stats`'s own already-real functions: real per-player raw counts
(`compute_player_season_front7_stats` for EDGE-IDL's Sacks/TFL/QB-Hits; a real merge of
`compute_player_season_tackle_stats` + `compute_player_season_front7_stats` for LB's
Tackles+TFL; `compute_player_season_secondary_stats` for CB-S's INT/PBU) + real per-player
defensive snaps (`fetch_snap_counts`/`fetch_player_ids`, PFR-sourced, cross-walked to this
project's gsis_id) + real seasonal rosters, run through the SAME shared
`compute_player_season_defensive_rates` (the real 200-snap qualifying threshold + rate
conversion, used identically by all 3). All 3 modules deliberately do NOT resolve "who is
starting" — each tab's real population is every player who could appear at any of several real
slots (current_roster.py's own per-slot logic), a genuinely different, harder resolution
problem than a single volume rank, deliberately deferred; each takes a specific real player_id
(however sourced) and resolves their own real historical score. Verified live (2024, real pbp +
snap counts + player-ID crosswalk + rosters): real league-wide per-snap rates all plausible
(EDGE-IDL sack rate avg=0.43%, TFL rate avg=0.78%, QB hit rate avg=0.99%; LB tackle rate
avg=6.5%, TFL rate avg=0.69%; CB-S INT rate avg=0.13%, PBU rate avg=0.70%) — real players
sampled from each all resolved to real, spread scores around the 50-point baseline.

**WR-TE Value Index** (`wr_te_index_historical.py`) — ninth index, and the first with a
genuinely NEW role-resolution design. This project has NO pre-existing historical-role
convention for WR-TE at all (checked before starting — `build_wr_te_index.py`'s own docstring
confirms "Section 1 has NO historical Role/label column"), and the live pipeline scores 4 real
roles per team (WR1/WR2/WR3/TE1) from real LIVE depth-chart data, which has no meaning for an
arbitrary past date. **This module's own real, documented convention** (not previously
established elsewhere): rank each team's real WRs by real Targets-so-far — top 3 =
WR1/WR2/WR3; separately rank real TEs the same way — top 1 = TE1. Same real volume-ranking
spirit as QB/RB/Kicking's own conventions, applied per-position-group using real Position from
nflverse's own seasonal rosters. Of the tab's 9 real metrics, 4 carry a real weight of 0 by
design (confirmed in Step 4) — computing them for real needs 3 more real data sources beyond
what the other 5 already need, and since they're mathematically inert for the real Score, this
module defaults them to a documented 0.0 placeholder rather than building that pipeline now (a
real walk-forward of Player Prop Projections specifically would need to revisit this). Real
finding: the same systemic real NGS null-team-abbr quirk RB Index's RYOE fix already caught
also affects NGS receiving data — fixed the same way. Verified live (2024 week 10): real role
ranking confirmed correct; multiple real successes (San Francisco's real WR1 score=70.03,
Detroit's real WR1 score=70.74 — both real elite receivers) alongside many correct honest
raises for real young WR3/TE1 depth players without 3 full real qualifying NGS seasons.

**Special Teams Player Index** (`special_teams_player_index_historical.py`) — tenth index. No
current-season blend step exists for this tab, so no `through_week` logic is needed for the
player's own metric — real Y1/Y2/Y3 + a real per-slot-type (P/KR/PR) league baseline/avg/std,
each scored against its OWN real population. No pre-existing role-ranking helper exists for
these slots either — same real volume-ranking convention as everywhere else (most real
Punts/Returns-so-far = that team's real P/KR/PR). **Real finding, not a bug**: verified live
that only 1 real player had a qualifying KR season in ALL of 2021/2022/2023 simultaneously —
kick returner is a genuinely volatile role, and the real degenerate population (n=1, std=0.0)
would silently produce a ZeroDivisionError downstream; added an explicit guard that raises a
clear, real error instead.

**OL Index** (`offensive_line_index_historical.py`) — eleventh and final index. Enforces the
real FTN-coverage constraint documented earlier (target seasons before 2025 can't resolve all
3 metrics) by raising a clear, real error rather than silently dropping the third metric. Real
correctness fix caught during development: an early draft paired a real nonzero
`games_played` with a placeholder `current_season=0.0`, which would have silently biased the
blended value toward 0 through `blend_weight()`'s own real formula — fixed by forcing
`games_played=0` explicitly (PFR's own real data has no week-level granularity to build a
genuine current-season blend from anyway).

**All 11 real indices are done.** Extending to the 5 matchup tabs that depend on them:

- **Pass Defense Matchup** / **Run Defense Matchup** — team-level, no current-season blend.
  Metric inversion (5/5 and 4/5 metrics respectively) is handled inside the already-Excel-
  proven engine functions themselves; these modules feed real, non-inverted raw values. Both
  reuse the same real `compute_team_season_matchup_metrics` function; Pass Defense also merges
  in real NY/A Allowed from `compute_team_season_efficiency`.
- **Pass Rush Generation Index** — team-level, no blend. Sack Rate and Pressure Proxy (QB Hit
  Rate) reuse the SAME real team-level function Front Seven Index already uses; Blitz Rate
  comes from real nflverse participation data (`number_of_pass_rushers >= 5`).
- **Coaching Index** — genuinely different from every other tab: the real underlying data is
  keyed by (Coach, Season, Team), not Team alone — a coach's own real Y1/Y2/Y3 history follows
  THAT PERSON across a real team change. Real current-coach resolution reuses
  `compute_current_coach_by_team()` directly (already real, parameterized by season). **Real
  finding**: `compute_coach_season_stats`'s own Penalty Rate division has no `fillna(0)` on
  the numerator first — a coach with a real, genuine ZERO penalties in a season comes back as
  NaN, not 0.0 (a pandas index-alignment artifact). This module's existing never-fabricate
  handling already treats that correctly; documented for whoever next touches
  `coaching_stats.py` directly, not patched there in this pass.
- **QB Environment Model** — the tab this project's own PROGRESS.md previously (incorrectly)
  documented as out of scope for Z/AA, before a real correction found it DOES feed Season
  Matchups via Effective QB Rating. Reuses the already-built QB Index resolver directly for
  its real EPA/CPOE/ANY-A Z-score references. Two scoped inputs: `new_team_this_season` is
  computed for real; `recently_returned_from_injury` defaults to False (no free reliable real
  source identified — documented as a real, honest limitation, since this one is NOT
  weight-0).
- **Explosive Play Matchup** — the tab flagged from the start as genuinely harder: composes 3
  already-built real resolvers (this team's own real Pass/Run Defense Matchup results supply
  the real Z-score references its own formula live-references), plus 2 more real metrics from
  already-parameterized `nflverse_pull.efficiency` functions (real Deep Pass Completion Rate
  Allowed, real YAC Allowed).

**Every tab in `v35_core_formula_components.csv`/`v35_all_weighted_components.csv` now has a
real, verified walk-forward resolver.**

### Full composition — the actual Step 6 deliverable

Beyond the per-component layer above, `full_game_prediction.py`'s
`resolve_historical_model_home_away_score()` composes all of them into one real, end-to-end
historical Model Home/Away Score for an arbitrary real past game — the same real summation
`season_matchups.py` itself uses, sourced from real historical nflverse data instead of the
frozen 2026 Excel snapshot. Real sub-compositions built to get there: **QB Replacement Value**
(reuses the QB Index resolver for both Starter and Backup, diffs their real scores), **Road
Fatigue Adj** (a real consecutive-road-games count computed directly from nflverse's own real
schedule — previously scoped as a given input, now genuinely computed), **OL Pressure Adj**
(OL Index Pass Protection Z vs opposing Pass Rush Generation Score), **Effective QB Rating**
(QB Environment Model + a real OL modifier + a real weather-on-passing modifier, the latter
using a real, honest pass-rate-share proxy computed from pbp rather than the exact real SUMIFS
formula), **Phase Matchup Adj** (Effective QB Rating and RB Index vs the opponent's real
Pass/Run Defense Matchup Score), and **Explosive Play Adj** (composing the already-built
Explosive Play Matchup resolver for both teams).

Two real, honestly-scoped gaps remain, documented rather than fabricated around: **Travel
Effect** (needs real stadium-to-stadium distance) and **Travel Direction Adj** (needs real
per-team UTC offsets) have no real historical resolver built yet — no real, verified
geographic/timezone data source was identified and extracted this session. Both default to
their real Excel blank-guard value (0.0), exposed as explicit optional overrides. Coaching
Index is deliberately excluded from this composition — confirmed real formula text shows it
feeds Team Ratings' own Net Home Advantage/display composite, never Z/AA directly.

**Real bug caught and fixed during live verification, not after**: an early version of the
composer passed only the CURRENT season's real schedule into Base Team Quality's own
resolver, which genuinely needs 3 full real prior seasons from the SAME DataFrame — it
correctly raised rather than silently using a truncated real history, surfacing the bug
immediately. Fixed by combining the data bundle's own two real schedule slices before that
one call.

**Verified live end-to-end, twice, with a programmatically-selected target (never
hand-picked)**: San Francisco @ LA Rams (2025 week 10) — real Model Score 25.70-22.45, +3.25
real home margin; Arizona @ Seattle (2025 week 10, first real game of that week by real
game_id sort order) — real Model Score, Seattle 25.88-22.68, +3.20 real home margin (real
actual result: Seattle won 44-22, directionally consistent with the real prediction favoring
Seattle).

## Step 7 — real preliminary baseline backtest

`backtest_step7_baseline.py` runs the Step 6 composer against every real REG game in one real
target week (not a hand-picked subset), compares each real predicted margin against the real
actual margin and the real closing line (Step 5's own real habitatring.com source, fetched
fresh for the target season), and reports real aggregate metrics.

**Real, honest scoping**: this reuses `demo_full_game_prediction.py`'s own real, plausible
Model-Assumptions-style constants (`build_demo_constants()`) — representative values matching
what this session's own individual resolver verifications found sane throughout, NOT freshly
re-extracted from a live Model Assumptions sheet. Treat the numbers below as a real, honest
proof the pipeline works end to end, not a final validated accuracy figure. A production Step
7 run should pull these constants from the real frozen v35 Model Assumptions sheet directly,
and should cover many real weeks/seasons, not one.

**Real result** (all 14 real REG games, week 10 2025 — every game that week, not selected):

| Metric | Real value |
|---|---|
| MAE vs real actual margin | 10.60 points |
| Real winner-pick accuracy | 71.4% (10/14) |
| Real directional agreement with the real closing line | 71.4% (10/14) |

All three are real, plausible results for a preliminary NFL margin-prediction model — genuinely
in the range a reasonable real model should land in, not a red flag in either direction (an MAE
near 0 or an agreement rate near 100% with the real closing line would have suggested a bug,
e.g. the model accidentally leaking the real line itself into its own prediction).

### Rigor fix — real Model Assumptions constants, not representative ones

`real_constants.py` extracts the REAL weight/conversion/threshold constants directly from the
frozen v35 workbook (a live read, never hardcoded), replacing the representative constants
above. `league_avg`/`league_std` stay correctly separate — real, per-target-season COMPUTED
values (each tab's own real Section 4), resolved via this package's own
`resolve_*_league_stats()` functions, not extracted from the workbook.

**Real corrections this caught**, documented rather than silently fixed: QB Index's real
ANY/A weight is 0.3 (the representative version used 0.2); QB Index's real Points-to-Game-
Points Conversion (C39) is 0.15 (the representative version used 0.3); RB Index's real
RYOE/Att weight (C82) is 0.35 (the representative version used 0.2); several Pass/Run Defense
Matchup and Explosive Play Matchup weights were off by smaller amounts. Also confirmed C92/C99
really are the dead constants Step 1 found — those tabs' own Score conversion uses the
standard C37/C38 instead.

**Real result with the corrected constants** (same real target — all 14 real week-10 2025
games):

| Metric | Representative constants | Real constants |
|---|---|---|
| MAE vs real actual margin | 10.60 pts | 10.68 pts |
| Real winner-pick accuracy | 71.4% (10/14) | 64.3% (9/14) |
| Real closing-line agreement | 71.4% (10/14) | 78.6% (11/14) |

Small sample (n=14), so these shifts aren't individually meaningful — the real value of this
fix is confirming the pipeline is robust to the real corrected constants (not a lucky
coincidence with the earlier approximations), and every real per-tab league-wide stat (QB EPA,
RB rushing EPA, OL pass protection, Pass/Run Defense Matchup rates, etc.) landed in a real,
plausible NFL range.

## Tracked but paused — The Odds API integration (Part A blocked, not abandoned)

A full spec for automating DraftKings/FanDuel/BetMGM/Caesars line entry via The Odds API
(explicitly NOT MyBookie, which stays 100% manual — offshore book, scraping/credential access
both ruled out) arrived this session. Real blocker: Part A requires checking real coverage
(props tier, season-win-totals tier, book presence) against a real API key, and creating an
Odds API account is outside what this assistant can do on its own (account/credential creation
is off-limits regardless of authorization) — the user chose to hold this and continue Step 6
instead. Prep work already done: `.gitignore` now excludes `.env`/`.env.*`/`*.local.json` so a
future key can never be accidentally committed. **Next step when resumed**: the user provides
a real Odds API key (existing or newly signed-up), then Part A's 3 real coverage questions get
checked against real response data before any pull code is written.

## Verification

Every commit in this phase: syntax-checked, ruff-clean, full test suite run before and after.
Current total: **10164 tests pass, 0 failures.**

## Suggested next step

Four real options, all concrete:

1. **Scale up the Step 7 backtest** — run `backtest_step7_real_constants.py` across many real
   weeks/seasons instead of one, and persist the results into the Step 2 database (the schema
   already supports it) instead of printing them, so Steps 8-9 (walk-forward validation,
   ablation) have a real, queryable base to work from.
2. **Fill the 2 remaining real gaps** — Travel Effect (real stadium-to-stadium distance) and
   Travel Direction Adj (real per-team UTC offsets) still default to 0.0. A real, free
   stadium-coordinates source would need to be found and verified the same way every other
   real data source in this project was.
3. **Keep Step 5's forward-CLV loop running** — re-run `ingest_step5_market_lines.py` close to
   each week's kickoffs to capture real `'closing'`-stage lines; the `v_clv` view starts
   returning real rows the first time a game has both a real `'prediction_time'` and a real
   `'closing'` line captured.
4. **Resume the Odds API integration** — once a real key is available, verify Part A's 3
   coverage questions for real before writing any pull code.
