"""
Special Teams Index's own real calculation chain -- eleventh fully-wired tab. Team-level (32
real teams), 2 real metrics (Net Punt Average, Return Average), both higher-is-better, no
inversion. Like Coaching Index and Pass/Run Defense Matchup, confirmed to have NO
current-season blend step (Section 4's own real title says "League Average & Std. Dev. of
the 3-Yr Baselines", and its real Z-score formulas reference the Projected 3-Yr Baseline
columns directly). UNLIKE Coaching Index, the real Score formula uses the standard
baseline+points-per-SD shape (Model Assumptions C37/C38), same as Pass/Run Defense Matchup.
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

METRIC_KEYS = ("net_punt_avg", "return_avg")


@dataclass
class SpecialTeamsIndexConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float
    weights: dict[str, float]
    score_baseline: float
    points_per_sd: float
    league_avg: dict[str, float]
    league_std: dict[str, float]


@dataclass
class SpecialTeamsTeamHistory:
    team: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]


@dataclass
class SpecialTeamsIndexResult:
    team: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    z_scores: dict[str, float]
    weighted_zsum: float
    score: float


def compute_special_teams_index(
    history: SpecialTeamsTeamHistory, constants: SpecialTeamsIndexConstants,
) -> SpecialTeamsIndexResult:
    """No blend step -- Projected Baseline IS the final per-metric value (see this module's
    own docstring)."""
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

    z_scores = {
        m: z_score(pb[m], constants.league_avg[m], constants.league_std[m])
        for m in METRIC_KEYS
    }
    weighted_zsum, score = weighted_composite_score(
        z_scores, constants.weights, constants.score_baseline, constants.points_per_sd,
    )

    return SpecialTeamsIndexResult(
        team=history.team, weighted_avg=weighted_avg, team_history=th, proj_baseline=pb,
        z_scores=z_scores, weighted_zsum=weighted_zsum, score=score,
    )
