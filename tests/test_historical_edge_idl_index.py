"""
Tests for prediction_audit/historical/edge_idl_index_historical.py -- pure logic, no network.
Compact synthetic fixtures across all 4 real underlying sources (pbp, snap counts, player-ID
crosswalk, seasonal rosters) prove the real multi-source join and the real Y1/Y2/Y3 assembly.
No `through_week`/current-season logic exists for this tab (confirmed real -- no blend step).
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.edge_idl_index import (  # noqa: E402
    EdgeIdlIndexConstants,
    compute_edge_idl_index,
)
from prediction_audit.historical.edge_idl_index_historical import (  # noqa: E402
    build_real_rate_table,
    resolve_edge_idl_history,
    resolve_edge_idl_league_stats,
)

PLACEHOLDER_CONSTANTS = EdgeIdlIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    weights={"sack_rate": 0.4, "tfl_rate": 0.3, "qb_hit_rate": 0.3},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(["sack_rate", "tfl_rate", "qb_hit_rate"], 0.0),
    league_std=dict.fromkeys(["sack_rate", "tfl_rate", "qb_hit_rate"], 1.0),
)

# gsis-format "Player ID" <-> pfr-format id, consistent across all 4 fixtures below.
_PLAYERS = {
    "00-EDGE1": "EdgeOne00",
    "00-EDGE2": "EdgeTwo00",
}


def _def_play_row(season, week, defteam, sack_id=None, tfl_id=None, qb_hit_id=None,
                   season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "defteam": defteam,
        "sack_player_id": sack_id, "half_sack_1_player_id": None,
        "half_sack_2_player_id": None, "tackle_for_loss_1_player_id": tfl_id,
        "tackle_for_loss_2_player_id": None, "qb_hit_1_player_id": qb_hit_id,
        "qb_hit_2_player_id": None,
    }


def _make_player_season_pbp(season, weeks, plays_per_week, defteam, player_id,
                             sack_rate, tfl_rate, qb_hit_rate):
    weeks = list(weeks)
    total = len(weeks) * plays_per_week
    n_sacks = round(total * sack_rate)
    n_tfls = round(total * tfl_rate)
    n_qb_hits = round(total * qb_hit_rate)
    rows = []
    idx = 0
    for week in weeks:
        for _ in range(plays_per_week):
            rows.append(_def_play_row(
                season, week, defteam,
                sack_id=player_id if idx < n_sacks else None,
                tfl_id=player_id if idx < n_tfls else None,
                qb_hit_id=player_id if idx < n_qb_hits else None,
            ))
            idx += 1
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_player_season_pbp(
            season, range(1, 9), 60, "BUF", "00-EDGE1", 0.02, 0.03, 0.05,
        )
        rows += _make_player_season_pbp(
            season, range(1, 9), 60, "MIA", "00-EDGE2", 0.01, 0.015, 0.025,
        )
    return pd.DataFrame(rows)


def _fake_snap_counts():
    rows = []
    for season in (2021, 2022, 2023):
        rows.append({"game_type": "REG", "pfr_player_id": _PLAYERS["00-EDGE1"],
                      "season": season, "defense_snaps": 500})
        rows.append({"game_type": "REG", "pfr_player_id": _PLAYERS["00-EDGE2"],
                      "season": season, "defense_snaps": 500})
    return pd.DataFrame(rows)


def _fake_player_ids():
    return pd.DataFrame([
        {"pfr_id": pfr, "gsis_id": gsis} for gsis, pfr in _PLAYERS.items()
    ])


def _fake_rosters():
    rows = []
    for season in (2021, 2022, 2023, 2024):
        rows.append({"player_id": "00-EDGE1", "season": season, "entry_year": 2018})
        rows.append({"player_id": "00-EDGE2", "season": season, "entry_year": 2019})
    return pd.DataFrame(rows)


def test_build_real_rate_table_real_join_across_4_sources():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    edge1_2023 = rate_table[
        (rate_table["Player ID"] == "00-EDGE1") & (rate_table["Season"] == 2023)
    ]
    assert not edge1_2023.empty
    assert edge1_2023.iloc[0]["Sacks Rate"] == pytest.approx(0.02, abs=0.005)


def test_resolve_edge_idl_history_real_y1_y2_y3():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    history = resolve_edge_idl_history(rate_table, target_season=2024, player_id="00-EDGE1")
    assert history.player_id == "00-EDGE1"
    assert history.y1["sack_rate"] == pytest.approx(0.02, abs=0.005)
    assert history.y2["sack_rate"] == pytest.approx(0.02, abs=0.005)
    assert history.y3["sack_rate"] == pytest.approx(0.02, abs=0.005)


def test_resolve_edge_idl_history_raises_on_missing_player():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    with pytest.raises(ValueError, match="no real qualifying"):
        resolve_edge_idl_history(rate_table, target_season=2024, player_id="00-NOBODY")


def test_resolve_edge_idl_league_stats_and_full_score():
    rate_table = build_real_rate_table(
        _fake_pbp_3yr_prior(), _fake_snap_counts(), _fake_player_ids(), _fake_rosters(),
    )
    stats = resolve_edge_idl_league_stats(rate_table, 2024, PLACEHOLDER_CONSTANTS)
    assert set(stats.keys()) == {"sack_rate", "tfl_rate", "qb_hit_rate"}

    real_constants = EdgeIdlIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        weights={"sack_rate": 0.4, "tfl_rate": 0.3, "qb_hit_rate": 0.3},
        score_baseline=50, points_per_sd=10,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    history = resolve_edge_idl_history(rate_table, 2024, "00-EDGE1")
    result = compute_edge_idl_index(history, real_constants)
    assert isinstance(result.score, float)
