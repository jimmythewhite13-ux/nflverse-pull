# Phase 9 — Feature Graduation Table (Real Evidence Only)

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
| **Travel — nonlinear distance (G)** | **TESTED** | 1 (MAE −0.326, Brier −0.0012, Phase 2/8), 3 (Brier improved, not damaged), 4 (no correlation check flagged a concern — travel vs. rest r=−0.102, vs. tz r=+0.027, Phase 7), 5 (stadium coordinates, static, sustainable), 6 (deterministic spline fit), 7 (leakage_check=True) | 2 (unverifiable, 1 season) | Phase 2/7/8 |
| **Travel — existing production (+0.4pts/1000mi)** | **REJECTED** | 5, 6, 7 | 1 (Variant A "no travel at all" beats it on both MAE and Brier — Phase 2) | Phase 2 |
| **Probability calibration — Platt** | **TESTED** | 1 (Brier 0.2410→0.2368, Phase 3/8), 3 (this *is* the calibration check), 4 (n/a — doesn't touch margin), 5, 6 (deterministic gradient descent), 7 (temporal split enforced) | 2 (unverifiable) | Phase 3/8 |
| **Probability calibration — Isotonic** | **TESTED, weaker** | 1 (real but smaller Brier gain than Platt), 5, 6, 7 | 2 (unverifiable); real overfitting risk on this sample size (Phase 3, and this session's own unit tests) | Phase 3 |
| **SOS — A (raw opponent win%)** | **REJECTED** | 5, 6, 7 | 1 (MAE +0.915, Brier +0.0235 worse — Phase 4) | Phase 4 |
| **SOS — B (raw opponent strength)** | **REJECTED** | 5, 6, 7 | 1 (MAE +1.502, Brier +0.0384 worse) | Phase 4 |
| **SOS — C/D (opponent-adjusted points/offense)** | **REJECTED** | 5, 6, 7 | 1 (worse), 4 (r=+0.727 vs. Base Team Quality/EPA — comprehensively redundant, Phase 7) | Phase 4/7 |
| **SOS — E (opponent-adjusted defense)** | **REJECTED** | 5, 6, 7 | 1 (MAE +3.178 worse — the worst of every variant tested anywhere in this program) | Phase 4 |
| **SOS — F (iterative, main impl.)** | **REJECTED** | 5, 6, 7 | 1 (not a clean improvement — MAE +0.065), 4 (r=+0.621 vs. EPA, +0.631 vs. NY/A) | Phase 4/7 |
| **SOS — G (recency-weighted)** | **REJECTED — redundant, not wrong** | 1 (real dual-metric improvement, MAE −0.023/Brier −0.0125), 3, 5, 6, 7 | 4 (r=+0.605 vs. Base Team Quality, +0.621 vs. EPA, +0.631 vs. NY/A — exceeds threshold on 3 of 4 real checks) | Phase 4/7 |
| **SOS — H (shrinkage)** | **REJECTED — redundant, not wrong** | 1 (real dual-metric improvement, MAE −0.091/Brier −0.0042), 3, 5, 6, 7 | 4 (r=+0.624 vs. Base Team Quality, +0.674 vs. EPA, +0.614 vs. Success Rate, +0.671 vs. NY/A — exceeds threshold on all 4) | Phase 4/7 |
| **HFA — revised (A, no HFA)** | **TESTED** | 1 (best of 6 real variants: MAE −0.599/−0.404 depending on comparison base, Brier −0.0076/−0.0047, Phase 6/8), 4 (r=−0.038 vs. Base Team Quality — confirmed NOT a double-counting artifact, Phase 7), 5, 6, 7 | 2 (unverifiable) | Phase 6/7/8 |
| **HFA — flat constant (B, 1.5)** | **TESTED, second-best** | 1 (beats corrected C: MAE −0.459, Brier −0.0057), 5, 6, 7 | 2 (unverifiable) | Phase 6 |
| **HFA — existing Team-Specific (C, corrected, current champion)** | **REJECTED as currently implemented** | 4, 5, 6, 7 | 1 (worst of all 6 real variants tested — beaten by both simpler alternatives) | Phase 6/8 |
| **HFA — shrunk (D) / shrinkage+recency (F)** | **TESTED, partial** | 1 (real but smaller improvement than A/B), 5, 6, 7 | 2 (unverifiable) | Phase 6 |
| **HFA — recency-weighted alone (E)** | **REJECTED** | 5, 6, 7 | 1 (essentially indistinguishable from C — real delta ≈ 0) | Phase 6 |
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

## Real, honest summary for Phase 10

The only two new-research rows carrying a real, positive, non-redundant, non-BLOCKED signal
right now are **Travel (nonlinear distance, G)** and **HFA (revised, no-HFA, A)** — both
status **TESTED**, both explicitly *not yet* VALIDATED pending a second real season. Every SOS
variant is REJECTED (either underperforms, or is redundant with information already in Base
Team Quality). AGL remains BLOCKED. Calibration (Platt) is TESTED and real, but per Phase 8's
own finding, needs refitting against whatever margin model Phase 10 actually selects — it
cannot be bolted onto a different model's probability distribution unchanged.
