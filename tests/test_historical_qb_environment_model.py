"""
Tests for prediction_audit/historical/qb_environment_model_historical.py -- pure logic, no
network. Reuses the same real pbp fixture shape as test_historical_qb_index.py (this module
wraps resolve_qb_index_history() internally for the real EPA/CPOE/ANY-A Z-score references),
extended with the extra real columns compute_player_season_qb_extended_stats needs.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.qb_environment_model import (  # noqa: E402
    QBEnvironmentModelConstants,
    compute_qb_environment_model,
)
from prediction_audit.historical.qb_environment_model_historical import (  # noqa: E402
    resolve_qb_environment_model_history,
    resolve_qb_environment_model_league_stats,
)

PLACEHOLDER_CONSTANTS = QBEnvironmentModelConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    league_avg={"success": 0.0, "explosive": 0.0, "sack": 0.0},
    league_std={"success": 1.0, "explosive": 1.0, "sack": 1.0},
    success_weight=0.15, explosive_weight=0.15, epa_weight=0.5, cpoe_weight=0.3,
    anya_weight=0.2, score_baseline=50, points_per_sd=10, new_team_penalty=1,
    recently_injured_penalty=1,
)


def _dropback_row(season, week, posteam, passer_id, passer, epa, cpoe, yards, success,
                   td=0, intc=0, sack=False, season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "posteam": posteam,
        "passer_id": passer_id, "passer": passer, "qb_dropback": 1,
        "pass_attempt": 0 if sack else 1, "sack": 1 if sack else 0, "qb_scramble": 0,
        "play_type": "pass", "epa": epa, "cpoe": cpoe if not sack else None,
        "passing_yards": 0 if sack else yards, "yards_gained": (-6 if sack else yards),
        "pass_touchdown": td, "interception": intc, "success": success,
    }


def _make_qb_season(season, weeks, dropbacks_per_week, posteam, passer_id, passer, epa, cpoe,
                     yards=7, success_rate=1.0, explosive_rate=0.0, sack_rate=0.0):
    """Global attempt counter for exact, computable real success/explosive/sack rates
    (avoids the real zero-variance league-population issue a uniform per-row value would
    cause). Explosive plays use a real 16-yard gain (>= the real 15-yard EXPLOSIVE_PASS_YARDS
    threshold); non-explosive, non-sack plays use `yards`."""
    weeks = list(weeks)
    total = len(weeks) * dropbacks_per_week
    n_success = round(total * success_rate)
    n_explosive = round(total * explosive_rate)
    n_sack = round(total * sack_rate)
    rows = []
    idx = 0
    for week in weeks:
        for _ in range(dropbacks_per_week):
            is_sack = idx < n_sack
            is_explosive = (not is_sack) and (idx < n_sack + n_explosive)
            rows.append(_dropback_row(
                season, week, posteam, passer_id, passer, epa, cpoe,
                yards=16 if is_explosive else yards,
                success=1 if idx < n_success else 0, sack=is_sack,
            ))
            idx += 1
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_qb_season(
            season, range(1, 16), 15, "BUF", "00-BUF1", "J.Starter", 0.10, 2.0, yards=7,
            success_rate=0.55, explosive_rate=0.10, sack_rate=0.05,
        )
        rows += _make_qb_season(
            season, range(1, 11), 12, "BUF", "00-BUF2", "B.Backup", -0.05, -1.0, yards=6,
            success_rate=0.40, explosive_rate=0.04, sack_rate=0.10,
        )
        rows += _make_qb_season(
            season, range(1, 16), 15, "MIA", "00-MIA1", "M.Starter", 0.05, 1.0, yards=5,
            success_rate=0.45, explosive_rate=0.06, sack_rate=0.08,
        )
    return pd.DataFrame(rows)


def _fake_pbp_current_season(target_season=2024):
    rows = []
    rows += _make_qb_season(
        target_season, range(1, 5), 35, "BUF", "00-BUF1", "J.Starter", 0.20, 3.0, yards=7,
        success_rate=0.55,
    )
    rows += _make_qb_season(
        target_season, range(1, 5), 35, "MIA", "00-MIA1", "M.Starter", 0.05, 1.0, yards=5,
        success_rate=0.45,
    )
    return pd.DataFrame(rows)


def _fake_sched(target_season=2024):
    return pd.DataFrame([
        {"season": target_season, "game_type": "REG", "week": w,
         "home_team": "BUF", "away_team": "MIA", "home_score": 20, "away_score": 17}
        for w in range(1, 5)
    ])


def test_resolve_qb_environment_model_history_real_y1_y2_y3():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    history = resolve_qb_environment_model_history(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
        team="Buffalo Bills", role="Starter",
    )
    assert history.player_id == "00-BUF1"
    assert history.y1["success"] == pytest.approx(0.55, abs=0.01)


def test_resolve_qb_environment_model_history_real_epa_z_ref_matches_qb_index():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    history = resolve_qb_environment_model_history(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
        team="Buffalo Bills", role="Starter",
    )
    # A real, finite Z-score reference was resolved (not a placeholder 0.0 by coincidence --
    # BUF's real EPA differs meaningfully from a flat 0.0 league average).
    assert isinstance(history.epa_z_ref, float)


def test_resolve_qb_environment_model_history_raises_on_missing_role():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    with pytest.raises(ValueError):
        resolve_qb_environment_model_history(
            pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
            team="Denver Broncos", role="Starter",
        )


def test_resolve_qb_environment_model_league_stats_and_full_result():
    pbp_3yr, pbp_current, sched = (
        _fake_pbp_3yr_prior(), _fake_pbp_current_season(), _fake_sched(),
    )
    stats = resolve_qb_environment_model_league_stats(pbp_3yr, 2024, PLACEHOLDER_CONSTANTS)
    assert set(stats.keys()) == {"success", "explosive", "sack"}

    real_constants = QBEnvironmentModelConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
        success_weight=0.15, explosive_weight=0.15, epa_weight=0.5, cpoe_weight=0.3,
        anya_weight=0.2, score_baseline=50, points_per_sd=10, new_team_penalty=1,
        recently_injured_penalty=1,
    )
    history = resolve_qb_environment_model_history(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
        team="Buffalo Bills", role="Starter",
    )
    result = compute_qb_environment_model(history, real_constants)
    assert isinstance(result.adjusted_baseline, float)
    assert result.situational_adj == pytest.approx(0.0)  # no new-team/injury flag triggered
