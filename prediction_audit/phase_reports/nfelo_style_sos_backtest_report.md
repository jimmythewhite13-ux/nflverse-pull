# nfelo-style Market-Derived SOS — Real Backtest Result

**Follow-up to the correlation screen** (real, low correlation with every existing metric,
r ≤ 0.245 in magnitude — see `nfelo_style_sos_check_report.md`). That check explicitly said low
correlation is necessary, not sufficient, and that no backtest had been run. This is that
backtest.

## Real methodology

Same convention as Phase 4's 8 already-tested SOS variants, for direct apples-to-apples
comparability: the candidate's own real team-strength value **replaces** Base Team Quality
entirely (`home_margin = proxy_home − proxy_away + flat_hfa`) — not summed as a bolt-on
adjustment. Evaluated on the exact same real out-of-sample test weeks (11-18, n=123) used
throughout Phases 2-10.

## Real result

| Candidate | MAE | RMSE | Win% | Brier | Log Loss |
|---|--:|--:|--:|--:|--:|
| CHAMPION (real Base Team Quality) | 10.152 | 12.903 | 61.8% | 0.2263 | 0.6443 |
| nfelo-style SOS proxy (standalone) | 11.128 | 14.283 | 52.8% | 0.2514 | 0.6960 |

**Delta vs. champion: MAE +0.975, Brier +0.0251 → NOT IMPROVED**, worse on every metric. All
123 real test games had a resolvable proxy value on both sides (no coverage gap).

## Real, honest read

A single real preseason market number, alone, does not compete with this project's real,
sophisticated 3-year-decay/blend Base Team Quality pipeline as a standalone team-strength
signal — the same real outcome most of Phase 4's 8 variants hit when tested this way. This is
not surprising: Base Team Quality incorporates offense/defense split, recency weighting, and
real in-season blending that a single fixed preseason number never captures.

**This does NOT contradict the correlation screen's finding.** Low correlation with existing
metrics and poor standalone predictive power are consistent, not conflicting, real results —
independence just means the market's opinion isn't *redundant*; it says nothing about whether
that opinion is *any good* on its own. A genuinely independent signal can still be a weak one.

**What this does NOT rule out**: whether this proxy adds anything when *combined* with (not
replacing) Base Team Quality — a real, separate test this backtest did not run, matching Phase
4's own convention of testing each SOS variant standalone first. Given the standalone result is
this decisively negative, and given Phase 9's own graduation criteria require a real, positive
standalone-or-combined delta before anything advances, this candidate's real status is:

**REJECTED — standalone real performance is clearly worse than the champion.** A combined test
would be the only way to reopen this, and nothing in the correlation or backtest results above
makes a strong case that one is warranted.
