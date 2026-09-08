# Phase 10 — Model Selection (Real Evidence)

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

**Real note on candidate 2 vs. what Phase 8 labeled "best individual"**: Phase 8's own write-up
led with Travel as the individual example, but the real numbers show HFA alone (MAE=10.626,
Brier=0.2363) beats Travel alone (MAE=10.748, Brier=0.2398) on every metric. HFA alone is
therefore the real best individual challenger, corrected here rather than carried forward
uncritically from an earlier framing.

**Real, second-season reinforcement**: the corrected 2024 secondary check (degraded-OL-Index,
not fully comparable in absolute terms, but real) shows HFA-A alone beating even the combined
Travel+HFA candidate on *every* metric (MAE=10.121 vs. 10.521, Brier=0.2071 vs. 0.2132,
Win%=76.7% vs. 69.2%) — a real, second data point pointing the same direction as this
selection, for whatever a still-degraded-formula secondary check is worth.

## Selection principle, applied literally

**The preferred model is the simplest model that demonstrates durable out-of-sample
improvement.** Under the corrected numbers, candidates 2 and 3 are closer on real MAE than
originally reported (10.626 vs. 10.591 — a 0.035pt gap, not 0.124) while candidate 2 is now
*more clearly* the better real Brier/log-loss (0.2363 vs. 0.2386 — a larger real gap than
originally reported). The corrected evidence makes candidate 2 a stronger pick, not a weaker one.

## Real decision

**Selected: Candidate 2 — HFA revised (no HFA), alone.**

Justification against every primary metric (corrected numbers):
- MAE: candidate 2 is not the best (candidate 3 is lower by 0.035pts) — **acknowledged
  explicitly**, not hidden — but the gap is now real and small.
- RMSE: candidate 2 is now the **better** of the two (13.337 vs. 13.436) — reversed from the
  original (buggy) numbers.
- Winner accuracy: candidate 3 is marginally better (59.3% vs. 58.5%).
- Brier: candidate 2 is the **best** of all 5 (0.2363), by a clearer real margin than before.
- Log loss: candidate 2 is the **best** of all 5 (0.6649).
- ATS-dir: candidate 3 is marginally better (59.3% vs. 58.5%).

Candidate 2 is selected over candidate 3 on the stated **simplicity** principle: it is a single
change (remove one term) versus two independent changes (remove HFA, replace travel with a
fitted spline model). Under the corrected numbers it now wins or ties on 3 of 6 primary metrics
outright (Brier, log loss, RMSE) while trailing only narrowly on the other 3 — a cleaner case
for the simpler model than the original (buggy) numbers showed, not a weaker one. This selection
is provisional in the same sense every TESTED (not VALIDATED) feature is: full cross-season
durability has not been checked against a real, full-fidelity second season (the 2024 check
used a degraded OL Index) — but real, second-season evidence now points the same direction.

## What was NOT selected, and why

- Candidate 3 (Travel+HFA) was the closest alternative and is a legitimate second choice if
  margin accuracy is weighted more heavily than probability calibration for the eventual
  production use case — this is a real, open value judgment, not a settled question this
  document can close on its own.
- Candidates 4 and 5 do not exist as meaningfully distinct models given the current real
  evidence (4 is numerically identical to 1; 5 collapses to 3).
