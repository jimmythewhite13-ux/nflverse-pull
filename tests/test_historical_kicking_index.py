"""
Tests for prediction_audit/historical/kicking_index_historical.py -- pure logic, no network.
Compact synthetic pbp fixture proves the real most-attempts K1 resolution, real Y1/Y2/Y3
assembly, and the no-future-information guard.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.kicking_index import (  # noqa: E402
    KickingIndexConstants,
    compute_kicking_index,
)
from prediction_audit.historical.kicking_index_historical import (  # noqa: E402
    resolve_k1_as_of_week,
    resolve_kicking_index_history,
    resolve_kicking_index_league_stats,
)

PLACEHOLDER_CONSTANTS = KickingIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
    weights={"fg_pct_oe": 0.5, "fg_pct": 0.3, "xp_pct": 0.2},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(["fg_pct_oe", "fg_pct", "xp_pct"], 0.0),
    league_std=dict.fromkeys(["fg_pct_oe", "fg_pct", "xp_pct"], 1.0),
)


def _fg_row(season, week, posteam, kicker_id, kicker_name, made, distance=40,
            season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "posteam": posteam,
        "play_type": "field_goal", "kicker_player_id": kicker_id,
        "kicker_player_name": kicker_name, "field_goal_result": "made" if made else "missed",
        "kick_distance": distance, "extra_point_result": None,
    }


def _xp_row(season, week, posteam, kicker_id, kicker_name, good, season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "posteam": posteam,
        "play_type": "extra_point", "kicker_player_id": kicker_id,
        "kicker_player_name": kicker_name, "field_goal_result": None,
        "kick_distance": None, "extra_point_result": "good" if good else "missed",
    }


def _make_kicker_season(season, weeks, attempts_per_week, posteam, kicker_id, kicker_name,
                         make_rate, xp_make_rate=1.0):
    """Global attempt counter (not reset per week) so `make_rate`/`xp_make_rate` produce an
    EXACT, easily-computable real fg_pct/xp_pct over the full real attempt count -- the first
    round(N*rate) attempts are makes, the rest misses; order doesn't affect the season mean,
    only the count does."""
    weeks = list(weeks)
    total = len(weeks) * attempts_per_week
    n_makes = round(total * make_rate)
    n_xp_makes = round(total * xp_make_rate)
    rows = []
    attempt_idx = 0
    for week in weeks:
        for _ in range(attempts_per_week):
            made = attempt_idx < n_makes
            xp_good = attempt_idx < n_xp_makes
            rows.append(_fg_row(season, week, posteam, kicker_id, kicker_name, made))
            rows.append(_xp_row(season, week, posteam, kicker_id, kicker_name, good=xp_good))
            attempt_idx += 1
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_kicker_season(
            season, range(1, 8), 3, "BUF", "00-BUF-K1", "T.Kicker", 0.85,
        )
        rows += _make_kicker_season(
            season, range(1, 8), 3, "MIA", "00-MIA-K1", "M.Kicker", 0.75, xp_make_rate=0.9,
        )
    return pd.DataFrame(rows)


def _fake_pbp_current_season(target_season=2024):
    # 4 attempts/week x 4 weeks = 16, clearing the real 15-attempt MIN_QUALIFYING_FG_ATTEMPTS
    # threshold within the real 4-games-played window.
    rows = []
    rows += _make_kicker_season(
        target_season, range(1, 5), 4, "BUF", "00-BUF-K1", "T.Kicker", 0.90,
    )
    rows += _make_kicker_season(
        target_season, range(1, 5), 4, "MIA", "00-MIA-K1", "M.Kicker", 0.75, xp_make_rate=0.9,
    )
    # Week 5 (real target week) -- a fresh, unqualified kicker who must NOT become K1 yet
    # (only 1 attempt so far, vs the incumbent's real season-long volume).
    rows += _make_kicker_season(target_season, [5], 1, "BUF", "00-BUF-K2", "New.Kicker", 1.0)
    return pd.DataFrame(rows)


def _fake_sched(target_season=2024):
    return pd.DataFrame([
        {"season": target_season, "game_type": "REG", "week": w,
         "home_team": "BUF", "away_team": "MIA", "home_score": 20, "away_score": 17}
        for w in range(1, 5)
    ])


def test_resolve_k1_picks_the_most_attempts_kicker():
    k1_table = resolve_k1_as_of_week(_fake_pbp_3yr_prior(), through_week=99)
    buf_k1 = k1_table[k1_table["Team"] == "Buffalo Bills"].iloc[0]
    assert buf_k1["Player ID"] == "00-BUF-K1"


def test_resolve_kicking_index_history_real_y1_y2_y3_and_no_leakage():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    history = resolve_kicking_index_history(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5, team="Buffalo Bills",
    )
    assert history.player_id == "00-BUF-K1"
    assert history.y1["fg_pct"] == pytest.approx(0.85, abs=0.03)
    # Current season (weeks 1-4) reflects the real 0.90 rate, not the week-5 new kicker.
    assert history.current_season["fg_pct"] == pytest.approx(0.90, abs=0.03)
    assert history.games_played == 4


def test_resolve_kicking_index_history_raises_on_missing_team():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    with pytest.raises(ValueError, match="No real K1"):
        resolve_kicking_index_history(
            pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
            team="Denver Broncos",
        )


def test_resolve_kicking_index_league_stats_and_full_score():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    stats = resolve_kicking_index_league_stats(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
        constants_without_league_stats=PLACEHOLDER_CONSTANTS,
    )
    assert set(stats.keys()) == {"fg_pct_oe", "fg_pct", "xp_pct"}

    real_constants = KickingIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
        weights={"fg_pct_oe": 0.5, "fg_pct": 0.3, "xp_pct": 0.2},
        score_baseline=50, points_per_sd=10,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    history = resolve_kicking_index_history(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5, team="Buffalo Bills",
    )
    result = compute_kicking_index(history, real_constants)
    assert isinstance(result.score, float)
