"""
Tests for prediction_audit/historical/pass_defense_matchup_historical.py -- pure logic, no
network. Team-level, no role resolution needed -- focus is the real Y1/Y2/Y3 assembly and real
league-wide stats feeding a full real (correctly inverted) score.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.pass_defense_matchup import (  # noqa: E402
    PassDefenseMatchupConstants,
    compute_pass_defense_matchup,
)
from prediction_audit.historical.pass_defense_matchup_historical import (  # noqa: E402
    resolve_pass_defense_matchup_history,
    resolve_pass_defense_matchup_league_stats,
)

PLACEHOLDER_CONSTANTS = PassDefenseMatchupConstants(
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


def _pass_row(season, defteam, posteam, epa, success, complete, yards_gained, sack=0):
    return {
        "season": season, "season_type": "REG", "defteam": defteam, "posteam": posteam,
        "play_type": "pass", "pass_attempt": 1, "sack": sack, "epa": epa, "success": success,
        "complete_pass": complete, "yards_gained": yards_gained, "yards_after_catch": 0,
        "air_yards": yards_gained, "passing_yards": yards_gained if not sack else 0,
        "pass_oe": 0.0,
    }


def _make_team_season(season, n_plays, defteam, posteam, epa, success_rate, comp_pct,
                       explosive_rate, yards):
    rows = []
    n_success = round(n_plays * success_rate)
    n_complete = round(n_plays * comp_pct)
    n_explosive = round(n_plays * explosive_rate)
    for i in range(n_plays):
        rows.append(_pass_row(
            season, defteam, posteam, epa,
            success=1 if i < n_success else 0,
            complete=1 if i < n_complete else 0,
            yards_gained=(20 + yards) if i < n_explosive else yards,
        ))
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_team_season(season, 200, "BUF", "MIA", -0.05, 0.42, 0.62, 0.10, 6.0)
        rows += _make_team_season(season, 200, "MIA", "BUF", 0.10, 0.50, 0.68, 0.18, 7.5)
    return pd.DataFrame(rows)


def test_resolve_pass_defense_matchup_history_real_y1_y2_y3():
    pbp_3yr = _fake_pbp_3yr_prior()
    history = resolve_pass_defense_matchup_history(
        pbp_3yr, target_season=2024, team="Buffalo Bills",
    )
    assert history.y1["epa_dropback"] == pytest.approx(-0.05, abs=0.01)


def test_resolve_pass_defense_matchup_history_raises_on_missing_team():
    pbp_3yr = _fake_pbp_3yr_prior()
    with pytest.raises(ValueError, match="No real Pass Defense data"):
        resolve_pass_defense_matchup_history(pbp_3yr, target_season=2024, team="Denver Broncos")


def test_resolve_pass_defense_matchup_league_stats_and_inverted_score():
    pbp_3yr = _fake_pbp_3yr_prior()
    stats = resolve_pass_defense_matchup_league_stats(pbp_3yr, 2024, PLACEHOLDER_CONSTANTS)
    assert set(stats.keys()) == {
        "epa_dropback", "pass_success", "completion_pct", "nya", "explosive_pass",
    }

    real_constants = PassDefenseMatchupConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        weights={"epa_dropback": 0.3, "pass_success": 0.25, "completion_pct": 0.15,
                 "nya": 0.15, "explosive_pass": 0.15},
        score_baseline=50, points_per_sd=10,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    buf_history = resolve_pass_defense_matchup_history(pbp_3yr, 2024, "Buffalo Bills")
    mia_history = resolve_pass_defense_matchup_history(pbp_3yr, 2024, "Miami Dolphins")
    buf_result = compute_pass_defense_matchup(buf_history, real_constants)
    mia_result = compute_pass_defense_matchup(mia_history, real_constants)
    # BUF allows LESS (better real defense: lower EPA/completion%/explosive rate allowed) --
    # after real inversion, BUF's real score must be HIGHER than MIA's.
    assert buf_result.score > mia_result.score
