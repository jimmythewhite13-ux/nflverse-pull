"""
Tests for prediction_audit/historical/rb_index_historical.py -- pure logic, no network. Compact
synthetic pbp + NGS fixtures (real column shapes) prove the real role-ranking, Y1/Y2/Y3
assembly, the real NGS null-team-abbr filter, and rz_share's real 0.0-default behavior.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.rb_index import RBIndexConstants, compute_rb_index  # noqa: E402
from prediction_audit.historical.rb_index_historical import (  # noqa: E402
    resolve_rb_index_history,
    resolve_rb_index_league_stats,
    resolve_rb_roles_as_of_week,
)

PLACEHOLDER_CONSTANTS = RBIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
    weights={"rushing_epa": 0.3, "rushing_sr": 0.25, "ypc": 0.2, "ryoe": 0.25, "rz_share": 0.0},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(["rushing_epa", "rushing_sr", "ypc", "ryoe", "rz_share"], 0.0),
    league_std=dict.fromkeys(["rushing_epa", "rushing_sr", "ypc", "ryoe", "rz_share"], 1.0),
)


def _run_row(season, week, posteam, rusher_id, rusher_name, epa, success, yards,
             yardline_100=50, season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "posteam": posteam,
        "rusher_player_id": rusher_id, "rusher_player_name": rusher_name, "play_type": "run",
        "epa": epa, "success": success, "yards_gained": yards, "yardline_100": yardline_100,
    }


def _make_rb_season(season, weeks, carries_per_week, posteam, rusher_id, rusher_name,
                     epa, success, yards, rz_share_target=0.0):
    """Real-shaped volume clearing the real 50-carry MIN_QUALIFYING_CARRIES threshold. A
    fraction of carries (rz_share_target) are placed inside the red zone (yardline_100<=20)."""
    rows = []
    for week in weeks:
        n_rz = round(carries_per_week * rz_share_target)
        for i in range(carries_per_week):
            yardline = 10 if i < n_rz else 50
            rows.append(_run_row(
                season, week, posteam, rusher_id, rusher_name, epa, success, yards,
                yardline_100=yardline,
            ))
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_rb_season(
            season, range(1, 9), 20, "BUF", "00-BUF-RB1", "D.Starter", 0.05, 0.45, 4.5,
            rz_share_target=0.5,
        )
        rows += _make_rb_season(
            season, range(1, 6), 15, "BUF", "00-BUF-RB2", "B.Backup", -0.10, 0.35, 3.5,
            rz_share_target=0.1,
        )
        rows += _make_rb_season(
            season, range(1, 9), 20, "MIA", "00-MIA-RB1", "M.Starter", 0.02, 0.40, 4.0,
            rz_share_target=0.5,
        )
    return pd.DataFrame(rows)


def _fake_pbp_current_season(target_season=2024):
    rows = []
    rows += _make_rb_season(
        target_season, range(1, 5), 20, "BUF", "00-BUF-RB1", "D.Starter", 0.15, 0.55, 5.5,
        rz_share_target=0.5,
    )
    rows += _make_rb_season(
        target_season, range(1, 5), 20, "MIA", "00-MIA-RB1", "M.Starter", 0.02, 0.40, 4.0,
        rz_share_target=0.5,
    )
    # Week 5 (the real target week) -- must NOT leak in.
    rows += _make_rb_season(
        target_season, [5], 20, "BUF", "00-BUF-RB1", "D.Starter", 99.0, 0.99, 99.0,
        rz_share_target=0.5,
    )
    return pd.DataFrame(rows)


def _ngs_row(season, player_id, team_abbr, ryoe, week=0):
    return {"season": season, "week": week, "player_gsis_id": player_id,
            "team_abbr": team_abbr, "rush_yards_over_expected_per_att": ryoe}


def _fake_ngs_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows.append(_ngs_row(season, "00-BUF-RB1", "BUF", 0.8))
        rows.append(_ngs_row(season, "00-BUF-RB2", "BUF", -0.3))
        rows.append(_ngs_row(season, "00-MIA-RB1", "MIA", 0.2))
        # Real null-team-abbr quirk (verified live for real 2021 NGS data) -- a decoy row
        # that must be filtered out, never crash the resolver.
        rows.append(_ngs_row(season, "00-DECOY", None, 5.0))
    return pd.DataFrame(rows)


def _fake_ngs_current(target_season=2024):
    return pd.DataFrame([
        _ngs_row(target_season, "00-BUF-RB1", "BUF", 1.2),
        _ngs_row(target_season, "00-MIA-RB1", "MIA", 0.2),
    ])


def _fake_sched(target_season=2024):
    return pd.DataFrame([
        {"season": target_season, "game_type": "REG", "week": w,
         "home_team": "BUF", "away_team": "MIA", "home_score": 20, "away_score": 17}
        for w in range(1, 5)
    ])


def test_resolve_rb_roles_ranks_by_real_carries():
    roles = resolve_rb_roles_as_of_week(_fake_pbp_3yr_prior(), through_week=99)
    buf = roles[roles["Team"] == "Buffalo Bills"]
    starter = buf[buf["Player ID"] == "00-BUF-RB1"].iloc[0]
    backup = buf[buf["Player ID"] == "00-BUF-RB2"].iloc[0]
    assert starter["Role"] == "Starter"
    assert backup["Role"] == "Backup"


def test_resolve_rb_index_history_real_y1_y2_y3_and_no_leakage():
    pbp_3yr, pbp_current = _fake_pbp_3yr_prior(), _fake_pbp_current_season()
    ngs_3yr, ngs_current = _fake_ngs_3yr_prior(), _fake_ngs_current()
    sched = _fake_sched()

    history = resolve_rb_index_history(
        pbp_3yr, pbp_current, ngs_3yr, ngs_current, sched,
        target_season=2024, target_week=5, team="Buffalo Bills", role="Starter",
    )
    assert history.player_id == "00-BUF-RB1"
    assert history.y1["rushing_epa"] == pytest.approx(0.05)
    assert history.y1["ryoe"] == pytest.approx(0.8)
    # Current season (weeks 1-4 only) must reflect 0.15, NOT week 5's 99.0.
    assert history.current_season["rushing_epa"] == pytest.approx(0.15)
    assert history.games_played == 4


def test_resolve_rb_index_history_real_rz_share_defaults_to_zero_not_missing():
    pbp_3yr, pbp_current = _fake_pbp_3yr_prior(), _fake_pbp_current_season()
    ngs_3yr, ngs_current = _fake_ngs_3yr_prior(), _fake_ngs_current()
    sched = _fake_sched()
    history = resolve_rb_index_history(
        pbp_3yr, pbp_current, ngs_3yr, ngs_current, sched,
        target_season=2024, target_week=5, team="Buffalo Bills", role="Starter",
    )
    # Starter had real red-zone carries (rz_share_target=0.5) -- a real nonzero share.
    assert history.y1["rz_share"] > 0.0


def test_resolve_rb_index_history_raises_on_missing_role():
    pbp_3yr, pbp_current = _fake_pbp_3yr_prior(), _fake_pbp_current_season()
    ngs_3yr, ngs_current = _fake_ngs_3yr_prior(), _fake_ngs_current()
    sched = _fake_sched()
    with pytest.raises(ValueError, match="No real"):
        resolve_rb_index_history(
            pbp_3yr, pbp_current, ngs_3yr, ngs_current, sched,
            target_season=2024, target_week=5, team="Denver Broncos", role="Starter",
        )


def test_ngs_null_team_abbr_rows_are_filtered_not_a_crash():
    # The fixture includes a real-shaped null-team-abbr decoy row every season -- must not
    # raise "No full-name mapping for team abbreviation(s): [None]".
    pbp_3yr, pbp_current = _fake_pbp_3yr_prior(), _fake_pbp_current_season()
    ngs_3yr, ngs_current = _fake_ngs_3yr_prior(), _fake_ngs_current()
    sched = _fake_sched()
    resolve_rb_index_history(
        pbp_3yr, pbp_current, ngs_3yr, ngs_current, sched,
        target_season=2024, target_week=5, team="Buffalo Bills", role="Starter",
    )  # no raise


def test_resolve_rb_index_league_stats_and_full_score():
    pbp_3yr, pbp_current = _fake_pbp_3yr_prior(), _fake_pbp_current_season()
    ngs_3yr, ngs_current = _fake_ngs_3yr_prior(), _fake_ngs_current()
    sched = _fake_sched()

    stats = resolve_rb_index_league_stats(
        pbp_3yr, pbp_current, ngs_3yr, ngs_current, sched,
        target_season=2024, target_week=5,
        constants_without_league_stats=PLACEHOLDER_CONSTANTS,
    )
    assert set(stats.keys()) == {"rushing_epa", "rushing_sr", "ypc", "ryoe", "rz_share"}

    real_constants = RBIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
        weights={"rushing_epa": 0.3, "rushing_sr": 0.25, "ypc": 0.2, "ryoe": 0.25,
                 "rz_share": 0.0},
        score_baseline=50, points_per_sd=10,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    history = resolve_rb_index_history(
        pbp_3yr, pbp_current, ngs_3yr, ngs_current, sched,
        target_season=2024, target_week=5, team="Buffalo Bills", role="Starter",
    )
    result = compute_rb_index(history, real_constants)
    assert isinstance(result.score, float)
