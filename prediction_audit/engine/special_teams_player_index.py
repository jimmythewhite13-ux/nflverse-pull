"""
Special Teams Player Index's own real calculation chain -- fifteenth fully-wired tab, and
genuinely different from every player-level tab so far: ONE governing stat per real slot type
(P/KR/PR), not several metrics scored together. Confirmed by inspecting v35's own real
Section 5 title before writing this ("one real governing stat per role -- Z is scored within
that role's OWN population, not blended across roles") and Section 4's own real per-role
average/std rows (P/KR/PR each get their own real AVERAGE/STDEVP over their own contiguous
Section 3 sub-range, not one shared league baseline). No current-season blend step (Projected
Baseline feeds the Z-score directly, same as EDGE-IDL/LB/CB-S Index).

Reuses weighted_composite_score() unchanged with a single-key {"stat": 1.0} weight dict --
mathematically identical to a direct baseline+Z*points_per_sd formula (which is exactly what
the real Score formula is), no new generic function needed.
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

SLOT_TYPES = ("P", "KR", "PR")


@dataclass
class SpecialTeamsPlayerIndexConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float
    score_baseline: float
    points_per_sd: float
    league_avg: dict[str, float]  # keyed by slot_type (P/KR/PR)
    league_std: dict[str, float]  # keyed by slot_type (P/KR/PR)


@dataclass
class SpecialTeamsPlayerHistory:
    player_id: str
    slot_type: str  # "P", "KR", or "PR"
    y1: float
    y2: float
    y3: float
    league_baseline_y1: float


@dataclass
class SpecialTeamsPlayerIndexResult:
    player_id: str
    weighted_avg: float
    team_history: float
    proj_baseline: float
    z_score: float
    score: float


def compute_special_teams_player_index(
    history: SpecialTeamsPlayerHistory, constants: SpecialTeamsPlayerIndexConstants,
) -> SpecialTeamsPlayerIndexResult:
    weighted_avg = decay_weighted_average(
        history.y1, history.y2, history.y3, constants.decay_factor,
    )
    th = team_history(history.y1, weighted_avg, constants.last_year_emphasis)
    pb = projected_baseline(th, history.league_baseline_y1, constants.regression_weight)

    z = z_score(
        pb, constants.league_avg[history.slot_type], constants.league_std[history.slot_type],
    )
    _, score = weighted_composite_score(
        {"stat": z}, {"stat": 1.0}, constants.score_baseline, constants.points_per_sd,
    )

    return SpecialTeamsPlayerIndexResult(
        player_id=history.player_id, weighted_avg=weighted_avg, team_history=th,
        proj_baseline=pb, z_score=z, score=score,
    )
