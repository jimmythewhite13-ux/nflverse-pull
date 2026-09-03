"""
Tests for prediction_audit/historical/effective_qb_rating_historical.py -- pure logic, no
network. Every underlying resolver (QB Environment Model, OL Pressure diff) is already
independently verified against real data; this focuses on the real composition itself (pass-
rate resolution, the None-propagation chain, and the final effective_qb_rating() combination).
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.offensive_line_index import OLIndexConstants  # noqa: E402
from prediction_audit.engine.pass_rush_generation_index import (  # noqa: E402
    PassRushGenerationConstants,
)
from prediction_audit.engine.qb_environment_model import QBEnvironmentModelConstants  # noqa: E402
from prediction_audit.historical.effective_qb_rating_historical import (  # noqa: E402
    resolve_effective_qb_rating,
    resolve_team_pass_rate,
)

QB_ENV_CONSTANTS = QBEnvironmentModelConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    league_avg={"success": 0.0, "explosive": 0.0, "sack": 0.0},
    league_std={"success": 1.0, "explosive": 1.0, "sack": 1.0},
    success_weight=0.15, explosive_weight=0.15, epa_weight=0.5, cpoe_weight=0.3,
    anya_weight=0.2, score_baseline=50, points_per_sd=10, new_team_penalty=1,
    recently_injured_penalty=1,
)
OL_CONSTANTS = OLIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
    weights={"pass_protection": 0.4, "run_blocking": 0.3, "sack_free_rate": 0.3},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(["pass_protection", "run_blocking", "sack_free_rate"], 0.0),
    league_std=dict.fromkeys(["pass_protection", "run_blocking", "sack_free_rate"], 1.0),
)
PASS_RUSH_CONSTANTS = PassRushGenerationConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    weights={"sack_rate": 0.5, "pressure_proxy": 0.35, "blitz_rate": 0.15},
    league_avg=dict.fromkeys(["sack_rate", "pressure_proxy", "blitz_rate"], 0.0),
    league_std=dict.fromkeys(["sack_rate", "pressure_proxy", "blitz_rate"], 1.0),
)


def _play_row(season, week, posteam, play_type):
    return {"season": season, "week": week, "season_type": "REG", "posteam": posteam,
            "play_type": play_type}


def test_resolve_team_pass_rate_real_ratio():
    rows = []
    for _ in range(30):
        rows.append(_play_row(2024, 1, "BUF", "pass"))
    for _ in range(20):
        rows.append(_play_row(2024, 1, "BUF", "run"))
    pbp = pd.DataFrame(rows)
    rate = resolve_team_pass_rate(pbp, target_week=2, team_abbr="BUF")
    assert rate == pytest.approx(0.6)


def test_resolve_team_pass_rate_none_when_no_real_plays_yet():
    pbp = pd.DataFrame([_play_row(2024, 1, "BUF", "pass")])
    rate = resolve_team_pass_rate(pbp, target_week=1, team_abbr="BUF")
    assert rate is None


def test_resolve_effective_qb_rating_none_when_qb_env_model_fails():
    # An entirely empty real pbp -- QB Environment Model can't resolve anything real, so the
    # whole composition must return None, not raise.
    empty = pd.DataFrame(columns=[
        "season", "week", "season_type", "posteam", "defteam", "passer_id", "passer",
        "qb_dropback", "pass_attempt", "sack", "play_type", "epa", "cpoe", "passing_yards",
        "yards_gained", "pass_touchdown", "interception", "success",
    ])
    result = resolve_effective_qb_rating(
        empty, empty, pd.DataFrame(columns=["season", "game_type", "week", "home_team",
                                              "away_team", "home_score", "away_score"]),
        pd.DataFrame(columns=["team", "season", "pass_attempts", "times_pressured"]),
        pd.DataFrame(columns=["tm", "season", "att", "ybc"]),
        pd.DataFrame(columns=["nflverse_game_id", "nflverse_play_id", "is_qb_fault_sack"]),
        target_season=2024, target_week=5, team="Buffalo Bills", team_abbr="BUF",
        pass_rush_opponent="Miami Dolphins", weather_adj_value=-1.5,
        qb_env_constants=QB_ENV_CONSTANTS, ol_constants=OL_CONSTANTS,
        pass_rush_constants=PASS_RUSH_CONSTANTS, ol_modifier_scaling=0.25,
        weather_modifier_scaling=0.5,
    )
    assert result is None
