"""
Run Defense Matchup's own real calculation chain -- seventh fully-wired tab. Same shape as
pass_defense_matchup.py (team-level, no current-season blend, standard baseline+points-per-SD
Score), except a real deliberate asymmetry confirmed by inspecting v35's own real Section 5
title before writing this: "FOUR of five metrics are ALLOWED rates where LOWER is better
... Stuff Rate Allowed is the OPPOSITE (higher = better, NOT sign-flipped)". Despite its own
name, a team that stuffs more runs at/behind the line is playing BETTER run defense, so its
real Z-score formula is `=(AK110-$F$145)/$F$146` (raw minus average, NOT inverted) while the
other 4 metrics use `=($col$145-raw)/$col$146` (inverted) -- confirmed directly from the real
formula text, not assumed from the other 4 metrics' own pattern.
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

METRIC_KEYS = ("epa_rush", "run_success", "ypc", "explosive_run", "stuff_rate")
INVERTED_METRICS = frozenset({"epa_rush", "run_success", "ypc", "explosive_run"})


@dataclass
class RunDefenseMatchupConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float
    weights: dict[str, float]
    score_baseline: float
    points_per_sd: float
    league_avg: dict[str, float]
    league_std: dict[str, float]


@dataclass
class RunDefenseTeamHistory:
    team: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]


@dataclass
class RunDefenseMatchupResult:
    team: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    z_scores: dict[str, float]
    weighted_zsum: float
    score: float


def compute_run_defense_matchup(
    history: RunDefenseTeamHistory, constants: RunDefenseMatchupConstants,
) -> RunDefenseMatchupResult:
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

    return RunDefenseMatchupResult(
        team=history.team, weighted_avg=weighted_avg, team_history=th, proj_baseline=pb,
        z_scores=z_scores, weighted_zsum=weighted_zsum, score=score,
    )
