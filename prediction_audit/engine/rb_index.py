"""
RB Value Index's own real calculation chain -- second fully-wired tab of the Python Model
Engine, reusing decay_baseline.py's shared generic functions unchanged.

5 real metrics (Rushing EPA/Play, Rushing Success Rate, YPC, RYOE/Att NGS, Red-Zone Carry
Share) -- Red-Zone Carry Share carries a real weight of 0 by design (confirmed in Step 4's
own extraction), computed every run but excluded from the scored composite.

RYOE/Att is genuinely NOT full-coverage the way the other 4 metrics are (real official NGS
Rush Yards Over Expected data, which not every real RB-season has) -- its own real Section 3
Y-1/Y-2/Y-3 substitution formula in v35 is measurably different from the other 4 metrics'
(an extra real "$K$5:$K$240,\"<>\"" existence check plus an ISBLANK-guarded rookie fallback).
That difference is entirely in DATA SOURCING, though -- once RYOE/Att's own real Y-1/Y-2/Y-3
values are resolved (however that happened), the downstream decay-weight/team-history/
regression arithmetic is IDENTICAL in shape to every other metric, confirmed by inspecting
v35's own real formula text before writing this module. No RYOE-specific arithmetic exists
here; this module's own scoping (already-resolved Y-1/Y-2/Y-3 as input, matching qb_index.py)
handles it for free.
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

METRIC_KEYS = ("rushing_epa", "rushing_sr", "ypc", "ryoe", "rz_share")


@dataclass
class RBIndexConstants:
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
class RBHistory:
    player_id: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]
    games_played: int
    current_season: dict[str, float]


@dataclass
class RBIndexResult:
    player_id: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    blend_weight: float
    blended: dict[str, float]
    z_scores: dict[str, float]
    weighted_zsum: float
    score: float


def compute_rb_index(history: RBHistory, constants: RBIndexConstants) -> RBIndexResult:
    """Pure function -- identical shape to compute_qb_index, generalized to 5 metrics."""
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

    return RBIndexResult(
        player_id=history.player_id, weighted_avg=weighted_avg, team_history=th,
        proj_baseline=pb, blend_weight=bw, blended=blended, z_scores=z_scores,
        weighted_zsum=weighted_zsum, score=score,
    )
