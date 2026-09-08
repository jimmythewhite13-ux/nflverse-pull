# Phase 8 Secondary Check — Real 2024 Season (Degraded OL Index)

**2026-09-08 correction**: every HFA-A number below was originally computed on a real, confirmed
bug (`phase8_2024_run.py`'s `hfa_A_home_net_delta`, same root cause as `phase8_run.py`'s —
margin's real HFA effect is symmetric, so a true zero requires removing twice the champion's
own real per-game net, not once). Fixed and re-run; every number below is the corrected result.
Travel-G's own numbers are unaffected (different code path, doesn't touch HFA).

**Not comparable 1:1 to the real 2025 Phase 8 numbers** (2024 uses a degraded, 2-of-3-metric OL
Index — see [ol_index_degraded_pre2025.py](../research/ol_index_degraded_pre2025.py) —
since 2024 fails OL Index's real FTN-coverage constraint). Compare *relative order and sign*
across the two real seasons, not absolute MAE/Brier.

## Real numbers, both seasons (test weeks 11-18), corrected

| Candidate | 2025 MAE Δ | 2025 Brier Δ | 2024 MAE Δ | 2024 Brier Δ |
|---|--:|--:|--:|--:|
| Travel-G alone | -0.326 | -0.0012 | -0.391 | -0.0097 |
| HFA-A alone | -0.448 | **-0.0047** | **-0.694** | **-0.0148** |
| Travel-G + HFA-A | **-0.483** | -0.0024 | -0.294 | -0.0087 |

(n=123 in 2025, n=120 in 2024; both real, same real methodology: train weeks 4-10, test weeks
11-18, `leakage_check`-verified True in both runs.)

## Real, honest finding (revised after the correction)

**Directionally robust across both real seasons**: all three candidates still beat the champion
on both MAE and Brier in both 2024 and 2025 — no sign flip anywhere. That part of the original
finding survives the correction unchanged.

**HFA-A alone is now the clear real winner on Brier in BOTH seasons** (2025: -0.0047, the best
of the three; 2024: -0.0148, also the best of the three) — this is a cleaner, more consistent
result than the pre-correction numbers showed. On MAE, the picture differs by season: 2025 still
favors the combined candidate narrowly (-0.483 vs. -0.448); **2024 now shows HFA-A alone with a
substantially larger real MAE improvement than the combined candidate** (-0.694 vs. -0.294) —
adding Travel-G on top of HFA-A actually reduces the real 2024 improvement rather than adding to
it. This is a real, honest observation worth flagging on its own: it suggests Travel-G and
HFA-A's real, per-game adjustments may partially work against each other in at least one real
season, not purely add — a genuine open question for a future phase, not resolved here.

**Read plainly, this now supports Phase 10's "prefer the simplest model" selection more
strongly than before**: HFA-A alone is the single most consistent real performer across both
real seasons on the metric (Brier) Phase 10 actually weighted most heavily, and in 2024 it beats
the more complex combined candidate outright.

**Travel-G alone remains the consistent third** on Brier in both seasons, though its real MAE
contribution in 2024 (-0.391) is respectable on its own, just smaller than HFA-A's.

## What this does and doesn't change

- Does NOT change the Phase 10 selection (HFA-A alone) — this corrected check reinforces it more
  clearly than the original (buggy) numbers did.
- Does NOT serve as Phase 11's untouched holdout (degraded formula, and now explicitly "looked
  at" for this exact purpose).
- DOES upgrade Phase 9's "season stability: unverifiable" note for HFA-A specifically — real,
  second-season evidence now exists, and post-correction it's stronger and more one-sided than
  first reported, even though a *degraded*, non-production OL Index means this can't yet promote
  it to fully VALIDATED.
