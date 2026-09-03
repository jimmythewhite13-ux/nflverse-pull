"""
Tests for the road-fatigue additions to game_context.py and
qb_replacement_value_historical.py -- pure logic, no network.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.qb_index import QBIndexConstants  # noqa: E402
from prediction_audit.historical.game_context import (  # noqa: E402
    resolve_consecutive_road_games,
    resolve_road_fatigue_adj_for_game,
)
from prediction_audit.historical.qb_replacement_value_historical import (  # noqa: E402
    resolve_qb_replacement_value,
)

QB_CONSTANTS = QBIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
    weights={"epa": 0.5, "cpoe": 0.3, "anya": 0.2},
    score_baseline=50, points_per_sd=10,
    league_avg={"epa": 0.0, "cpoe": 0.0, "anya": 0.0},
    league_std={"epa": 1.0, "cpoe": 1.0, "anya": 1.0},
)


def _sched_row(season, week, home, away):
    return {
        "season": season, "game_type": "REG", "week": week,
        "home_team": home, "away_team": away, "home_score": 20, "away_score": 17,
    }


def _fake_sched_road_trip():
    # BUF: home wk1, away wk2, away wk3, away wk4 (a real 3-game road trip before wk5), home wk5.
    return pd.DataFrame([
        _sched_row(2024, 1, "BUF", "NYJ"),
        _sched_row(2024, 2, "MIA", "BUF"),
        _sched_row(2024, 3, "NE", "BUF"),
        _sched_row(2024, 4, "PIT", "BUF"),
        _sched_row(2024, 5, "BUF", "KC"),
    ])


def test_resolve_consecutive_road_games_counts_a_real_streak():
    sched = _fake_sched_road_trip()
    assert resolve_consecutive_road_games(sched, 2024, target_week=5, team="BUF") == 3


def test_resolve_consecutive_road_games_resets_after_a_home_game():
    sched = _fake_sched_road_trip()
    assert resolve_consecutive_road_games(sched, 2024, target_week=2, team="BUF") == 0


def test_resolve_road_fatigue_adj_applies_the_real_penalty_above_threshold():
    sched = _fake_sched_road_trip()
    adj = resolve_road_fatigue_adj_for_game(
        sched, 2024, target_week=5, team="BUF", threshold=3, penalty=-1.0,
    )
    assert adj == pytest.approx(-1.0)


def test_resolve_road_fatigue_adj_zero_below_threshold():
    sched = _fake_sched_road_trip()
    adj = resolve_road_fatigue_adj_for_game(
        sched, 2024, target_week=2, team="BUF", threshold=3, penalty=-1.0,
    )
    assert adj == pytest.approx(0.0)


def _dropback_row(season, week, posteam, passer_id, passer, epa, cpoe, yards):
    return {
        "season": season, "week": week, "season_type": "REG", "posteam": posteam,
        "passer_id": passer_id, "passer": passer, "qb_dropback": 1, "pass_attempt": 1,
        "sack": 0, "qb_scramble": 0, "play_type": "pass", "epa": epa, "cpoe": cpoe,
        "passing_yards": yards, "yards_gained": yards, "pass_touchdown": 0, "interception": 0,
    }


def _make_qb_season(season, weeks, dropbacks_per_week, posteam, passer_id, passer, epa, cpoe):
    rows = []
    for week in weeks:
        for _ in range(dropbacks_per_week):
            rows.append(_dropback_row(season, week, posteam, passer_id, passer, epa, cpoe, 7))
    return rows


def _fake_qb_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_qb_season(season, range(1, 16), 15, "BUF", "00-BUF1", "J.Starter",
                                 0.10, 2.0)
        rows += _make_qb_season(season, range(1, 11), 12, "BUF", "00-BUF2", "B.Backup",
                                 -0.05, -1.0)
    return pd.DataFrame(rows)


def _fake_qb_pbp_current(target_season=2024):
    rows = []
    rows += _make_qb_season(target_season, range(1, 5), 35, "BUF", "00-BUF1", "J.Starter",
                             0.20, 3.0)
    # 26/week x 4 weeks = 104, clears the real 100-dropback qualifying threshold within the
    # 4-week current-season slice used for role resolution (unlike the 3 full prior seasons,
    # which have plenty of weeks to accumulate real volume).
    rows += _make_qb_season(target_season, range(1, 5), 26, "BUF", "00-BUF2", "B.Backup",
                             -0.05, -1.0)
    return pd.DataFrame(rows)


def _fake_qb_sched(target_season=2024):
    return pd.DataFrame([
        {"season": target_season, "game_type": "REG", "week": w,
         "home_team": "BUF", "away_team": "MIA", "home_score": 20, "away_score": 17}
        for w in range(1, 5)
    ])


def test_resolve_qb_replacement_value_real_starter_minus_backup():
    pbp_3yr = _fake_qb_pbp_3yr_prior()
    pbp_current = _fake_qb_pbp_current()
    sched = _fake_qb_sched()
    value = resolve_qb_replacement_value(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5, team="Buffalo Bills",
        qb_index_constants=QB_CONSTANTS,
    )
    assert value is not None
    assert value > 0  # the real Starter (better real EPA/CPOE) outscores the real Backup


def test_resolve_qb_replacement_value_none_when_no_real_backup():
    pbp_3yr = _fake_qb_pbp_3yr_prior()
    pbp_current = _fake_qb_pbp_current()
    sched = _fake_qb_sched()
    value = resolve_qb_replacement_value(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5, team="Denver Broncos",
        qb_index_constants=QB_CONSTANTS,
    )
    assert value is None
