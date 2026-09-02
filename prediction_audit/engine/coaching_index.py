"""
Coaching Index's own real calculation chain -- fifth fully-wired tab, and genuinely
DIFFERENT in shape from every tab so far (confirmed by inspecting v35's own real formulas
before writing this, not assumed from the others' pattern):

1. NO current-season blend step -- Section 4's own real title says "League Average & Std.
   Dev. of the 3-Yr Baseline", not "...Current-Season-Blended Baselines" like every other
   tab, and its real Z-score formulas reference the Projected 3-Yr Baseline column directly
   (no Games Played / Blend Weight / Current Season / Blended columns exist on this tab at
   all). This module's own compute function skips decay_baseline.py's blend_weight/
   blended_value entirely -- Projected Baseline IS the final per-metric value here.

2. Penalty's real Z-score is explicitly SIGN-FLIPPED (`=-1*(Z113-$Z$148)/$Z$149` in the real
   formula) -- lower penalty rate is better, unlike the other 3 "higher is better" metrics.
   `invert_penalty=True` is baked into compute_coaching_index() to match.

3. The real "Coaching Adjustment (pts)" formula has NO baseline offset --
   `=F153*'Model Assumptions'!$C$169`, not `=baseline+F153*points_per_sd` the way QB/RB/
   WR-TE/Secondary Index's own Score formulas all are (Coaching Index feeds a direct additive
   adjustment into Team Ratings' Net Power Rating, not a points-scale Score). Reuses
   decay_baseline.py's weighted_composite_score() unchanged by simply passing baseline=0.0 --
   0 + weighted_zsum*conversion_constant is mathematically identical to the real formula, so
   no new generic function was needed for this.
"""
from __future__ import annotations

from dataclasses import dataclass

from .decay_baseline import (
    decay_weighted_average,
    projected_baseline,
    team_history,
    weighted_composite_score,
    z_score,
)

METRIC_KEYS = ("fourth_down", "q1_epa", "penalty", "h2_epa_delta")
INVERTED_METRICS = frozenset({"penalty"})


@dataclass
class CoachingIndexConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float
    weights: dict[str, float]
    conversion_constant: float  # Model Assumptions C169 -- NOT a baseline/points-per-SD pair
    league_avg: dict[str, float]
    league_std: dict[str, float]


@dataclass
class CoachingTeamHistory:
    team: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]


@dataclass
class CoachingIndexResult:
    team: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    z_scores: dict[str, float]
    weighted_zsum: float
    score: float  # "Coaching Adjustment (pts)" -- an additive Team Ratings term, not a Score


def compute_coaching_index(
    history: CoachingTeamHistory, constants: CoachingIndexConstants,
) -> CoachingIndexResult:
    """Pure function. No blend step (see this module's own docstring) -- Z-scores are taken
    directly off Projected Baseline, with Penalty's own real sign-flip applied."""
    weighted_avg = {}
    th = {}
    pb = {}
    for m in METRIC_KEYS:
        weighted_avg[m] = decay_weighted_average(
            history.y1[m], history.y2[m], history.y3[m], constants.decay_factor,
        )
        th[m] = team_history(history.y1[m], weighted_avg[m], constants.last_year_emphasis)
        pb[m] = projected_baseline(
            th[m], history.league_baseline_y1[m], constants.regression_weight,
        )

    z_scores = {}
    for m in METRIC_KEYS:
        z = z_score(pb[m], constants.league_avg[m], constants.league_std[m])
        z_scores[m] = -z if m in INVERTED_METRICS else z

    weighted_zsum, score = weighted_composite_score(
        z_scores, constants.weights, baseline=0.0,
        points_per_sd=constants.conversion_constant,
    )

    return CoachingIndexResult(
        team=history.team, weighted_avg=weighted_avg, team_history=th, proj_baseline=pb,
        z_scores=z_scores, weighted_zsum=weighted_zsum, score=score,
    )
