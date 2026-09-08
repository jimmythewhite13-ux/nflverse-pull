"""
WR-TE Value Index's own real calculation chain -- third fully-wired tab of the Python Model
Engine, reusing decay_baseline.py's shared generic functions unchanged.

9 real metrics (Receiving EPA/Target, Reception Success Rate, YPT, Avg Separation NGS, YAC
Over Expectation NGS, Pass-Play Snap Participation %, Red-Zone Target Share, Target Share,
Catch Rate) -- the last 4 all carry a real weight of 0 by design (confirmed in Step 4's own
extraction): two "usage, not efficiency" signals kept out of the composite by the spec's own
instruction, and two "volume-projection only" signals that exist purely to feed Player Prop
Projections.

Covers both WR and TE in one population (real Position column, D in Section 3/5) -- the
shared decay-weighted chain doesn't care about Position at all, it operates identically per
player regardless; Position is carried through in this module's own dataclasses purely for
identification, not used in any calculation.
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

METRIC_KEYS = (
    "receiving_epa", "success_rate", "ypt", "avg_sep", "yac_oe", "pass_play_pct",
    "rz_target_share", "target_share", "catch_rate",
)


@dataclass
class WRTEIndexConstants:
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
class WRTEHistory:
    player_id: str
    position: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]
    games_played: int
    current_season: dict[str, float]


@dataclass
class WRTEIndexResult:
    player_id: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    blend_weight: float
    blended: dict[str, float]
    z_scores: dict[str, float]
    weighted_zsum: float
    score: float


def compute_wr_te_index(
    history: WRTEHistory, constants: WRTEIndexConstants,
) -> WRTEIndexResult:
    """Pure function -- identical shape to compute_qb_index/compute_rb_index, generalized to
    9 metrics."""
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

    return WRTEIndexResult(
        player_id=history.player_id, weighted_avg=weighted_avg, team_history=th,
        proj_baseline=pb, blend_weight=bw, blended=blended, z_scores=z_scores,
        weighted_zsum=weighted_zsum, score=score,
    )
