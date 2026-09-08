"""
Tests for prediction_audit/historical/lb_index_historical.py -- pure logic, no network. Same
4-source fixture convention as test_historical_edge_idl_index.py, extended to prove the real
Tackles+TFL merge specifically.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.lb_index import LBIndexConstants, compute_lb_index  # noqa: E402
from prediction_audit.historical.lb_index_historical import (  # noqa: E402
    build_real_rate_table,
    resolve_lb_history,
    resolve_lb_league_stats,
)

PLACEHOLDER_CONSTANTS = LBIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    weights={"tackle_rate": 0.6, "tfl_rate": 0.4},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(["tackle_rate", "tfl_rate"], 0.0),
    league_std=dict.fromkeys(["tackle_rate", "tfl_rate"], 1.0),
)

_PLAYERS = {"00-LB1": "LbOne0000", "00-LB2": "LbTwo0000"}


def _def_play_row(season, week, defteam, solo_id=None, assist_id=None, tfl_id=None,
                   season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "defteam": defteam,
        "solo_tackle_1_player_id": solo_id, "solo_tackle_2_player_id": None,
        "assist_tackle_1_player_id": assist_id, "assist_tackle_2_player_id": None,
        "assist_tackle_3_player_id": None, "assist_tackle_4_player_id": None,
        "tackle_for_loss_1_player_id": tfl_id, "tackle_for_loss_2_player_id": None,
        "sack_player_id": None, "half_sack_1_player_id": None, "half_sack_2_player_id": None,
        "qb_hit_1_player_id": None, "qb_hit_2_player_id": None,
    }


def _make_player_season_pbp(season, weeks, plays_per_week, defteam, player_id,
                             tackle_rate, tfl_rate):
    weeks = list(weeks)
    total = len(weeks) * plays_per_week
    n_tackles = round(total * tackle_rate)
    n_tfls = round(total * tfl_rate)
    rows = []
    idx = 0
    for week in weeks:
        for _ in range(plays_per_week):
            rows.append(_def_play_row(
                season, week, defteam,
                solo_id=player_id if idx < n_tackles else None,
                tfl_id=player_id if idx < n_tfls else None,
            ))
            idx += 1
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_player_season_pbp(
            season, range(1, 9), 60, "BUF", "00-LB1", 0.08, 0.01,
        )
        rows += _make_player_season_pbp(
            season, range(1, 9), 60, "MIA", "00-LB2", 0.05, 0.005,
        )
    return pd.DataFrame(rows)


def _fake_snap_counts():
    rows = []
    for season in (2021, 2022, 2023):
        for gsis, pfr in _PLAYERS.items():
            rows.append({"game_type": "REG", "pfr_player_id": pfr, "season": season,
                         "defense_snaps": 500})
    return pd.DataFrame(rows)


def _fake_player_ids():
    return pd.DataFrame([{"pfr_id": pfr, "gsis_id": gsis} for gsis, pfr in _PLAYERS.items()])


def _fake_rosters():
    rows = []
    for season in (2021, 2022, 2023, 2024):
        rows.append({"player_id": "00-LB1", "season": season, "entry_year": 2018})
        rows.append({"player_id": "00-LB2", "season": season, "entry_year": 2019})
    return pd.DataFrame(rows)


def test_build_real_rate_table_merges_tackles_and_tfl():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    lb1_2023 = rate_table[
        (rate_table["Player ID"] == "00-LB1") & (rate_table["Season"] == 2023)
    ]
    assert not lb1_2023.empty
    assert lb1_2023.iloc[0]["Tackles Rate"] == pytest.approx(0.08, abs=0.01)
    assert lb1_2023.iloc[0]["TFL Rate"] == pytest.approx(0.01, abs=0.005)
    assert lb1_2023.iloc[0]["Team"] == "Buffalo Bills"


def test_resolve_lb_history_real_y1_y2_y3():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    history = resolve_lb_history(rate_table, target_season=2024, player_id="00-LB1")
    assert history.y1["tackle_rate"] == pytest.approx(0.08, abs=0.01)


def test_resolve_lb_history_raises_on_missing_player():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    with pytest.raises(ValueError, match="no real qualifying"):
        resolve_lb_history(rate_table, target_season=2024, player_id="00-NOBODY")


def test_resolve_lb_league_stats_and_full_score():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    stats = resolve_lb_league_stats(rate_table, 2024, PLACEHOLDER_CONSTANTS)
    assert set(stats.keys()) == {"tackle_rate", "tfl_rate"}

    real_constants = LBIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        weights={"tackle_rate": 0.6, "tfl_rate": 0.4},
        score_baseline=50, points_per_sd=10,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    history = resolve_lb_history(rate_table, 2024, "00-LB1")
    result = compute_lb_index(history, real_constants)
    assert isinstance(result.score, float)
