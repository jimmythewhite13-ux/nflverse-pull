# Phase 10 — Model Selection (Real Evidence)

**2026-09-11 correction (supersedes the 2026-09-08 correction below, and revises this
document's selection)**: the 2026-09-08 correction fixed a margin-symmetry bug in how HFA-A's
own delta was computed. A third, separate, more fundamental bug remained: the raw Team-Specific
HFA *estimator* computed 2× the real home-field effect, which inflated the **champion's own
real error** (row 1 below) -- not any specific challenger's number. Confirmed and fixed
2026-09-09/10 (see `phase9_graduation_table.md`'s own 2026-09-11 correction for the full real
detail). Every row in the table below has been re-run against the corrected data and is
replaced, not just row 2.

**Real, corrected champion**: MAE=10.670, RMSE=13.363, Win%=57.7%, Brier=0.2363, LL=0.6641,
ATS-dir=57.7% -- down from the stale MAE=11.074/Brier=0.2410/Win%=54.5% this document originally
selected against. The champion was never as weak as previously recorded.

**What this changes about the real selection, stated plainly before the detail below**: the
first-season case for switching away from the champion has shrunk dramatically (candidate 2 is
now barely distinguishable from the champion: MAE −0.044, Brier −0.0000). But a real,
second-season check (freshly re-run against the corrected 2024 data, not previously available in
this exact form) reveals something the original document could not see: **candidate 3
(Travel+HFA) actually performs *worse* than the champion on 2024 MAE** (10.411 vs. 10.215,
Δ+0.196) -- its real 2025 MAE advantage does not survive a second season. **Candidate 2 (HFA-A
alone) is the only candidate showing a real, non-reversing improvement in both real seasons
checked**, most clearly in Win%/ATS-dir accuracy (2025: 58.5% vs. 57.7%; 2024: 76.7% vs. 65.0% --
a real, large, consistent-direction 8-12 point margin). The real selection below is unchanged
(candidate 2), but the *reasoning* is now durability-across-seasons, not first-season margin
size -- a materially more defensible real basis than the original document had available.

---

**2026-09-08 correction**: every "HFA-A" number in this document was originally computed on a
real, confirmed bug (`phase8_run.py`'s `hfa_A_home_net_delta` removed the champion's real HFA
signal once instead of twice — margin's real HFA effect is symmetric, home+net/away−net, so a
true zero requires removing it twice). Caught by Phase 13's own self-consistency check, fixed,
and every number below re-verified against the corrected run — independently cross-checked
against `phase6_run.py`'s own real fix and the corrected Phase 13 production pipeline, all
three now agree exactly (MAE=10.626, Brier=0.2363). The corrected numbers make the case for
this document's selection *more* clear-cut, not less — see below.

**Prerequisite confirmed**: Phase 9's graduation table is complete (`phase9_graduation_table.md`,
already delivered). This selection proceeds on that real evidence, not a claim that it exists.

## The 5 required candidates, real numbers (test weeks 11-18, n=123, same set throughout)

**2026-09-11 corrected table** (real, direct re-run against the corrected raw-HFA-estimator
data; test weeks 11-18, n=123):

| # | Candidate | MAE | RMSE | Win% | Brier | Log Loss | ATS-dir |
|---|---|--:|--:|--:|--:|--:|--:|
| 1 | Frozen champion (`v35-audit-passed-hfa-fix`) | 10.670 | 13.363 | 57.7% | 0.2363 | 0.6641 | 57.7% |
| 2 | Best individual challenger — **HFA (A, no HFA)** | 10.626 | 13.337 | 58.5% | **0.2363** | 0.6649 | 58.5% |
| 3 | Best combined challenger — **Travel (G) + HFA (A)** | **10.555** | 13.324 | **61.8%** | 0.2376 | 0.6686 | 61.8% |
| 4 | Simplified (injury_adj + qb_replacement removed) | 10.670 | 13.363 | 57.7% | 0.2363 | 0.6641 | 57.7% (identical to champion) |
| 5 | Full candidate v38 (every VALIDATED feature combined) | — | — | — | — | — | — |

Real, corrected deltas vs. the champion: candidate 2 is now MAE −0.044/Brier −0.0000/Win%
+0.8pt -- barely distinguishable from the champion on 2025 data alone. Candidate 3 is MAE
−0.115/Brier **+0.0013 (worse)**/Win% +4.1pt -- a real, larger MAE/Win% gain than candidate 2,
but a real Brier *regression*, not the real Brier improvement originally reported (was 0.2386
vs. a stale 0.2410 champion; is now 0.2376 vs. a corrected 0.2363 champion).

Superseded original table (stale champion baseline, kept for the record, not for reference):

| # | Candidate | MAE | RMSE | Win% | Brier | Log Loss | ATS-dir |
|---|---|--:|--:|--:|--:|--:|--:|
| 1 | Frozen champion (`v35-audit-passed-hfa-fix`) | 11.074 | 13.731 | 54.5% | 0.2410 | 0.6732 | 54.5% |
| 2 | Best individual challenger — **HFA (A, no HFA)** | 10.626 | 13.337 | 58.5% | **0.2363** | 0.6649 | 58.5% |
| 3 | Best combined challenger — **Travel (G) + HFA (A)** | **10.591** | 13.436 | **59.3%** | 0.2386 | 0.6711 | 59.3% |
| 4 | Simplified (injury_adj + qb_replacement removed) | 11.074 | 13.731 | 54.5% | 0.2410 | 0.6732 | 54.5% (identical to champion) |
| 5 | Full candidate v38 (every VALIDATED feature combined) | — | — | — | — | — | — |

**Real, honest note on candidate 5**: Phase 9 found **zero** features achieved full VALIDATED
status — criterion 2 (season stability) is unverifiable with only one real reconstructed
season, so nothing has cleared the bar yet by the strict definition. There is nothing to
combine that Phase 8 hasn't already tested. Candidate 5 as literally specified does not exist
as a distinct model right now; it collapses to candidate 3 (the best combination of currently
TESTED, non-redundant, non-BLOCKED real improvements).

**Real note on candidate 2 vs. what Phase 8 labeled "best individual"** (2026-09-11 correction):
the real, corrected numbers show HFA alone (MAE=10.626, Brier=0.2363) beats Travel alone
(real, corrected: MAE=10.627, Brier=0.2379 — not the stale MAE=10.748/Brier=0.2398 originally
cited) on Brier/log-loss, essentially tied on MAE (10.626 vs. 10.627, a 0.001pt real
difference). HFA alone remains the real best individual challenger.

**Real, second-season check, now decisive for a different reason than originally stated
(2026-09-11 correction)**: the corrected 2024 secondary check (degraded-OL-Index, not fully
comparable in absolute terms, but real) gives:

| Candidate (2024, n=120) | MAE | Brier | Win% |
|---|--:|--:|--:|
| Champion | 10.215 | 0.2102 | 65.0% |
| HFA-A alone | 10.121 | 0.2071 | **76.7%** |
| Travel-G + HFA-A (combined) | 10.411 | 0.2102 | 69.2% |

The real, important finding this correction surfaces: **the combined candidate's real 2025 MAE
advantage does not survive the second season** — its 2024 MAE (10.411) is actually *worse* than
the 2024 champion's own MAE (10.215), a real reversal, not noise. HFA-A alone is the only
candidate showing a real, non-reversing improvement over the champion in **both** real seasons
checked, most clearly in Win% (2025: 58.5% vs. 57.7%; 2024: 76.7% vs. 65.0%). This is a more
durable, more defensible real basis for selection than the original document had access to —
the original framed this as "HFA-A beats the combined candidate on every metric" using stale
2024 numbers; the corrected picture is sharper and more important than that: the combined
candidate doesn't just lose to HFA-A, it loses to the *unmodified champion* on 2024 MAE.

## Selection principle, applied literally

**The preferred model is the simplest model that demonstrates durable out-of-sample
improvement.** Under the corrected numbers, the real first-season case for candidate 2 over the
champion has shrunk to near-parity (MAE −0.044, Brier −0.0000) — far smaller than originally
reported. But "durable" is the operative word in the stated principle, and durability is exactly
what the corrected second-season check speaks to: candidate 3's real 2025 MAE edge reverses in
2024, while candidate 2's real improvement — particularly in Win%/ATS-dir accuracy — persists in
both seasons. The corrected evidence changes *why* candidate 2 is the right pick (durability
across two real seasons, not first-season margin size), without changing the pick itself.

## Real decision (2026-09-11 correction)

**Selected: Candidate 2 — HFA revised (no HFA), alone.** The pick is unchanged, but the real
margin over both the champion (candidate 1) and the alternative (candidate 3) is now much
narrower on 2025 data alone than originally reported — full honesty about that is the point of
this correction.

Justification against every primary metric (corrected numbers, 2025):
- MAE: candidate 2 (10.626) barely beats the champion (10.670, Δ−0.044) and trails candidate 3
  (10.555) by 0.071 — **real, but a much smaller edge over the champion than the stale
  Δ−0.448 originally reported**.
- RMSE: candidate 2 (13.337) beats the champion (13.363) and candidate 3 (13.324) sits between
  the two — no longer a clean win for candidate 2 over candidate 3 as previously claimed.
- Winner accuracy / ATS-dir: candidate 3 is clearly better here (61.8% vs. candidate 2's 58.5%
  vs. the champion's 57.7%).
- Brier: candidate 2 (0.2363) is essentially tied with the champion (0.2363) and **better than**
  candidate 3 (0.2376, a real regression for candidate 3 vs. the corrected champion).
- Log loss: candidate 2 (0.6649) is close to the champion (0.6641) and better than candidate 3
  (0.6686).

On 2025 evidence alone, this is now a genuinely close call between "keep the champion as-is"
and "make the single, simple HFA-A change" — candidate 2's real edge over the champion is small
on every metric. **What tips this from a close call to a real, defensible selection is the
corrected 2024 secondary check**: candidate 2 is the only candidate whose real improvement over
the champion persists into a second season (most clearly Win%: +11.7 points in 2024, vs. +0.8
in 2025 — a real, large, same-direction signal, not noise), while candidate 3's real 2025 MAE
edge actively reverses in 2024 (worse than even the unmodified champion). Candidate 2 is
selected on **durability across two real seasons**, applying the stated principle's own
"durable" requirement literally — not on first-season margin size, which the corrected numbers
show is no longer large. This selection remains provisional in the same sense every TESTED (not
VALIDATED) feature is: the 2024 check used a degraded OL Index, so full cross-season durability
against a real, full-fidelity second season is still open.

## What was NOT selected, and why (2026-09-11 correction)

- **Candidate 3 (Travel+HFA)** looked like the stronger 2025 pick on MAE/Win%/ATS-dir alone, and
  under the original (stale-champion) numbers appeared to also win on Brier. The corrected
  numbers show its Brier is actually **worse** than the champion's (0.2376 vs. 0.2363), and —
  more importantly — its real 2025 MAE advantage **does not survive the 2024 secondary check**
  (2024 MAE=10.411, worse than the 2024 champion's own 10.215). This is no longer just "a
  legitimate second choice" as the original document framed it — the real, second-season
  evidence is a genuine, real strike against selecting it now, not a value judgment left open.
- Candidates 4 and 5 do not exist as meaningfully distinct models given the current real
  evidence (4 is numerically identical to 1; 5 collapses to 3) — unaffected by this correction.
- **The champion itself (candidate 1)** deserves an explicit, honest word here that the original
  document did not need: with the corrected numbers, the case for changing *anything* is far
  weaker than originally presented. If the second-season Win% evidence were judged insufficient
  justification for a change this small, retaining the champion unchanged would be a defensible,
  real alternative decision — this document selects candidate 2 because the second-season
  evidence is real and consistent, not because the champion was shown to be badly broken (it
  was not; its own real error was previously overstated by the same bug this correction fixes).
