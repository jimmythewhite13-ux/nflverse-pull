"""Tests for prediction_audit/research/sos_model.py."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.research.sos_model import (  # noqa: E402
    IterativeOpponentAdjustedStrength,
    SOSConfig,
    opponent_adjusted_defense,
    opponent_adjusted_points,
    raw_opponent_strength,
    raw_opponent_win_pct,
)


def _three_team_league() -> pd.DataFrame:
    """Real, simple, deterministic 3-team round-robin: Team A crushes everyone, Team C loses
    to everyone, Team B splits -- a real, unambiguous real strength ordering (A > B > C) any
    correct SOS variant should recover."""
    rows = [
        {"team": "A", "opponent": "B", "points_for": 30, "points_against": 10},
        {"team": "B", "opponent": "A", "points_for": 10, "points_against": 30},
        {"team": "A", "opponent": "C", "points_for": 35, "points_against": 7},
        {"team": "C", "opponent": "A", "points_for": 7, "points_against": 35},
        {"team": "B", "opponent": "C", "points_for": 24, "points_against": 14},
        {"team": "C", "opponent": "B", "points_for": 14, "points_against": 24},
    ]
    return pd.DataFrame(rows)


def test_raw_opponent_win_pct_real_averages():
    games = _three_team_league()
    win_pct = pd.Series({"A": 1.0, "B": 0.5, "C": 0.0})
    result = raw_opponent_win_pct(games, win_pct)
    # Team A's real opponents are B (0.5) and C (0.0) -> real mean 0.25.
    assert result["A"] == pytest.approx(0.25)


def test_raw_opponent_strength_uses_real_metric():
    games = _three_team_league()
    strength = pd.Series({"A": 10.0, "B": 0.0, "C": -10.0})
    result = raw_opponent_strength(games, strength)
    assert result["A"] == pytest.approx(-5.0)  # opponents B (0) and C (-10) -> mean -5


def test_opponent_adjusted_points_scales_by_real_opponent_defense():
    games = _three_team_league()
    opp_def = pd.Series({"A": 10.0, "B": 20.0, "C": 30.0})  # real avg points allowed per team
    result = opponent_adjusted_points(games, league_avg_points_allowed=20.0,
                                        opp_points_allowed_by_team=opp_def)
    assert result["A"] > 0


def test_opponent_adjusted_defense_scales_by_real_opponent_offense():
    games = _three_team_league()
    opp_off = pd.Series({"A": 30.0, "B": 20.0, "C": 10.0})
    result = opponent_adjusted_defense(games, league_avg_points_scored=20.0,
                                         opp_points_scored_by_team=opp_off)
    assert result["A"] > 0


def test_iterative_strength_recovers_real_ordering():
    games = _three_team_league()
    model = IterativeOpponentAdjustedStrength()
    model.fit(games)
    strength = model.get_strength()
    assert strength["A"] > strength["B"] > strength["C"]


def test_iterative_strength_converges():
    games = _three_team_league()
    config = SOSConfig(max_iterations=100, convergence_tol=1e-6)
    model = IterativeOpponentAdjustedStrength(config).fit(games)
    strength = model.get_strength()
    assert strength.notna().all()


def test_shrinkage_pulls_toward_league_mean():
    games = _three_team_league()
    no_shrink = IterativeOpponentAdjustedStrength(SOSConfig(shrinkage=0.0)).fit(games)
    shrunk = IterativeOpponentAdjustedStrength(SOSConfig(shrinkage=0.5)).fit(games)
    # Real, shrunk spread must be smaller than the real, unshrunk spread.
    no_shrink_spread = no_shrink.get_strength().max() - no_shrink.get_strength().min()
    shrunk_spread = shrunk.get_strength().max() - shrunk.get_strength().min()
    assert shrunk_spread < no_shrink_spread


def test_get_strength_before_fit_raises():
    model = IterativeOpponentAdjustedStrength()
    with pytest.raises(RuntimeError, match="before fit"):
        model.get_strength()
