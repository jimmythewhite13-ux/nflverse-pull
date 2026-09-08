"""
Tests for prediction_audit/historical/qb_index_historical.py -- pure logic, no network. A
compact synthetic pbp fixture (same real column shape nflverse's own pbp uses) proves the real
role-ranking, Y1/Y2/Y3 assembly, league-baseline computation, and no-future-information guard.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.qb_index import QBIndexConstants, compute_qb_index  # noqa: E402
from prediction_audit.historical.qb_index_historical import (  # noqa: E402
    resolve_qb_index_history,
    resolve_qb_index_league_stats,
    resolve_qb_roles_as_of_week,
)

PLACEHOLDER_CONSTANTS = QBIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
    weights={"epa": 0.5, "cpoe": 0.3, "anya": 0.3},
    score_baseline=50, points_per_sd=10,
    league_avg={"epa": 0.0, "cpoe": 0.0, "anya": 0.0},
    league_std={"epa": 1.0, "cpoe": 1.0, "anya": 1.0},
)


def _dropback_row(season, week, posteam, passer_id, passer, epa, cpoe, yards, td=0, intc=0,
                   sack=False, season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "posteam": posteam,
        "passer_id": passer_id, "passer": passer, "qb_dropback": 1,
        "pass_attempt": 0 if sack else 1, "sack": 1 if sack else 0, "qb_scramble": 0,
        "play_type": "pass", "epa": epa, "cpoe": cpoe if not sack else None,
        "passing_yards": 0 if sack else yards, "yards_gained": (-6 if sack else yards),
        "pass_touchdown": td, "interception": intc,
    }


def _make_qb_season(
    season, weeks, dropbacks_per_week, posteam, passer_id, passer, epa, cpoe, yards=7,
):
    """Real-shaped volume: `dropbacks_per_week` dropback rows (~a real game's worth) in each
    of `weeks`, so MIN_QUALIFYING_DROPBACKS (100) is realistically clearable within a normal
    NFL week range, not spread across an unrealistic 100+-week span."""
    rows = []
    for week in weeks:
        for _ in range(dropbacks_per_week):
            rows.append(_dropback_row(
                season, week, posteam, passer_id, passer, epa, cpoe, yards=yards, td=0, intc=0,
            ))
    return rows


def _fake_pbp_3yr_prior():
    # BUF Starter (00-BUF1): 15 weeks x 15 dropbacks = 225, ranks #1 by volume.
    # BUF Backup (00-BUF2): 10 weeks x 12 dropbacks = 120 -- still clears the real 100-dropback
    # qualifying threshold (so they actually appear in the population to be ranked #2), but
    # fewer than the Starter's real total.
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_qb_season(
            season, range(1, 16), 15, "BUF", "00-BUF1", "J.Starter", 0.10, 2.0,
        )
        rows += _make_qb_season(
            season, range(1, 11), 12, "BUF", "00-BUF2", "B.Backup", -0.05, -1.0,
        )
        rows += _make_qb_season(
            season, range(1, 16), 15, "MIA", "00-MIA1", "M.Starter", 0.05, 1.0, yards=5,
        )
    return pd.DataFrame(rows)


def _fake_pbp_current_season(target_season=2024):
    # Weeks 1-4 (real-game-volume: 35 dropbacks/week) before the target week (5); week 5
    # itself must never leak in.
    rows = []
    rows += _make_qb_season(
        target_season, range(1, 5), 35, "BUF", "00-BUF1", "J.Starter", 0.20, 3.0,
    )
    rows += _make_qb_season(
        target_season, range(1, 5), 35, "MIA", "00-MIA1", "M.Starter", 0.05, 1.0, yards=5,
    )
    # Week 5 (the real target week) -- a wildly different value that must NOT leak in.
    rows += _make_qb_season(
        target_season, [5], 35, "BUF", "00-BUF1", "J.Starter", 99.0, 99.0,
    )
    return pd.DataFrame(rows)


def _fake_sched(target_season=2024):
    return pd.DataFrame([
        {"season": target_season, "game_type": "REG", "week": w,
         "home_team": "BUF", "away_team": "MIA", "home_score": 20, "away_score": 17}
        for w in range(1, 5)
    ])


def test_resolve_qb_roles_as_of_week_ranks_starter_and_backup_by_real_dropbacks():
    roles = resolve_qb_roles_as_of_week(_fake_pbp_3yr_prior(), 2021, through_week=99)
    buf = roles[roles["Team"] == "Buffalo Bills"]
    starter = buf[buf["Player ID"] == "00-BUF1"].iloc[0]
    backup = buf[buf["Player ID"] == "00-BUF2"].iloc[0]
    assert starter["Role"] == "Starter"
    assert backup["Role"] == "Backup"


def test_resolve_qb_index_history_real_y1_y2_y3_and_current_season():
    pbp_3yr = _fake_pbp_3yr_prior()
    pbp_current = _fake_pbp_current_season()
    sched = _fake_sched()

    history = resolve_qb_index_history(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
        team="Buffalo Bills", role="Starter",
    )
    assert history.player_id == "00-BUF1"
    assert history.y1["epa"] == pytest.approx(0.10)
    assert history.y2["epa"] == pytest.approx(0.10)
    assert history.y3["epa"] == pytest.approx(0.10)
    # Current season (weeks 1-4 only) must reflect the real 0.20 value, NOT week 5's 99.0.
    assert history.current_season["epa"] == pytest.approx(0.20)
    assert history.games_played == 4


def test_resolve_qb_index_history_raises_on_missing_role():
    pbp_3yr = _fake_pbp_3yr_prior()
    pbp_current = _fake_pbp_current_season()
    sched = _fake_sched()
    with pytest.raises(ValueError, match="No real"):
        resolve_qb_index_history(
            pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
            team="Denver Broncos", role="Starter",
        )


def test_resolve_qb_index_league_stats_computes_real_blended_avg_std():
    pbp_3yr = _fake_pbp_3yr_prior()
    pbp_current = _fake_pbp_current_season()
    sched = _fake_sched()

    stats = resolve_qb_index_league_stats(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
        constants_without_league_stats=PLACEHOLDER_CONSTANTS,
    )
    assert set(stats.keys()) == {"epa", "cpoe", "anya"}
    for key in stats:
        assert stats[key]["std"] >= 0.0


def test_league_stats_feed_back_into_a_real_full_qb_index_score():
    pbp_3yr = _fake_pbp_3yr_prior()
    pbp_current = _fake_pbp_current_season()
    sched = _fake_sched()

    stats = resolve_qb_index_league_stats(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
        constants_without_league_stats=PLACEHOLDER_CONSTANTS,
    )
    real_constants = QBIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
        weights={"epa": 0.5, "cpoe": 0.3, "anya": 0.3},
        score_baseline=50, points_per_sd=10,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    history = resolve_qb_index_history(
        pbp_3yr, pbp_current, sched, target_season=2024, target_week=5,
        team="Buffalo Bills", role="Starter",
    )
    result = compute_qb_index(history, real_constants)
    assert isinstance(result.score, float)
