"""
Tests for prediction_audit/historical/front_seven_historical.py -- pure logic, no network.
Team-level, so no role resolution is tested (unlike QB/RB/Kicking) -- focus is the real
Y1/Y2/Y3 + no-leakage current-season assembly and real league-wide stats.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.front_seven_index import (  # noqa: E402
    FrontSevenIndexConstants,
    compute_front_seven_index,
)
from prediction_audit.historical.front_seven_historical import (  # noqa: E402
    resolve_front_seven_history,
    resolve_front_seven_league_stats,
)

PLACEHOLDER_CONSTANTS = FrontSevenIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
    weights={"sack_rate": 0.4, "tfl_rate": 0.3, "qb_hit_rate": 0.3},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(["sack_rate", "tfl_rate", "qb_hit_rate"], 0.0),
    league_std=dict.fromkeys(["sack_rate", "tfl_rate", "qb_hit_rate"], 1.0),
)


def _def_row(season, week, defteam, sack=0, qb_hit=0, tfl=0, pass_attempt=1,
             season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "defteam": defteam,
        "pass_attempt": pass_attempt, "sack": sack, "qb_hit": qb_hit,
        "tackled_for_loss": tfl,
    }


def _make_team_season(season, weeks, plays_per_week, defteam, sack_rate, tfl_rate,
                       qb_hit_rate):
    """Global play counter for exact, computable real rates over the full real play count."""
    weeks = list(weeks)
    total = len(weeks) * plays_per_week
    n_sacks = round(total * sack_rate)
    n_tfls = round(total * tfl_rate)
    n_qb_hits = round(total * qb_hit_rate)
    rows = []
    idx = 0
    for week in weeks:
        for _ in range(plays_per_week):
            rows.append(_def_row(
                season, week, defteam,
                sack=1 if idx < n_sacks else 0,
                qb_hit=1 if idx < n_qb_hits else 0,
                tfl=1 if idx < n_tfls else 0,
            ))
            idx += 1
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_team_season(season, range(1, 9), 30, "BUF", 0.08, 0.03, 0.16)
        rows += _make_team_season(season, range(1, 9), 30, "MIA", 0.05, 0.02, 0.10)
    return pd.DataFrame(rows)


def _fake_pbp_current_season(target_season=2024):
    rows = []
    rows += _make_team_season(target_season, range(1, 5), 30, "BUF", 0.12, 0.04, 0.20)
    rows += _make_team_season(target_season, range(1, 5), 30, "MIA", 0.05, 0.02, 0.10)
    # Week 5 (real target week) -- must NOT leak in.
    rows += _make_team_season(target_season, [5], 30, "BUF", 0.99, 0.99, 0.99)
    return pd.DataFrame(rows)


def _fake_sched(target_season=2024):
    return pd.DataFrame([
        {"season": target_season, "game_type": "REG", "week": w,
         "home_team": "BUF", "away_team": "MIA", "home_score": 20, "away_score": 17}
        for w in range(1, 5)
    ])


def test_resolve_front_seven_history_real_y1_y2_y3_and_no_leakage():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    history = resolve_front_seven_history(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5, team="Buffalo Bills",
    )
    assert history.y1["sack_rate"] == pytest.approx(0.08, abs=0.01)
    # Current season (weeks 1-4) reflects the real 0.12 rate, not week 5's 0.99.
    assert history.current_season["sack_rate"] == pytest.approx(0.12, abs=0.02)
    assert history.games_played == 4


def test_resolve_front_seven_history_raises_on_missing_team():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    with pytest.raises(ValueError, match="No real Front Seven data"):
        resolve_front_seven_history(
            pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
            team="Denver Broncos",
        )


def test_resolve_front_seven_league_stats_and_full_score():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    stats = resolve_front_seven_league_stats(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
        constants_without_league_stats=PLACEHOLDER_CONSTANTS,
    )
    assert set(stats.keys()) == {"sack_rate", "tfl_rate", "qb_hit_rate"}
    for key in stats:
        assert stats[key]["std"] >= 0.0

    real_constants = FrontSevenIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
        weights={"sack_rate": 0.4, "tfl_rate": 0.3, "qb_hit_rate": 0.3},
        score_baseline=50, points_per_sd=10,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    history = resolve_front_seven_history(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5, team="Buffalo Bills",
    )
    result = compute_front_seven_index(history, real_constants)
    assert isinstance(result.score, float)
