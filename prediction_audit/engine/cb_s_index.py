"""
CB-S Index's own real calculation chain -- fourteenth fully-wired tab. Same no-blend,
standard-baseline shape as EDGE-IDL Index/LB Index. 317 real players (every real
starter+backup at every real CB/S slot -- CB1/CB2/NB/FS/SS and their real backups), 2 real
metrics (INT Rate, PBU Rate, both per-snap), both higher-is-better, no inversion.
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

METRIC_KEYS = ("int_rate", "pbu_rate")


@dataclass
class CBSIndexConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float
    weights: dict[str, float]
    score_baseline: float
    points_per_sd: float
    league_avg: dict[str, float]
    league_std: dict[str, float]


@dataclass
class CBSPlayerHistory:
    player_id: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]


@dataclass
class CBSIndexResult:
    player_id: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    z_scores: dict[str, float]
    weighted_zsum: float
    score: float


def compute_cb_s_index(
    history: CBSPlayerHistory, constants: CBSIndexConstants,
) -> CBSIndexResult:
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

    return CBSIndexResult(
        player_id=history.player_id, weighted_avg=weighted_avg, team_history=th,
        proj_baseline=pb, z_scores=z_scores, weighted_zsum=weighted_zsum, score=score,
    )
