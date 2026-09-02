"""
Pass Rush Generation Index's own real calculation chain -- sixteenth fully-wired tab. Team-
level (32 real teams), no current-season blend step, 3 real metrics (Sack Rate, Pressure
Proxy/QB Hit Rate, Blitz Rate), all higher-is-better, no inversion.

Genuinely unique among every tab ported so far: confirmed by inspecting v35's own real
Section 5 title before writing this -- "DELIBERATELY NO points-scale column here (unlike
every other Section 5 in this workbook) -- the Weighted Z-Score Sum IS the 'Pass Rush
Generation Score (Z)'" (this tab feeds the OL vs. Pass Rush Matchup wiring directly by being
subtracted against Offensive Line Index's own Pass Protection Z, not converted to a points
scale first). Reuses weighted_composite_score() unchanged via baseline=0.0,
points_per_sd=1.0 -- 0 + weighted_zsum*1.0 is mathematically identical to the real formula.
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

METRIC_KEYS = ("sack_rate", "pressure_proxy", "blitz_rate")


@dataclass
class PassRushGenerationConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float
    weights: dict[str, float]
    league_avg: dict[str, float]
    league_std: dict[str, float]


@dataclass
class PassRushGenerationTeamHistory:
    team: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]


@dataclass
class PassRushGenerationResult:
    team: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    z_scores: dict[str, float]
    score: float  # "Pass Rush Generation Score (Z)" -- IS the weighted Z-sum, no conversion


def compute_pass_rush_generation_index(
    history: PassRushGenerationTeamHistory, constants: PassRushGenerationConstants,
) -> PassRushGenerationResult:
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
    _, score = weighted_composite_score(z_scores, constants.weights, 0.0, 1.0)

    return PassRushGenerationResult(
        team=history.team, weighted_avg=weighted_avg, team_history=th, proj_baseline=pb,
        z_scores=z_scores, score=score,
    )
