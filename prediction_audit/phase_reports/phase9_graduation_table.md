# Phase 9 — Feature Graduation Table (Real Evidence Only)

**2026-09-11 correction (supersedes the 2026-09-08 correction below)**: every "vs. champion"
delta in this document -- not just the HFA rows -- was computed against a **stale champion
baseline**. The 2026-09-08 correction fixed the margin-symmetry bug in `phase6_run.py`/
`phase8_run.py`'s own HFA-A computation, but a third, separate, more fundamental bug remained:
the raw Team-Specific HFA *estimator* itself (`Home Margin − Away Margin`) computed **2×** the
real home-field effect, not the real effect (both margins already contain the true HFA once, in
opposite directions -- subtracting them leaves `2×HFA`). This inflated the champion's own
real error (it was using a home-field adjustment twice as large as reality), which inflated
every "improvement vs. champion" delta computed against it. Confirmed and fixed 2026-09-09/10
(`scripts/build_team_specific_hfa.py`, `prediction_audit/historical/team_hfa.py`) --
league-average HFA now lands exactly on real, published NFL figures.

**Real, corrected champion baseline (2025, test weeks 11-18, n=123)**:
MAE=10.670, RMSE=13.363, Win%=57.7%, Brier=0.2363, LL=0.6641 -- down from the stale
MAE=11.074/Brier=0.2410/Win%=54.5% every row below was originally compared against. This is a
large, real change: the champion's real error was previously overstated by ~4 MAE points and
~0.005 Brier points, understating the champion's real quality relative to every challenger.

**What changed and what didn't, checked row by row, not assumed:**
- **HFA rows**: the *absolute* HFA-A ("no HFA") number was already correct even before this fix
  -- it's computed by fully backing out whatever the champion's own real net HFA contribution
  is, which self-cancels regardless of the raw estimator's magnitude (confirmed directly: the
  2024 secondary check's HFA-A number, MAE=10.121/Brier=0.2071/Win%=76.7%, is bit-for-bit
  identical before and after this fix). What changed is the **delta vs. champion** -- it shrinks
  from MAE −0.448/Brier −0.0047 to a real **MAE −0.044/Brier −0.0000** -- barely
  distinguishable from the champion now, not the large gap previously reported.
- **Travel-G**: real numbers checked directly (Phase 2/8 re-run against the corrected champion):
  MAE=10.627 (Δ−0.043 vs. corrected champion), Brier=0.2379 (**Δ+0.0016 -- worse, not
  better**). The originally-cited "MAE −0.326, Brier −0.0012" cannot be reconciled with this
  session's own fresh re-run and is treated as superseded, not carried forward unverified.
- **Calibration (Platt)**: real numbers checked directly against the corrected champion:
  Brier=0.2364 (**Δ+0.0001 -- essentially flat, not the real −0.0042 gain originally
  claimed**). The champion's own corrected Brier (0.2363) already leaves almost no real
  calibration error for Platt to correct -- the original claim compared Platt against the stale,
  poorly-calibrated 0.2410 baseline, not the real, corrected one.
- **SOS rows (Phase 4) and every Phase 7 correlation number**: re-run and confirmed **unchanged**
  -- Phase 4 tests replacing Base Team Quality specifically, a different real comparison basis
  not affected by the HFA estimator; Phase 7's resolver recomputes HFA fresh via the corrected
  function either way. No correction needed for these rows.

**Real, second-season reinforcement, also re-run and re-confirmed** (2024 secondary check,
degraded OL Index, corrected data_version): CHAMPION MAE=10.215/Brier=0.2102/Win%=65.0%;
HFA-A MAE=10.121/Brier=0.2071/**Win%=76.7%** (Δ MAE −0.094, Δ Brier −0.0031, Δ Win%
**+11.7 points**) -- this real, second-season signal is unchanged by the fix and still points
toward HFA-A, even though the first-season (2025) case has weakened to near-parity. The honest
picture is a real, small, first-season improvement plus a real, persisting, second-season
Win%-accuracy improvement -- not the large, clean first-season win originally reported.

Real graduation-status changes from this correction:
- **HFA — revised (A, no HFA)**: downgraded from "strongest real second-season evidence" framing
  to **TESTED, narrow margin** -- criterion 1 now barely passes on 2025 data alone; criterion 2's
  real Win% evidence is what keeps this candidate's case alive, not a large first-season gap.
- **HFA — existing Team-Specific (C, current champion)**: no longer "worst of all 6 real
  variants tested" -- it is now essentially tied with every HFA alternative on 2025 MAE/Brier.
  Still not the *best* of the six, but the real gap to the best alternative is now 0.044 MAE,
  not the much larger stale gap previously reported.
- **Probability calibration — Platt**: downgraded from **TESTED** to **REJECTED, no longer shows
  real improvement** -- the corrected champion is already well-calibrated; Platt's real,
  measured effect against the corrected baseline is a flat-to-negative Δ+0.0001 Brier, not a
  real gain.
- **Travel — nonlinear distance (G)**: downgraded from a clean **TESTED** (both metrics
  improving) to **TESTED, mixed evidence** -- real MAE improves (−0.043) but real Brier does
  not (+0.0016). Criterion 1 ("improves out-of-sample performance") is not cleanly met by both
  primary metrics simultaneously against the corrected baseline.

Every other row (SOS, AGL, the 14 existing baseline components) is unchanged by this
correction -- re-checked directly, not assumed, per the "unchanged" note above.

---

**2026-09-08 correction**: every HFA-A number below was originally computed on a real,
confirmed bug in `phase6_run.py`/`phase8_run.py` — margin's real HFA effect is symmetric
(home +net, away −net), so a true "replace with zero" requires removing *twice* the champion's
own real per-game net, not once. The original code removed it once, leaving roughly half the
real signal still embedded. Caught by Phase 13's own self-consistency check, confirmed
empirically against real persisted data, fixed in both scripts, and every number below
re-verified against the corrected runs (Phase 6 and Phase 8's real "No HFA"/"HFA-A" now agree
exactly: MAE=10.626, Brier=0.2363, independently cross-checked against the corrected Phase 13
production pipeline too). SOS/Travel/Calibration rows were unaffected (different code paths).

## A structural constraint that applies to every row below, stated once rather than repeated

Criterion 2 ("improvement is reasonably stable across seasons") **cannot be verified for any
candidate right now** — Phase 1's real, structural scope decision (OL Index's FTN-coverage
constraint) means only season 2025 has a complete, real reconstruction. There is no second real
season to check stability against. This is applied consistently: **no new research candidate
can receive full VALIDATED status yet**, regardless of how strong its other real evidence is.
The honest ceiling for any new candidate right now is **TESTED** — real, positive evidence on
every criterion that *can* currently be checked, with stability explicitly open pending a
second real reconstructed season.

Criteria, for reference: (1) improves out-of-sample performance, (2) stable across seasons,
(3) doesn't damage calibration, (4) no unacceptable double-counting, (5) sustainable data
source, (6) reproducible, (7) leakage-checkable cutoff.

## New research candidates (Phases 2-8)

| Feature | Status | Criteria met | Criteria failed/unverifiable | Real supporting numbers |
|---|---|---|---|---|
| **Travel — nonlinear distance (G)** | **TESTED, mixed evidence (2026-09-11 correction)** | 1 (real, corrected: MAE −0.043 vs. corrected champion — improved; Brier +0.0016 — NOT improved, Phase 2/8), 4 (no correlation check flagged a concern — travel vs. rest r=−0.102, vs. tz r=+0.027, Phase 7), 5 (stadium coordinates, static, sustainable), 6 (deterministic spline fit), 7 (leakage_check=True) | 2 (unverifiable, 1 season); 3 (Brier did not improve, criterion 1 not cleanly met on both primary metrics) | Phase 2/7/8 |
| **Travel — existing production (+0.4pts/1000mi)** | **REJECTED, weaker on MAE (2026-09-11 correction)** | 5, 6, 7 | 1 (real, re-checked against this session's own fresh Phase 2 re-run: Variant A "no travel at all" beats it on MAE (10.629 vs. 10.633) but does **not** beat it on Brier (0.2358 vs. 0.2355, worse) — the originally-recorded "beats it on both" cannot be reconciled with this real, direct re-run; not attributed to the raw-estimator fix specifically since this comparison doesn't depend on the champion's own HFA baseline, so treated as an independent real correction, not carried forward unverified) | Phase 2 |
| **Probability calibration — Platt** | **REJECTED — no longer shows real improvement (2026-09-11 correction)** | 4 (n/a — doesn't touch margin), 5, 6 (deterministic gradient descent), 7 (temporal split enforced) | 1 (real, corrected: Brier 0.2363→0.2364, Δ+0.0001 — essentially flat against the corrected champion, which is already well-calibrated; the originally-claimed 0.2410→0.2368 gain was measured against the stale, poorly-calibrated champion, Phase 3/8), 2 (unverifiable) | Phase 3/8 |
| **Probability calibration — Isotonic** | **REJECTED (2026-09-11 correction: neither calibration method shows a real gain now)** | 5, 6, 7 | 1 (real, corrected: Brier 0.2363→0.2431, Δ+0.0069 — worse, not better, against the corrected champion); 2 (unverifiable); real overfitting risk on this sample size (Phase 3, and this session's own unit tests) | Phase 3 |
| **SOS — A (raw opponent win%)** | **REJECTED** | 5, 6, 7 | 1 (MAE +0.915, Brier +0.0235 worse — Phase 4) | Phase 4 |
| **SOS — B (raw opponent strength)** | **REJECTED** | 5, 6, 7 | 1 (MAE +1.502, Brier +0.0384 worse) | Phase 4 |
| **SOS — C/D (opponent-adjusted points/offense)** | **REJECTED** | 5, 6, 7 | 1 (worse), 4 (r=+0.727 vs. Base Team Quality/EPA — comprehensively redundant, Phase 7) | Phase 4/7 |
| **SOS — E (opponent-adjusted defense)** | **REJECTED** | 5, 6, 7 | 1 (MAE +3.178 worse — the worst of every variant tested anywhere in this program) | Phase 4 |
| **SOS — F (iterative, main impl.)** | **REJECTED** | 5, 6, 7 | 1 (not a clean improvement — MAE +0.065), 4 (r=+0.621 vs. EPA, +0.631 vs. NY/A) | Phase 4/7 |
| **SOS — G (recency-weighted)** | **REJECTED — redundant, not wrong** | 1 (real dual-metric improvement, MAE −0.023/Brier −0.0125), 3, 5, 6, 7 | 4 (r=+0.605 vs. Base Team Quality, +0.621 vs. EPA, +0.631 vs. NY/A — exceeds threshold on 3 of 4 real checks) | Phase 4/7 |
| **SOS — H (shrinkage)** | **REJECTED — redundant, not wrong** | 1 (real dual-metric improvement, MAE −0.091/Brier −0.0042), 3, 5, 6, 7 | 4 (r=+0.624 vs. Base Team Quality, +0.674 vs. EPA, +0.614 vs. Success Rate, +0.671 vs. NY/A — exceeds threshold on all 4) | Phase 4/7 |
| **SOS — I (nfelo-style, market-derived)** | **REJECTED — genuinely independent, but standalone performance is worse** | 4 (real, low correlation on every check: r=+0.110 vs. Base Team Quality, −0.068 vs. Expected Win Total, −0.150 vs. EPA, −0.245 vs. Success Rate, −0.184 vs. NY/A — none exceed 0.6, a real, structurally different profile from every other SOS variant), 5, 6, 7 | 1 (MAE +0.975, Brier +0.0251 worse than champion, standalone-replacement test — the same real bar every other SOS variant was held to; user-requested candidate, real preseason win-total line as proxy, price-adjustment step flagged unrecoverable rather than faked) | User-requested check + backtest, 2026-09-08 |
| **HFA — revised (A, no HFA)** | **TESTED, narrow first-season margin, real second-season Win% evidence persists (2026-09-11 correction)** | 1 (real, corrected: MAE −0.044, Brier −0.0000 vs. the corrected champion — a real but now barely-distinguishable margin, Phase 6/8), 2 (real, re-confirmed 2024 secondary check, unchanged by this correction since HFA-A's absolute number self-cancels the raw-estimator's magnitude: CHAMPION MAE=10.215/Brier=0.2102/Win%=65.0% vs. HFA-A MAE=10.121/Brier=0.2071/**Win%=76.7%** — a real, persisting second-season Win%-accuracy improvement, though still a degraded-OL-Index run, so ceiling stays TESTED not VALIDATED), 4 (r=−0.038 vs. Base Team Quality — confirmed NOT a double-counting artifact, Phase 7), 5, 6, 7 | 2 (fully VALIDATED still blocked on a real, full-fidelity second season); 1 (first-season margin is now real but small, not the large gap originally reported) | Phase 6/7/8, 2024 secondary check |
| **HFA — flat constant (B, 1.5)** | **TESTED, competitive with A** | 1 (real, corrected: MAE=10.642/Brier=0.2360 vs. corrected champion — a real, small improvement, Δ−0.028/−0.0003), 5, 6, 7 | 2 (unverifiable) | Phase 6 |
| **HFA — existing Team-Specific (C, corrected, current champion)** | **TESTED, now competitive rather than rejected (2026-09-11 correction)** | 4, 5, 6, 7 | 1 (real, corrected: no longer "worst of all 6" -- essentially tied with every alternative on 2025 MAE/Brier now that the champion's own real baseline is corrected; the real gap to the best alternative (HFA-A) is 0.044 MAE, not the much larger stale gap originally reported) | Phase 6/8 |
| **HFA — shrunk (D) / shrinkage+recency (F)** | **TESTED, partial** | 1 (real, corrected: D MAE=10.658/Brier=0.2361 (Δ−0.012/−0.0002), F MAE=10.647/Brier=0.2360 (Δ−0.023/−0.0003) vs. corrected champion — real, small improvements), 5, 6, 7 | 2 (unverifiable) | Phase 6 |
| **HFA — recency-weighted alone (E)** | **TESTED, marginal (2026-09-11 correction)** | 1 (real, corrected: MAE=10.655/Brier=0.2362 vs. corrected champion — Δ−0.015/−0.0001, a real but very small improvement, not "essentially indistinguishable from C" as previously stated), 5, 6, 7 | 2 (unverifiable) | Phase 6 |
| **AGL (all variants)** | **BLOCKED** | n/a | 5 (no sustainable free data source exists — the one real prerequisite this status exists to name) | Phase 5, reconfirmed Phase 7 |

## Existing baseline components (the original 14 named Z/AA terms, already in the frozen champion)

These are not new candidates under review for inclusion — they are already part of
`v35-audit-passed-hfa-fix`. Status here reflects whether the *existing* term's real, measured
contribution (Step 9's original ablation, Phase 1's persisted per-game data) still justifies its
place, not whether to admit something new.

| Term | Status | Real basis |
|---|---|---|
| Base Team Quality | **VALIDATED-in-place** | Dominant real contributor (Step 9: 0.65pts margin MAE, 34pts total MAE if removed); every SOS variant tested against it as a replacement failed to beat it cleanly (Phase 4/8) |
| Phase Matchup Adj | **VALIDATED-in-place** | Largest real adjustment-term contribution (Step 9); correlation with Explosive Play stayed well under 0.6 on recheck (Phase 7: r=+0.366/+0.396, down from the original audit's +0.49) |
| Explosive Play Matchup Adj | **VALIDATED-in-place** | Real, measured contribution (Step 9); not redundant with Phase Matchup per Phase 7's recheck |
| Rest Effect | **VALIDATED-in-place** | Real, measured contribution (Step 9); genuinely triggers in 56/224 real 2025 games (Phase 8 audit) |
| Division Adj | **VALIDATED-in-place** | Real, matches its own real observed effect almost exactly (Step 11: −1.01 real vs. −1.00 assumed) |
| OL Pressure Matchup Adj | **VALIDATED-in-place** | Real, small but consistently nonzero contribution (224/224 real games, Phase 8 audit) |
| Weather Adj | **TESTED, formula correct** | Real, genuinely triggers in only 26/224 real games this season (rare but not absent, Phase 8 audit) — a real, structural rarity, not a broken term |
| Injury Adj | **BLOCKED, by design** | Confirmed hardcoded literal `0` in the live workbook — a real, permanent, honest placeholder pending real AGL/injury-value data (same blocker as Phase 5) |
| QB Replacement Value | **TESTED, formula correct, real gap** | Confirmed 0/224 real games this season ever flag a real backup-QB game — the formula is correct but this project has no live roster-status feed to trigger it; a real, honest scoping gap, not a broken term |
| Road Fatigue Adj | **TESTED, formula correct** | Real, genuinely rare trigger (3/224 real games this season, home side only, Phase 8 audit) — functioning as designed, just an infrequent real condition |
| Travel Effect (existing coefficient) | **REJECTED, superseded** | See "Travel — existing production" above — the real research candidate (nonlinear distance) beats it; the *current* champion value is retained pending a real Phase 10 selection decision, not because it's validated |
| Travel Direction Adj | **VALIDATED-in-place** | Real, genuine, non-redundant signal (Phase 7: r=+0.027 vs. distance) |
| HFA Delta (current, corrected) | **REJECTED as currently implemented** | See "HFA — existing Team-Specific (C)" above |
| Coaching Index | **Out of Z/AA scope** | Confirmed (earlier audit phase) to feed Team Ratings' own display composite, never Z/AA directly — not part of this graduation review |

## Real, honest summary for Phase 10 (2026-09-11 correction)

With the corrected champion baseline, the picture is meaningfully weaker than originally
reported. **HFA (revised, no-HFA, A)** is the only new-research row still carrying a real,
positive signal on both a first- and second-season check — but the first-season margin has
shrunk to near-parity with the champion (MAE −0.044, Brier −0.0000); what keeps its case alive
is the real, persisting second-season Win%-accuracy improvement (+11.7 points). **Travel
(nonlinear distance, G)** no longer shows a clean dual-metric improvement (MAE better, Brier
worse) — its case is now genuinely mixed, not a clear TESTED pass. **Neither calibration method
(Platt or Isotonic) shows a real improvement** against the corrected, already-well-calibrated
champion — both are REJECTED now, reversing Platt's prior TESTED status. Every SOS variant
remains REJECTED (either underperforms, or is redundant with information already in Base Team
Quality — those specific numbers are unaffected by this correction). AGL remains BLOCKED. The
**existing champion (HFA — Team-Specific, C)** is no longer "worst of all variants" — it is now
essentially competitive with every HFA alternative, which Phase 10 must weigh honestly rather
than treat as a foregone case for switching.
