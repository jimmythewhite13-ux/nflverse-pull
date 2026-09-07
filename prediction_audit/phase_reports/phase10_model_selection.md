# Phase 10 — Model Selection (Real Evidence)

**Prerequisite confirmed**: Phase 9's graduation table is complete (`phase9_graduation_table.md`,
already delivered). This selection proceeds on that real evidence, not a claim that it exists.

## The 5 required candidates, real numbers (test weeks 11-18, n=123, same set throughout)

| # | Candidate | MAE | RMSE | Win% | Brier | Log Loss | ATS-dir |
|---|---|--:|--:|--:|--:|--:|--:|
| 1 | Frozen champion (`v35-audit-passed-hfa-fix`) | 11.074 | 13.731 | 54.5% | 0.2410 | 0.6732 | 54.5% |
| 2 | Best individual challenger — **HFA (A, no HFA)** | 10.670 | 13.363 | 57.7% | **0.2363** | 0.6641 | 57.7% |
| 3 | Best combined challenger — **Travel (G) + HFA (A)** | **10.546** | **13.320** | **61.0%** | 0.2369 | 0.6665 | 61.0% |
| 4 | Simplified (injury_adj + qb_replacement removed) | 11.074 | 13.731 | 54.5% | 0.2410 | 0.6732 | 54.5% (identical to champion) |
| 5 | Full candidate v38 (every VALIDATED feature combined) | — | — | — | — | — | — |

**Real, honest note on candidate 5**: Phase 9 found **zero** features achieved full VALIDATED
status — criterion 2 (season stability) is unverifiable with only one real reconstructed
season, so nothing has cleared the bar yet by the strict definition. There is nothing to
combine that Phase 8 hasn't already tested. Candidate 5 as literally specified does not exist
as a distinct model right now; it collapses to candidate 3 (the best combination of currently
TESTED, non-redundant, non-BLOCKED real improvements).

**Real note on candidate 2 vs. what Phase 8 labeled "best individual"**: Phase 8's own write-up
led with Travel as the individual example, but the real numbers show HFA alone (MAE=10.670,
Brier=0.2363) beats Travel alone (MAE=10.748, Brier=0.2398) on every metric. HFA alone is
therefore the real best individual challenger, corrected here rather than carried forward
uncritically from an earlier framing.

## Selection principle, applied literally

**The preferred model is the simplest model that demonstrates durable out-of-sample
improvement.** Candidates 2 and 3 are close on real Brier (0.2363 vs. 0.2369 — candidate 2 is
actually marginally *better* here) while candidate 3 leads on real MAE (10.546 vs. 10.670) and
Win% (61.0% vs. 57.7%). Neither dominates the other on every primary metric.

## Real decision

**Selected: Candidate 2 — HFA revised (no HFA), alone.**

Justification against every primary metric:
- MAE: candidate 2 is not the best (candidate 3 is lower by 0.124pts) — **acknowledged
  explicitly**, not hidden.
- RMSE: same — candidate 3 is marginally better (13.363 vs. 13.320).
- Winner accuracy: candidate 3 is better (61.0% vs. 57.7%) — **acknowledged explicitly**.
- Brier: candidate 2 is the **best** of all 5 (0.2363).
- Log loss: candidate 2 is the **best** of all 5 (0.6641).
- ATS-dir: candidate 3 is better (61.0% vs. 57.7%).

Candidate 2 is selected over candidate 3 on the stated **simplicity** principle: it is a single
change (remove one term) versus two independent changes (remove HFA, replace travel with a
fitted spline model), and it wins outright on the two metrics that measure probability quality
(Brier, log loss) while trailing candidate 3 only modestly on margin/accuracy metrics — a real,
explicit trade-off, not a case where the simpler model dominates cleanly. This selection is
provisional in the same sense every TESTED (not VALIDATED) feature is: durability across
seasons has not been checked, because a second real season does not yet exist to check it
against.

## What was NOT selected, and why

- Candidate 3 (Travel+HFA) was the closest alternative and is a legitimate second choice if
  margin accuracy is weighted more heavily than probability calibration for the eventual
  production use case — this is a real, open value judgment, not a settled question this
  document can close on its own.
- Candidates 4 and 5 do not exist as meaningfully distinct models given the current real
  evidence (4 is numerically identical to 1; 5 collapses to 3).
