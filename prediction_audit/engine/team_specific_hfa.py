"""
Team-Specific HFA's own real calculation chain -- seventeenth fully-wired tab, and the
simplest of all: a SINGLE metric (real home/away scoring margin split), no blend, no
Z-scoring, no weighted composite. Confirmed by inspecting v35's own real Section 3 before
writing this: the tab has no Section 5 at all -- "Regressed Team-Specific HFA" (Section 3's
own last column) IS the tab's real final output, feeding directly into Season Matchups' own
Z/AA formula via a real cross-sheet lookup (see build_season_matchups.py's own HFA-lookup
docstring, and prediction_audit's own v35_core_formula_components.csv row Z11/AA04).

Reuses decay_baseline.py's decay_weighted_average/team_history/projected_baseline unchanged
-- projected_baseline()'s own return value IS the real "Regressed Team-Specific HFA", no
further step needed.
"""
from __future__ import annotations

from dataclasses import dataclass

from .decay_baseline import decay_weighted_average, projected_baseline, team_history


@dataclass
class TeamSpecificHFAConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float


@dataclass
class TeamSpecificHFAHistory:
    team: str
    y1: float
    y2: float
    y3: float
    league_baseline_y1: float


@dataclass
class TeamSpecificHFAResult:
    team: str
    weighted_avg: float
    team_history: float
    regressed_hfa: float  # the tab's own real final output -- no further conversion


def compute_team_specific_hfa(
    history: TeamSpecificHFAHistory, constants: TeamSpecificHFAConstants,
) -> TeamSpecificHFAResult:
    weighted_avg = decay_weighted_average(
        history.y1, history.y2, history.y3, constants.decay_factor,
    )
    th = team_history(history.y1, weighted_avg, constants.last_year_emphasis)
    regressed_hfa = projected_baseline(
        th, history.league_baseline_y1, constants.regression_weight,
    )

    return TeamSpecificHFAResult(
        team=history.team, weighted_avg=weighted_avg, team_history=th,
        regressed_hfa=regressed_hfa,
    )
