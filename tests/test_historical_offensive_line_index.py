"""
Tests for prediction_audit/historical/offensive_line_index_historical.py -- pure logic, no
network. Compact synthetic PFR/pbp/FTN fixtures prove the real merge, the real Y1/Y2/Y3
assembly, and -- specifically -- the real FTN-coverage guard for target seasons before 2025.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.offensive_line_index import (  # noqa: E402
    OLIndexConstants,
    compute_ol_index,
)
from prediction_audit.historical.offensive_line_index_historical import (  # noqa: E402
    FTN_MIN_SEASON,
    resolve_ol_index_history,
    resolve_ol_index_league_stats,
)

PLACEHOLDER_CONSTANTS = OLIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
    weights={"pass_protection": 0.4, "run_blocking": 0.3, "sack_free_rate": 0.3},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(["pass_protection", "run_blocking", "sack_free_rate"], 0.0),
    league_std=dict.fromkeys(["pass_protection", "run_blocking", "sack_free_rate"], 1.0),
)


def _pfr_pass_rows(season, team, attempts, pressured):
    return [{"team": team, "season": season, "pass_attempts": attempts,
              "times_pressured": pressured}]


def _pfr_rush_rows(season, team, att, ybc):
    return [{"tm": team, "season": season, "att": att, "ybc": ybc}]


def _fake_pfr_pass():
    rows = []
    for season in (2022, 2023, 2024):
        rows += _pfr_pass_rows(season, "BUF", 500, 100)  # 20% pressure -> 80 Pass_Protection
        rows += _pfr_pass_rows(season, "MIA", 500, 150)  # 30% pressure -> 70 Pass_Protection
    return pd.DataFrame(rows)


def _fake_pfr_rush():
    rows = []
    for season in (2022, 2023, 2024):
        rows += _pfr_rush_rows(season, "BUF", 400, 800)  # 2.0 YBC/att
        rows += _pfr_rush_rows(season, "MIA", 400, 600)  # 1.5 YBC/att
    return pd.DataFrame(rows)


def _sack_row(season, week, posteam, sack=0, pass_attempt=1, qb_fault=None,
              season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "posteam": posteam,
        "pass_attempt": pass_attempt, "sack": sack, "game_id": f"{season}_{week}_{posteam}",
        "play_id": week * 100 + (1 if sack else 0),
    }


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2022, 2023, 2024):
        for week in range(1, 9):
            for _ in range(20):
                rows.append(_sack_row(season, week, "BUF"))
            rows.append(_sack_row(season, week, "BUF", sack=1))  # 1 real sack/week
            for _ in range(20):
                rows.append(_sack_row(season, week, "MIA"))
    return pd.DataFrame(rows)


def _fake_ftn_3yr_prior():
    # Real FTN charting: BUF's real weekly sack is NOT charted as QB-fault -> counts
    # against the O-line (the conservative default this project's own function documents).
    rows = []
    for season in (2022, 2023, 2024):
        for week in range(1, 9):
            rows.append({
                "nflverse_game_id": f"{season}_{week}_BUF", "nflverse_play_id": week * 100 + 1,
                "is_qb_fault_sack": False,
            })
    return pd.DataFrame(rows)


def test_resolve_ol_index_history_real_y1_y2_y3():
    pfr_pass, pfr_rush = _fake_pfr_pass(), _fake_pfr_rush()
    pbp_3yr, ftn_3yr = _fake_pbp_3yr_prior(), _fake_ftn_3yr_prior()

    history = resolve_ol_index_history(
        pfr_pass, pfr_rush, pbp_3yr, ftn_3yr, target_season=2025, team="Buffalo Bills",
    )
    assert history.y1["pass_protection"] == pytest.approx(80.0)
    assert history.y1["run_blocking"] == pytest.approx(2.0)
    assert history.games_played == 0  # real current-season blend deliberately not applied


def test_resolve_ol_index_history_raises_on_ftn_coverage_constraint():
    pfr_pass, pfr_rush = _fake_pfr_pass(), _fake_pfr_rush()
    pbp_3yr, ftn_3yr = _fake_pbp_3yr_prior(), _fake_ftn_3yr_prior()
    target_season = FTN_MIN_SEASON + 2  # Y-3 = FTN_MIN_SEASON - 1, one year short
    with pytest.raises(ValueError, match="not available before"):
        resolve_ol_index_history(
            pfr_pass, pfr_rush, pbp_3yr, ftn_3yr, target_season=target_season,
            team="Buffalo Bills",
        )


def test_resolve_ol_index_history_raises_on_missing_team():
    pfr_pass, pfr_rush = _fake_pfr_pass(), _fake_pfr_rush()
    pbp_3yr, ftn_3yr = _fake_pbp_3yr_prior(), _fake_ftn_3yr_prior()
    with pytest.raises(ValueError, match="No real full-coverage"):
        resolve_ol_index_history(
            pfr_pass, pfr_rush, pbp_3yr, ftn_3yr, target_season=2025, team="Denver Broncos",
        )


def test_resolve_ol_index_league_stats_and_full_score():
    pfr_pass, pfr_rush = _fake_pfr_pass(), _fake_pfr_rush()
    pbp_3yr, ftn_3yr = _fake_pbp_3yr_prior(), _fake_ftn_3yr_prior()

    stats = resolve_ol_index_league_stats(
        pfr_pass, pfr_rush, pbp_3yr, ftn_3yr, 2025, PLACEHOLDER_CONSTANTS,
    )
    assert set(stats.keys()) == {"pass_protection", "run_blocking", "sack_free_rate"}

    real_constants = OLIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
        weights={"pass_protection": 0.4, "run_blocking": 0.3, "sack_free_rate": 0.3},
        score_baseline=50, points_per_sd=10,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    history = resolve_ol_index_history(
        pfr_pass, pfr_rush, pbp_3yr, ftn_3yr, 2025, "Buffalo Bills",
    )
    result = compute_ol_index(history, real_constants)
    assert isinstance(result.score, float)
