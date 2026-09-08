"""
Tests for prediction_audit/historical/wr_te_index_historical.py -- pure logic, no network.
Compact synthetic fixtures across pbp, real NGS receiving, and real seasonal rosters prove this
module's own real WR1/WR2/WR3/TE1 volume-ranking-by-position convention, the real Y1/Y2/Y3
assembly, the real NGS null-team-abbr filter, and the real weight-0-metric zero placeholder.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.wr_te_index import (  # noqa: E402
    WRTEIndexConstants,
    compute_wr_te_index,
)
from prediction_audit.historical.wr_te_index_historical import (  # noqa: E402
    resolve_wr_te_index_history,
    resolve_wr_te_roles_as_of_week,
)

PLACEHOLDER_CONSTANTS = WRTEIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
    weights={
        "receiving_epa": 0.3, "success_rate": 0.2, "ypt": 0.15, "avg_sep": 0.15,
        "yac_oe": 0.2, "pass_play_pct": 0.0, "rz_target_share": 0.0, "target_share": 0.0,
        "catch_rate": 0.0,
    },
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(
        ["receiving_epa", "success_rate", "ypt", "avg_sep", "yac_oe", "pass_play_pct",
         "rz_target_share", "target_share", "catch_rate"], 0.0,
    ),
    league_std=dict.fromkeys(
        ["receiving_epa", "success_rate", "ypt", "avg_sep", "yac_oe", "pass_play_pct",
         "rz_target_share", "target_share", "catch_rate"], 1.0,
    ),
)


def _target_row(season, week, posteam, receiver_id, receiver_name, epa, success, yards,
                 season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "posteam": posteam,
        "pass_attempt": 1, "sack": 0, "receiver_player_id": receiver_id,
        "receiver_player_name": receiver_name, "epa": epa, "success": success,
        "yards_gained": yards,
    }


def _make_receiver_season(season, weeks, targets_per_week, posteam, receiver_id, name,
                           epa, success, yards):
    rows = []
    for week in weeks:
        for _ in range(targets_per_week):
            rows.append(_target_row(season, week, posteam, receiver_id, name, epa, success,
                                     yards))
    return rows


def _fake_pbp_3yr_prior():
    # Real-shaped volume: enough targets/week that even the 4-week CURRENT-season slice
    # (used both for role-ranking and the current-season blend value) clears the real
    # 40-target MIN_QUALIFYING_TARGETS threshold -- not just the full prior seasons.
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_receiver_season(season, range(1, 12), 15, "BUF", "00-WR1", "W.One",
                                       0.15, 0.55, 12)
        rows += _make_receiver_season(season, range(1, 10), 11, "BUF", "00-WR2", "W.Two",
                                       0.05, 0.45, 9)
        rows += _make_receiver_season(season, range(1, 10), 11, "BUF", "00-TE1", "T.One",
                                       0.08, 0.48, 8)
    return pd.DataFrame(rows)


def _fake_pbp_current_season(target_season=2024):
    rows = []
    rows += _make_receiver_season(target_season, range(1, 5), 15, "BUF", "00-WR1", "W.One",
                                   0.20, 0.60, 13)
    rows += _make_receiver_season(target_season, range(1, 5), 11, "BUF", "00-WR2", "W.Two",
                                   0.05, 0.45, 9)
    rows += _make_receiver_season(target_season, range(1, 5), 11, "BUF", "00-TE1", "T.One",
                                   0.08, 0.48, 8)
    # Week 5 (real target week) -- must NOT leak in.
    rows += _make_receiver_season(target_season, [5], 15, "BUF", "00-WR1", "W.One", 99, 1, 99)
    return pd.DataFrame(rows)


def _fake_ngs(seasons):
    rows = []
    for season in seasons:
        for player_id, sep, yac_oe in (
            ("00-WR1", 3.5, 1.2), ("00-WR2", 2.8, 0.5), ("00-TE1", 2.0, 0.8),
        ):
            rows.append({"season": season, "week": 0, "player_gsis_id": player_id,
                         "team_abbr": "BUF", "avg_separation": sep, "avg_yac": 5.0,
                         "avg_expected_yac": 5.0 - yac_oe})
        # Real null-team-abbr decoy row -- must be filtered, never a crash.
        rows.append({"season": season, "week": 0, "player_gsis_id": "00-DECOY",
                     "team_abbr": None, "avg_separation": 9.0, "avg_yac": 9.0,
                     "avg_expected_yac": 0.0})
    return pd.DataFrame(rows)


def _fake_rosters(target_season=2024):
    return pd.DataFrame([
        {"season": target_season, "player_id": "00-WR1", "position": "WR"},
        {"season": target_season, "player_id": "00-WR2", "position": "WR"},
        {"season": target_season, "player_id": "00-TE1", "position": "TE"},
    ])


def _fake_sched(target_season=2024):
    return pd.DataFrame([
        {"season": target_season, "game_type": "REG", "week": w,
         "home_team": "BUF", "away_team": "MIA", "home_score": 20, "away_score": 17}
        for w in range(1, 5)
    ])


def test_resolve_wr_te_roles_ranks_wr_and_te_separately_by_targets():
    rosters = _fake_rosters()
    roles = resolve_wr_te_roles_as_of_week(
        _fake_pbp_current_season(), rosters, target_season=2024, through_week=5,
    )
    buf = roles[roles["Team"] == "Buffalo Bills"]
    assert set(buf["Role"]) == {"WR1", "WR2", "TE1"}
    wr1_row = buf[buf["Role"] == "WR1"].iloc[0]
    assert wr1_row["Player ID"] == "00-WR1"
    te1_row = buf[buf["Role"] == "TE1"].iloc[0]
    assert te1_row["Player ID"] == "00-TE1"


def test_resolve_wr_te_index_history_real_y1_y2_y3_and_no_leakage():
    pbp_3yr, pbp_current = _fake_pbp_3yr_prior(), _fake_pbp_current_season()
    ngs_3yr, ngs_current = _fake_ngs([2021, 2022, 2023]), _fake_ngs([2024])
    rosters, sched = _fake_rosters(), _fake_sched()

    history = resolve_wr_te_index_history(
        pbp_3yr, pbp_current, ngs_3yr, ngs_current, rosters, sched,
        target_season=2024, target_week=5, team="Buffalo Bills", role="WR1",
    )
    assert history.player_id == "00-WR1"
    assert history.position == "WR"
    assert history.y1["receiving_epa"] == pytest.approx(0.15, abs=0.02)
    # Current season (weeks 1-4) reflects the real 0.20 value, NOT week 5's 99.
    assert history.current_season["receiving_epa"] == pytest.approx(0.20, abs=0.02)
    assert history.games_played == 4


def test_resolve_wr_te_index_history_zero_weight_metrics_default_to_zero():
    pbp_3yr, pbp_current = _fake_pbp_3yr_prior(), _fake_pbp_current_season()
    ngs_3yr, ngs_current = _fake_ngs([2021, 2022, 2023]), _fake_ngs([2024])
    rosters, sched = _fake_rosters(), _fake_sched()
    history = resolve_wr_te_index_history(
        pbp_3yr, pbp_current, ngs_3yr, ngs_current, rosters, sched,
        target_season=2024, target_week=5, team="Buffalo Bills", role="WR1",
    )
    for key in ("pass_play_pct", "rz_target_share", "target_share", "catch_rate"):
        assert history.y1[key] == 0.0


def test_ngs_null_team_abbr_rows_are_filtered_not_a_crash():
    pbp_3yr, pbp_current = _fake_pbp_3yr_prior(), _fake_pbp_current_season()
    ngs_3yr, ngs_current = _fake_ngs([2021, 2022, 2023]), _fake_ngs([2024])
    rosters, sched = _fake_rosters(), _fake_sched()
    resolve_wr_te_index_history(
        pbp_3yr, pbp_current, ngs_3yr, ngs_current, rosters, sched,
        target_season=2024, target_week=5, team="Buffalo Bills", role="TE1",
    )  # no raise


def test_resolve_wr_te_index_history_raises_on_missing_role():
    pbp_3yr, pbp_current = _fake_pbp_3yr_prior(), _fake_pbp_current_season()
    ngs_3yr, ngs_current = _fake_ngs([2021, 2022, 2023]), _fake_ngs([2024])
    rosters, sched = _fake_rosters(), _fake_sched()
    with pytest.raises(ValueError, match="No real"):
        resolve_wr_te_index_history(
            pbp_3yr, pbp_current, ngs_3yr, ngs_current, rosters, sched,
            target_season=2024, target_week=5, team="Buffalo Bills", role="WR3",
        )


def test_resolve_wr_te_index_history_full_score():
    pbp_3yr, pbp_current = _fake_pbp_3yr_prior(), _fake_pbp_current_season()
    ngs_3yr, ngs_current = _fake_ngs([2021, 2022, 2023]), _fake_ngs([2024])
    rosters, sched = _fake_rosters(), _fake_sched()
    history = resolve_wr_te_index_history(
        pbp_3yr, pbp_current, ngs_3yr, ngs_current, rosters, sched,
        target_season=2024, target_week=5, team="Buffalo Bills", role="WR1",
    )
    result = compute_wr_te_index(history, PLACEHOLDER_CONSTANTS)
    assert isinstance(result.score, float)
