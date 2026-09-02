"""
Kicking Index's own real calculation chain -- eighth fully-wired tab, back to the standard
player-level shape (decay-weighted baseline -> current-season blend -> Z-score -> weighted
composite, all three metrics "higher is better", no inversion) that QB/RB/WR-TE Index all
share. 32 real kickers (one K1 per team), 3 real metrics (FG% Over Expected, FG%, XP%).
"""
from __future__ import annotations

from dataclasses import dataclass

from .decay_baseline import (
    blend_weight,
    blended_value,
    decay_weighted_average,
    projected_baseline,
    team_history,
    weighted_composite_score,
    z_score,
)

METRIC_KEYS = ("fg_pct_oe", "fg_pct", "xp_pct")


@dataclass
class KickingIndexConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float
    blend_base: float
    blend_per_game: float
    blend_cap: float
    weights: dict[str, float]
    score_baseline: float
    points_per_sd: float
    league_avg: dict[str, float]
    league_std: dict[str, float]


@dataclass
class KickerHistory:
    player_id: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]
    games_played: int
    current_season: dict[str, float]


@dataclass
class KickingIndexResult:
    player_id: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    blend_weight: float
    blended: dict[str, float]
    z_scores: dict[str, float]
    weighted_zsum: float
    score: float


def compute_kicking_index(
    history: KickerHistory, constants: KickingIndexConstants,
) -> KickingIndexResult:
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

    bw = blend_weight(
        history.games_played, constants.blend_base, constants.blend_per_game,
        constants.blend_cap,
    )
    blended = {m: blended_value(pb[m], history.current_season[m], bw) for m in METRIC_KEYS}

    z_scores = {
        m: z_score(blended[m], constants.league_avg[m], constants.league_std[m])
        for m in METRIC_KEYS
    }
    weighted_zsum, score = weighted_composite_score(
        z_scores, constants.weights, constants.score_baseline, constants.points_per_sd,
    )

    return KickingIndexResult(
        player_id=history.player_id, weighted_avg=weighted_avg, team_history=th,
        proj_baseline=pb, blend_weight=bw, blended=blended, z_scores=z_scores,
        weighted_zsum=weighted_zsum, score=score,
    )
