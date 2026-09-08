# Phase 12 — Final Mathematical Specification

**Model**: v35 baseline (tag `v35-audit-passed-hfa-fix`), exactly as validated in the Phase 0
integrity audit, with **exactly one deviation**: the HFA Delta term (Z/AA column) is fixed at
**0.0** for every game, both sides — the Phase 10-selected candidate ("HFA-A, revised, no HFA").
Every other one of the 22 real named terms — Travel, OL Index, all Z-score composite tabs,
Rest/Weather/Division/Injury/QB Replacement — is **unchanged from frozen production**. This is
deliberately the smallest possible spec deviation from a document this project has already
audited line-by-line (Phase 0), per Phase 10's own "simplest model" selection principle.

No probability calibration (Platt/isotonic) is part of this selection — Phase 8 found stacking
either onto a modified margin model made Brier worse without being refit, and Phase 10 selected
the margin-only change. Win probability uses the existing real logistic function, unchanged.

## 1. Formula shape (unchanged from v35)

```
home_score = SUM(all HOME-side real terms)
away_score = SUM(all AWAY-side real terms)
margin = home_score - away_score
home_win_probability = 1 / (1 + exp(-margin / logistic_slope))   [logistic_slope = 10.5, row C171]
```

Real, pure additive sum — no interaction terms, no term modifies another's coefficient. Ablating
one term is exactly subtracting its own value (Step 9's own real finding, still true here).

## 2. The one deviation, precisely

**HFA Delta (home) = 0.0, HFA Delta (away) = 0.0, unconditionally, every game.**

Production v35 (post Phase 0's double-counting fix) computes this as
`hfa_delta_home = regressed_team_hfa / 2` (using each home team's own real, decay-weighted,
regressed historical HFA, via `TeamSpecificHFAConstants`: decay_factor=0.5 [C20],
regression_weight=0.4 [C21], last_year_emphasis=0.3 [C22]) and `hfa_delta_away = -hfa_delta_home`.
Under this spec, both are replaced by a literal constant zero. The flat baseline constant
(`flat_hfa`, C3 = 1.5) is likewise never applied — it fed the now-removed team-specific
regression, not a separate additive term.

**Real justification** (Phase 6/7/8/9/10, already delivered): the corrected, non-double-counted
team-specific HFA was the worst of 6 real variants tested on real out-of-sample 2025 data; "no
HFA" had the best real Brier/log-loss of every candidate in Phase 8's matrix; Phase 7 confirmed
its removal is not masking a double-counting artifact (r=-0.038 vs. Base Team Quality, clean).

## 3. Every other real term — unchanged, by data-driven category

### 3a. Direct-arithmetic terms (no decay/blend/z-score machinery)

| Term | Real formula | Real coefficients |
|---|---|---|
| Rest Effect | Piecewise on rest-day differential | low_threshold=4 (C150), high_threshold=10 (C151), low_val=-1.5 (C152), mid_val=0 (C153), high_val=1 (C154) |
| Weather Adj | Piecewise on wind/cold/precip/snow/humidity | wind_threshold=15mph (C6)→-3 (C7); cold_threshold=32°F (C8)→-2 (C9); precip→-2 (C10); snow→-1.5 (C158); humidity_threshold=70% (C159)→-0.5 (C160) |
| Division Adj | Flat constant if divisional game | -1 (C11) |
| Injury Adj | Hardcoded 0.0 | N/A — confirmed literal placeholder, BLOCKED pending real AV data (Phase 5/9) |
| QB Replacement Value | Backup-in flag × replacement conversion | conversion=0.15 (C39); real 0/224 trigger rate this season (Phase 8 audit) — formula correct, real gap in live roster-status feed |
| Road Fatigue Adj | Flat penalty at ≥3 consecutive true road games | threshold=3 (C155), penalty=-1 (C156) |
| Travel Effect | miles × coefficient, home/away-relative | coefficient=0.4/1000mi (C5) — **unchanged**; the real research replacement (nonlinear distance, Travel-G) was NOT selected in Phase 10 (only HFA-A was) |
| Travel Direction Adj | West-to-east penalty flag | -0.5 (C157) |
| OL Pressure Matchup Adj | OL Index Pass Protection Z − opposing Pass Rush Generation Z | conversion=0.05 (C123) |

### 3b. Shared decay→blend→z-score→weighted-composite tabs

Every tab below follows the **same real shape** (`decay_weighted_average` → `team_history` →
`projected_baseline` → `blend_weight`/`blended_value` [current-season blend] → `z_score` →
`weighted_composite_score`), sharing decay_factor=0.5 (C20), regression_weight=0.4 (C21),
last_year_emphasis=0.3 (C22), and (where a current-season blend applies) blend_base=0.15 (C12),
blend_per_game=0.08 (C13), blend_cap=0.85 (C14). Composite scoring uses score_baseline=50 (C37),
points_per_sd=10 (C38) throughout. Only each tab's own metric weights differ:

| Tab | Real metric weights (workbook rows) |
|---|---|
| Team Quality (Base Team Quality) | Offensive/defensive EPA-based blend — see `team_quality.py`; no separate metric weight rows (decay/blend params only) |
| QB Index | EPA=0.5 (C34), CPOE=0.3 (C35), ANY/A=0.3 (C36) |
| RB Index | Rushing EPA=0.35 (C44), Rushing Success Rate=0.25 (C45), YPC=0.15 (C46), RYOE/Att=0.35 (C82), RZ Share=0.0 (C124, confirmed real dead/zero weight) |
| OL Index | Pass Protection=0.4 (C58), Run Blocking=0.35 (C59), Sack-Free Rate (Fault-Adjusted)=0.25 (C81) — **real, full 3-metric formula, requiring real FTN data (2022+)**. The degraded 2-metric stand-in built for Phase 8's 2024 secondary check is explicitly NOT part of this production spec. |
| Pass Rush Generation Index | Sack Rate=0.5 (C119), Pressure Proxy=0.35 (C120), Blitz Rate=0.15 (C121) |
| Pass Defense Matchup | EPA/Dropback=0.35 (C87), Pass Success=0.25 (C88), Completion%=0.15 (C89), NY/A=0.15 (C90), Explosive Pass=0.1 (C91) |
| Run Defense Matchup | EPA/Rush=0.35 (C94), Run Success=0.25 (C95), YPC=0.2 (C96), Explosive Run=0.1 (C97), Stuff Rate=0.1 (C98) |
| QB Environment Model | Success=0.15 (C128), Explosive=0.15 (C129), EPA=0.5 (C34), CPOE=0.3 (C35), ANY/A=0.3 (C36); New-Team Penalty=1 (C130), Recently-Injured Penalty=1 (C131) |
| Explosive Play Matchup (pass prevention) | Explosive-Pass-Allowed=0.4 (C136), Deep-Pass-Allowed=0.35 (C137), YAC-Allowed=0.25 (C138) |

### 3c. Composed/derived terms

| Term | Real formula |
|---|---|
| Phase Matchup Adj | Effective QB Rating (from QB Index + QB Environment Model + OL modifier + weather modifier) vs. opposing Pass/Run Defense Matchup, converted via pass_matchup_conversion=0.08 (C101) / run_matchup_conversion=0.06 (C102); OL/weather modifier scaling ol_modifier_scaling=0.25 (C133), weather_modifier_scaling=0.5 (C134) |
| Explosive Play Matchup Adj | Offense explosive-play tendency vs. opposing pass-prevention composite (3b) |

## 4. Real data sources, per input (walk-forward, never using data on/after kickoff)

| Source | Fetched via | Real coverage |
|---|---|---|
| Play-by-play | `nflverse_pull.efficiency.fetch_pbp` | Full nflverse pbp history |
| Schedules/results | `nflverse_pull.pull.fetch_schedules` | Full nflverse schedule history |
| PFR pass/rush (OL Index) | `nflverse_pull.oline_stats.fetch_pfr_pass/fetch_pfr_rush` | 2021+ (verified live) |
| FTN charting (OL Index Sack-Free Rate) | `nflverse_pull.oline_stats.fetch_ftn` | 2022+ (verified live: raises before) |
| NGS rushing (RB Index RYOE) | `nflverse_pull.rb_stats.fetch_ngs_rushing` | per nflverse's own real NGS coverage |
| Market lines (CLV/ATS reporting only, not the prediction itself) | `prediction_audit.market_data` (closing: nflverse; opening: aussportsbetting.com) | closing full history; opening matched 258/272 for 2025 |

**Structural, real gaps carried forward unchanged**: (1) OL Index needs target_season-3 ≥ 2022,
i.e. target_season ≥ 2025, for the full 3-metric formula — 2026 satisfies this (2026-3=2023).
(2) Weeks 1-3 of any season cannot resolve current-season QB/RB roles walk-forward (no prior
current-season data exists that early) — the model cannot produce a real prediction for those
weeks, and must not fabricate one. (3) Injury Adj and AGL remain BLOCKED — no real, sustainable
Approximate Value data source exists (Phase 5, reconfirmed Phase 7).

## 5. Excluded / rejected / blocked features — real reason, not "not included"

Full detail already delivered in Phase 9's graduation table
(`prediction_audit/phase_reports/phase9_graduation_table.md`); summarized here for this spec's
own self-containedness:

- **SOS (all 8 variants A-H)**: REJECTED — either real out-of-sample performance is worse than
  the current Base Team Quality term, or (recency-weighted G, shrinkage H) real but redundant
  (r > 0.6 against Base Team Quality/EPA/NY-A, Phase 7).
- **Travel — nonlinear distance (Travel-G)**: TESTED, real positive signal, but NOT selected —
  Phase 10 chose the simpler single-change candidate (HFA-A alone) over the combined
  Travel+HFA candidate.
- **Probability calibration (Platt/isotonic)**: TESTED, real Brier improvement in isolation, but
  not part of the Phase 10-selected candidate and not composable onto it without being refit
  (Phase 8's own finding) — a genuine, open item for a future phase, not silently dropped.
- **AGL (all variants)**: BLOCKED — no real, sustainable, free Approximate Value data source.
- **Injury Adj**: BLOCKED, by design — same real reason as AGL.

## 6. Win probability stage

`home_win_probability = 1 / (1 + exp(-margin / 10.5))` — unchanged, uncalibrated (see above).

## 7. What Phase 13 must reuse, not reimplement

- `prediction_audit/historical/full_game_prediction.py::resolve_historical_model_components()`
  — the real, already-validated 22-input resolver (with the HFA override applied as described in
  §2, the only production-code change this spec requires).
- `prediction_audit/engine/season_matchups.py::compute_model_home_away_score()` — the real
  additive-sum scorer.
- `prediction_audit/engine/market_comparison.py::win_probability_home()` — the real logistic
  function.
- `prediction_audit/historical/real_constants.py::build_real_constants()` /
  `load_real_model_assumptions()` — the real coefficient loader (unchanged).
- `capture_snapshot.py`'s immutability pattern and `verification_module.py`'s Tier 1 checks, per
  the kickoff document's own explicit instruction — for the audit-trail/database layer, not the
  prediction formula itself.

Any choice Phase 13 needs that is not covered above (e.g., how ties in a piecewise threshold are
handled, or a genuinely new edge case not seen in any of the 224+272 real games audited so far)
must be flagged, not filled with a default — per the kickoff document's own explicit constraint.
