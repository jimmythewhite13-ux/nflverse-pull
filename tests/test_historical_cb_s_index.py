"""
Tests for prediction_audit/historical/cb_s_index_historical.py -- pure logic, no network. Same
4-source fixture convention as EDGE-IDL/LB Index's own tests.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.cb_s_index import (  # noqa: E402
    CBSIndexConstants,
    compute_cb_s_index,
)
from prediction_audit.historical.cb_s_index_historical import (  # noqa: E402
    build_real_rate_table,
    resolve_cb_s_history,
    resolve_cb_s_league_stats,
)

PLACEHOLDER_CONSTANTS = CBSIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    weights={"int_rate": 0.5, "pbu_rate": 0.5},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(["int_rate", "pbu_rate"], 0.0),
    league_std=dict.fromkeys(["int_rate", "pbu_rate"], 1.0),
)

_PLAYERS = {"00-CB1": "CbOne00000", "00-CB2": "CbTwo00000"}


def _def_play_row(season, week, defteam, int_id=None, pbu_id=None, season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "defteam": defteam,
        "interception_player_id": int_id, "pass_defense_1_player_id": pbu_id,
        "pass_defense_2_player_id": None,
    }


def _make_player_season_pbp(season, weeks, plays_per_week, defteam, player_id,
                             int_rate, pbu_rate):
    weeks = list(weeks)
    total = len(weeks) * plays_per_week
    n_ints = round(total * int_rate)
    n_pbus = round(total * pbu_rate)
    rows = []
    idx = 0
    for week in weeks:
        for _ in range(plays_per_week):
            rows.append(_def_play_row(
                season, week, defteam,
                int_id=player_id if idx < n_ints else None,
                pbu_id=player_id if idx < n_pbus else None,
            ))
            idx += 1
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_player_season_pbp(
            season, range(1, 9), 60, "BUF", "00-CB1", 0.005, 0.02,
        )
        rows += _make_player_season_pbp(
            season, range(1, 9), 60, "MIA", "00-CB2", 0.002, 0.01,
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
        rows.append({"player_id": "00-CB1", "season": season, "entry_year": 2018})
        rows.append({"player_id": "00-CB2", "season": season, "entry_year": 2019})
    return pd.DataFrame(rows)


def test_build_real_rate_table_real_join():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    cb1_2023 = rate_table[
        (rate_table["Player ID"] == "00-CB1") & (rate_table["Season"] == 2023)
    ]
    assert not cb1_2023.empty
    assert cb1_2023.iloc[0]["INT Rate"] == pytest.approx(0.005, abs=0.002)
    assert cb1_2023.iloc[0]["PBU Rate"] == pytest.approx(0.02, abs=0.005)


def test_resolve_cb_s_history_real_y1_y2_y3():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    history = resolve_cb_s_history(rate_table, target_season=2024, player_id="00-CB1")
    assert history.y1["pbu_rate"] == pytest.approx(0.02, abs=0.005)


def test_resolve_cb_s_history_raises_on_missing_player():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    with pytest.raises(ValueError, match="no real qualifying"):
        resolve_cb_s_history(rate_table, target_season=2024, player_id="00-NOBODY")


def test_resolve_cb_s_league_stats_and_full_score():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    stats = resolve_cb_s_league_stats(rate_table, 2024, PLACEHOLDER_CONSTANTS)
    assert set(stats.keys()) == {"int_rate", "pbu_rate"}

    real_constants = CBSIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        weights={"int_rate": 0.5, "pbu_rate": 0.5},
        score_baseline=50, points_per_sd=10,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    history = resolve_cb_s_history(rate_table, 2024, "00-CB1")
    result = compute_cb_s_index(history, real_constants)
    assert isinstance(result.score, float)
