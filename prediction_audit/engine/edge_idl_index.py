"""
EDGE-IDL Index's own real calculation chain -- twelfth fully-wired tab, and the first
PLAYER-level tab with no current-season blend step (confirmed the same way as Coaching
Index/Pass-Run Defense Matchup/Special Teams Index: Section 4's own real title says "League
Average & Std. Dev. of the 3-Yr Baselines", Z-scores reference Projected Baseline directly).
Uses the standard baseline+points-per-SD Score formula (Model Assumptions C37/C38).

214 real players (every real starter+backup at every real EDGE/IDL slot -- current_roster.py's
own per-SLOT population, not a single team-wide Starter/Backup pair, per
claude_code_spec_defensive_player_index.md), 3 real metrics (Sack Rate, TFL Rate, QB Hit Rate,
all per-snap), all higher-is-better, no inversion.
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

METRIC_KEYS = ("sack_rate", "tfl_rate", "qb_hit_rate")


@dataclass
class EdgeIdlIndexConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float
    weights: dict[str, float]
    score_baseline: float
    points_per_sd: float
    league_avg: dict[str, float]
    league_std: dict[str, float]


@dataclass
class EdgeIdlPlayerHistory:
    player_id: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]


@dataclass
class EdgeIdlIndexResult:
    player_id: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    z_scores: dict[str, float]
    weighted_zsum: float
    score: float


def compute_edge_idl_index(
    history: EdgeIdlPlayerHistory, constants: EdgeIdlIndexConstants,
) -> EdgeIdlIndexResult:
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

    return EdgeIdlIndexResult(
        player_id=history.player_id, weighted_avg=weighted_avg, team_history=th,
        proj_baseline=pb, z_scores=z_scores, weighted_zsum=weighted_zsum, score=score,
    )
