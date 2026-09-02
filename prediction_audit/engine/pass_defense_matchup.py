"""
Pass Defense Matchup's own real calculation chain -- sixth fully-wired tab. Team-level (32
real teams), 5 real metrics, all "Allowed" rates -- confirmed by inspecting v35's own real
Section 5 title before writing this ("ALL FIVE metrics are ALLOWED rates ... Z-scores are
uniformly sign-flipped") and its own real Z-score formula (`=($B$145-I110)/$B$146`, league
average MINUS raw, not raw minus average) -- lower allowed value = better defense.

Like Coaching Index, has NO current-season blend step (confirmed the same way: Section 4's
own real title says "League Average & Std. Dev. of the 3-Yr Baselines", no Games Played/
Blend Weight/Current Season/Blended columns exist on this tab). UNLIKE Coaching Index, the
real Score formula DOES use the standard baseline+points-per-SD shape (Model Assumptions
C37/C38, same cells QB/RB/WR-TE/Secondary Index reuse) -- reuses
weighted_composite_score() with those real values, not baseline=0.0.
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

METRIC_KEYS = ("epa_dropback", "pass_success", "completion_pct", "nya", "explosive_pass")
INVERTED_METRICS = frozenset(METRIC_KEYS)  # all 5 real metrics are "Allowed" rates


@dataclass
class PassDefenseMatchupConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float
    weights: dict[str, float]
    score_baseline: float
    points_per_sd: float
    league_avg: dict[str, float]
    league_std: dict[str, float]


@dataclass
class PassDefenseTeamHistory:
    team: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]


@dataclass
class PassDefenseMatchupResult:
    team: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    z_scores: dict[str, float]
    weighted_zsum: float
    score: float


def compute_pass_defense_matchup(
    history: PassDefenseTeamHistory, constants: PassDefenseMatchupConstants,
) -> PassDefenseMatchupResult:
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
        z_scores, constants.weights, constants.score_baseline, constants.points_per_sd,
    )

    return PassDefenseMatchupResult(
        team=history.team, weighted_avg=weighted_avg, team_history=th, proj_baseline=pb,
        z_scores=z_scores, weighted_zsum=weighted_zsum, score=score,
    )
