"""
Test for prediction_audit/historical/explosive_play_adj_historical.py -- pure logic, no
network. Both underlying resolvers (Pass Defense Matchup, Run Defense Matchup, Explosive Play
Matchup) are already independently verified against real data. This focuses on the real
None-safe fallback (0.0, 0.0) when a team can't be resolved at all.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.explosive_play_matchup import (  # noqa: E402
    ExplosivePlayMatchupConstants,
)
from prediction_audit.engine.pass_defense_matchup import PassDefenseMatchupConstants  # noqa: E402
from prediction_audit.engine.run_defense_matchup import RunDefenseMatchupConstants  # noqa: E402
from prediction_audit.historical.explosive_play_adj_historical import (  # noqa: E402
    resolve_explosive_play_adj,
)

PD_C = PassDefenseMatchupConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    weights={"epa_dropback": 0.3, "pass_success": 0.25, "completion_pct": 0.15, "nya": 0.15,
             "explosive_pass": 0.15},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(
        ["epa_dropback", "pass_success", "completion_pct", "nya", "explosive_pass"], 0.0,
    ),
    league_std=dict.fromkeys(
        ["epa_dropback", "pass_success", "completion_pct", "nya", "explosive_pass"], 1.0,
    ),
)
RD_C = RunDefenseMatchupConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    weights={"epa_rush": 0.3, "run_success": 0.25, "ypc": 0.2, "explosive_run": 0.15,
             "stuff_rate": 0.1},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(
        ["epa_rush", "run_success", "ypc", "explosive_run", "stuff_rate"], 0.0,
    ),
    league_std=dict.fromkeys(
        ["epa_rush", "run_success", "ypc", "explosive_run", "stuff_rate"], 1.0,
    ),
)
EP_C = ExplosivePlayMatchupConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    league_avg_pass_off=0.0, league_std_pass_off=1.0,
    league_avg_run_off=0.0, league_std_run_off=1.0,
    league_avg_deep_pass_allowed=0.0, league_std_deep_pass_allowed=1.0,
    league_avg_yac_allowed=0.0, league_std_yac_allowed=1.0,
    pass_prevention_w_explosive_pass_allowed=0.5, pass_prevention_w_deep_pass_allowed=0.3,
    pass_prevention_w_yac_allowed=0.2,
)


def test_resolve_explosive_play_adj_none_safe_when_team_unresolvable():
    empty = pd.DataFrame(columns=[
        "season", "season_type", "defteam", "posteam", "play_type", "pass_attempt", "sack",
        "epa", "success", "complete_pass", "yards_gained", "passing_yards", "pass_oe",
        "air_yards", "yards_after_catch", "tackled_for_loss",
    ])
    home_adj, away_adj = resolve_explosive_play_adj(
        empty, 2024, "Buffalo Bills", "Miami Dolphins", PD_C, RD_C, EP_C,
        pass_conversion=0.1, run_conversion=0.08,
    )
    assert home_adj == pytest.approx(0.0)
    assert away_adj == pytest.approx(0.0)
