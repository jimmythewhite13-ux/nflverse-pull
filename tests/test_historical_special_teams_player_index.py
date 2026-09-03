"""
Tests for prediction_audit/historical/special_teams_player_index_historical.py -- pure logic,
no network. Compact synthetic pbp + roster fixtures prove the real per-slot-type role
resolution (P/KR/PR), real Y1/Y2/Y3 assembly, and the real small-population league-stats guard.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.special_teams_player_index import (  # noqa: E402
    SpecialTeamsPlayerIndexConstants,
    compute_special_teams_player_index,
)
from prediction_audit.historical.special_teams_player_index_historical import (  # noqa: E402
    resolve_slot_player_as_of_week,
    resolve_special_teams_player_history,
    resolve_special_teams_player_league_stats,
)


def _punt_row(season, week, posteam, punter_id, kick_distance, return_yards, blocked=0,
              season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "posteam": posteam,
        "punt_attempt": 1, "punt_blocked": blocked, "punter_player_id": punter_id,
        "kick_distance": kick_distance, "return_yards": return_yards,
        "kickoff_returner_player_id": None, "punt_returner_player_id": None,
    }


def _kr_row(season, week, defteam, returner_id, return_yards, season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "posteam": None,
        "defteam": defteam, "punt_attempt": 0, "punt_blocked": 0, "punter_player_id": None,
        "kickoff_returner_player_id": returner_id, "punt_returner_player_id": None,
        "kick_distance": None, "return_yards": return_yards,
    }


def _make_punter_season(season, weeks, punts_per_week, posteam, punter_id, net_avg):
    rows = []
    for week in weeks:
        for _ in range(punts_per_week):
            rows.append(_punt_row(season, week, posteam, punter_id, net_avg, 0))
    return rows


def _make_kr_season(season, weeks, returns_per_week, defteam, returner_id, avg):
    rows = []
    for week in weeks:
        for _ in range(returns_per_week):
            rows.append(_kr_row(season, week, defteam, returner_id, avg))
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_punter_season(season, range(1, 9), 3, "BUF", "00-P1", 43.0)
        rows += _make_kr_season(season, range(1, 4), 2, "BUF", "00-KR1", 22.0)
    return pd.DataFrame(rows)


def _fake_pbp_current_season(target_season=2024):
    # 6 punts/week x 4 weeks = 24, clearing the real 20-punt MIN_QUALIFYING_PUNTS threshold
    # within the real 4-games-played window used for role resolution.
    rows = []
    rows += _make_punter_season(target_season, range(1, 5), 6, "BUF", "00-P1", 45.0)
    rows += _make_kr_season(target_season, range(1, 4), 2, "BUF", "00-KR1", 24.0)
    # Week 5 (real target week) -- must NOT leak in.
    rows += _make_punter_season(target_season, [5], 6, "BUF", "00-P1", 99.0)
    return pd.DataFrame(rows)


def _fake_rosters():
    rows = []
    for season in (2021, 2022, 2023, 2024):
        rows.append({"player_id": "00-P1", "season": season, "entry_year": 2018})
        rows.append({"player_id": "00-KR1", "season": season, "entry_year": 2019})
    return pd.DataFrame(rows)


def test_resolve_slot_player_picks_the_most_volume_player():
    p_table = resolve_slot_player_as_of_week(_fake_pbp_3yr_prior(), _fake_rosters(), "P", 99)
    buf_p = p_table[p_table["Team"] == "Buffalo Bills"].iloc[0]
    assert buf_p["Player ID"] == "00-P1"


def test_resolve_special_teams_player_history_real_y1_y2_y3_and_no_leakage():
    pbp_3yr, pbp_current, rosters = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_rosters(),
    )
    history = resolve_special_teams_player_history(
        pbp_3yr, pbp_current, rosters, target_season=2024, target_week=5,
        team="Buffalo Bills", slot_type="P",
    )
    assert history.player_id == "00-P1"
    assert history.slot_type == "P"
    assert history.y1 == pytest.approx(43.0)
    assert history.y2 == pytest.approx(43.0)
    assert history.y3 == pytest.approx(43.0)


def test_resolve_special_teams_player_history_raises_on_missing_team():
    pbp_3yr, pbp_current, rosters = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_rosters(),
    )
    with pytest.raises(ValueError, match="No real P"):
        resolve_special_teams_player_history(
            pbp_3yr, pbp_current, rosters, target_season=2024, target_week=5,
            team="Denver Broncos", slot_type="P",
        )


def test_league_stats_raises_on_too_small_a_real_population():
    # Only 1 real qualifying KR player-season exists across all 3 prior years in this
    # fixture -- must raise a clear, real error, not silently return a degenerate std=0.0.
    pbp_3yr, rosters = _fake_pbp_3yr_prior(), _fake_rosters()
    constants = SpecialTeamsPlayerIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        score_baseline=50, points_per_sd=10,
        league_avg={"KR": 0.0}, league_std={"KR": 1.0},
    )
    with pytest.raises(ValueError, match="too few for a real"):
        resolve_special_teams_player_league_stats(pbp_3yr, rosters, 2024, "KR", constants)


def test_league_stats_and_full_score_for_punter():
    pbp_3yr, pbp_current, rosters = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_rosters(),
    )
    # Add a second real punter so the real league population has >= 2 real players.
    extra = pd.DataFrame(_make_punter_season(2023, range(1, 9), 3, "MIA", "00-P2", 40.0)
                          + _make_punter_season(2022, range(1, 9), 3, "MIA", "00-P2", 40.0)
                          + _make_punter_season(2021, range(1, 9), 3, "MIA", "00-P2", 40.0))
    pbp_3yr_full = pd.concat([pbp_3yr, extra], ignore_index=True)

    placeholder = SpecialTeamsPlayerIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        score_baseline=50, points_per_sd=10,
        league_avg={"P": 0.0}, league_std={"P": 1.0},
    )
    stats = resolve_special_teams_player_league_stats(pbp_3yr_full, rosters, 2024, "P",
                                                        placeholder)
    assert stats["std"] > 0.0

    real_constants = SpecialTeamsPlayerIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        score_baseline=50, points_per_sd=10,
        league_avg={"P": stats["avg"]}, league_std={"P": stats["std"]},
    )
    history = resolve_special_teams_player_history(
        pbp_3yr_full, pbp_current, rosters, target_season=2024, target_week=5,
        team="Buffalo Bills", slot_type="P",
    )
    result = compute_special_teams_player_index(history, real_constants)
    assert isinstance(result.score, float)
