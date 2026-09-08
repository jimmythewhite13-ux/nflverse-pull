# Phase 8 Secondary Check — Real 2024 Season (Degraded OL Index)

**Not comparable 1:1 to the real 2025 Phase 8 numbers** (2024 uses a degraded, 2-of-3-metric OL
Index — see [ol_index_degraded_pre2025.py](../nflverse-pull/prediction_audit/research/ol_index_degraded_pre2025.py) —
since 2024 fails OL Index's real FTN-coverage constraint). Compare *relative order and sign*
across the two real seasons, not absolute MAE/Brier.

## Real numbers, both seasons (test weeks 11-18)

| Candidate | 2025 MAE Δ | 2025 Brier Δ | 2024 MAE Δ | 2024 Brier Δ |
|---|--:|--:|--:|--:|
| Travel-G alone | -0.326 | -0.0012 | -0.391 | -0.0097 |
| HFA-A alone | -0.404 | **-0.0047** | **-0.600** | -0.0117 |
| Travel-G + HFA-A | **-0.528** | -0.0041 | -0.584 | **-0.0138** |

(n=123 in 2025, n=120 in 2024; both real, same real methodology: train weeks 4-10, test weeks
11-18, `leakage_check`-verified True in both runs.)

## Real, honest finding

**Directionally robust across both real seasons**: all three candidates beat the champion on
both MAE and Brier in both 2024 and 2025 — no sign flip anywhere. That's the real result that
matters most for Phase 9's "season stability" gap (previously unverifiable with only one
season) — this is now the first real second-season check, and it holds up.

**The fine ordering between HFA-A-alone and Travel-G+HFA-A is not stable across seasons**:
2025 favored HFA-A-alone (best Brier) with Combined best on MAE; 2024 shows Combined
marginally best on Brier with HFA-A marginally best on MAE — the two swap which metric each
wins. Neither candidate is a clean, reproducible winner over the other. Read plainly, this
supports rather than undermines Phase 10's "prefer the simplest model" selection: the added
complexity of combining Travel-G with HFA-A does not buy a consistent edge over HFA-A alone in
either real season checked so far.

**Travel-G alone is the consistent third**, meaningfully behind both other candidates on every
real metric in both seasons — its real, standalone signal is smaller than either HFA
correction, though still a genuine, directionally consistent improvement over the champion.

## What this does and doesn't change

- Does NOT change the Phase 10 selection (HFA-A alone) — this check reinforces rather than
  overturns it.
- Does NOT serve as Phase 11's untouched holdout (degraded formula, and now explicitly "looked
  at" for this exact purpose).
- DOES upgrade Phase 9's "season stability: unverifiable" note for Travel-G and HFA-A
  specifically — real, second-season evidence now exists that both directions hold, even though
  a *degraded*, non-production OL Index means this can't yet promote either to fully VALIDATED.
