"""
Tests for prediction_audit/historical/secondary_index_historical.py -- pure logic, no network.
Team-level, so no role resolution is tested -- focus is the real Y1/Y2/Y3 + no-leakage
current-season assembly and real league-wide stats.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.secondary_index import (  # noqa: E402
    SecondaryIndexConstants,
    compute_secondary_index,
)
from prediction_audit.historical.secondary_index_historical import (  # noqa: E402
    resolve_secondary_index_history,
    resolve_secondary_index_league_stats,
)

PLACEHOLDER_CONSTANTS = SecondaryIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
    weights={"int_rate": 0.5, "pbu_rate": 0.5},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(["int_rate", "pbu_rate"], 0.0),
    league_std=dict.fromkeys(["int_rate", "pbu_rate"], 1.0),
)


def _def_row(season, week, defteam, interception=0, pbu_p1=None, pass_attempt=1,
             season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "defteam": defteam,
        "pass_attempt": pass_attempt, "interception": interception,
        "pass_defense_1_player_id": pbu_p1, "pass_defense_2_player_id": None,
    }


def _make_team_season(season, weeks, plays_per_week, defteam, int_rate, pbu_rate):
    weeks = list(weeks)
    total = len(weeks) * plays_per_week
    n_ints = round(total * int_rate)
    n_pbus = round(total * pbu_rate)
    rows = []
    idx = 0
    for week in weeks:
        for _ in range(plays_per_week):
            rows.append(_def_row(
                season, week, defteam,
                interception=1 if idx < n_ints else 0,
                pbu_p1=("someone" if idx < n_pbus else None),
            ))
            idx += 1
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_team_season(season, range(1, 9), 30, "BUF", 0.02, 0.12)
        rows += _make_team_season(season, range(1, 9), 30, "MIA", 0.015, 0.09)
    return pd.DataFrame(rows)


def _fake_pbp_current_season(target_season=2024):
    rows = []
    rows += _make_team_season(target_season, range(1, 5), 30, "BUF", 0.03, 0.15)
    rows += _make_team_season(target_season, range(1, 5), 30, "MIA", 0.015, 0.09)
    # Week 5 (real target week) -- must NOT leak in.
    rows += _make_team_season(target_season, [5], 30, "BUF", 0.99, 0.99)
    return pd.DataFrame(rows)


def _fake_sched(target_season=2024):
    return pd.DataFrame([
        {"season": target_season, "game_type": "REG", "week": w,
         "home_team": "BUF", "away_team": "MIA", "home_score": 20, "away_score": 17}
        for w in range(1, 5)
    ])


def test_resolve_secondary_index_history_real_y1_y2_y3_and_no_leakage():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    history = resolve_secondary_index_history(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5, team="Buffalo Bills",
    )
    assert history.y1["int_rate"] == pytest.approx(0.02, abs=0.01)
    # Current season (weeks 1-4) reflects the real 0.03 rate, not week 5's 0.99.
    assert history.current_season["int_rate"] == pytest.approx(0.03, abs=0.02)
    assert history.games_played == 4


def test_resolve_secondary_index_history_raises_on_missing_team():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    with pytest.raises(ValueError, match="No real Secondary data"):
        resolve_secondary_index_history(
            pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
            team="Denver Broncos",
        )


def test_resolve_secondary_index_league_stats_and_full_score():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    stats = resolve_secondary_index_league_stats(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
        constants_without_league_stats=PLACEHOLDER_CONSTANTS,
    )
    assert set(stats.keys()) == {"int_rate", "pbu_rate"}
    for key in stats:
        assert stats[key]["std"] >= 0.0

    real_constants = SecondaryIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
        weights={"int_rate": 0.5, "pbu_rate": 0.5},
        score_baseline=50, points_per_sd=10,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    history = resolve_secondary_index_history(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5, team="Buffalo Bills",
    )
    result = compute_secondary_index(history, real_constants)
    assert isinstance(result.score, float)
