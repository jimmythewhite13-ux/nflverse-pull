"""
Tests for prediction_audit/historical/pass_rush_generation_index_historical.py -- pure logic,
no network. Team-level, no role resolution -- focus is the real merge of two data sources, the
real Y1/Y2/Y3 assembly, and real league-wide stats.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.pass_rush_generation_index import (  # noqa: E402
    PassRushGenerationConstants,
    compute_pass_rush_generation_index,
)
from prediction_audit.historical.pass_rush_generation_index_historical import (  # noqa: E402
    resolve_pass_rush_generation_history,
    resolve_pass_rush_generation_league_stats,
)

PLACEHOLDER_CONSTANTS = PassRushGenerationConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    weights={"sack_rate": 0.5, "pressure_proxy": 0.35, "blitz_rate": 0.15},
    league_avg=dict.fromkeys(["sack_rate", "pressure_proxy", "blitz_rate"], 0.0),
    league_std=dict.fromkeys(["sack_rate", "pressure_proxy", "blitz_rate"], 1.0),
)


def _def_row(season, week, defteam, sack=0, qb_hit=0, pass_attempt=1, n_rushers=4,
             season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "defteam": defteam,
        "pass_attempt": pass_attempt, "sack": sack, "qb_hit": qb_hit,
        "tackled_for_loss": 0, "number_of_pass_rushers": n_rushers,
        "defenders_in_box": 6, "play_type": "pass",
    }


def _make_team_season(season, weeks, plays_per_week, defteam, sack_rate, hit_rate,
                       blitz_rate):
    weeks = list(weeks)
    total = len(weeks) * plays_per_week
    n_sacks = round(total * sack_rate)
    n_hits = round(total * hit_rate)
    n_blitz = round(total * blitz_rate)
    rows = []
    idx = 0
    for week in weeks:
        for _ in range(plays_per_week):
            rows.append(_def_row(
                season, week, defteam,
                sack=1 if idx < n_sacks else 0, qb_hit=1 if idx < n_hits else 0,
                n_rushers=6 if idx < n_blitz else 4,
            ))
            idx += 1
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_team_season(season, range(1, 9), 30, "BUF", 0.08, 0.15, 0.30)
        rows += _make_team_season(season, range(1, 9), 30, "MIA", 0.05, 0.10, 0.15)
    return pd.DataFrame(rows)


def test_resolve_pass_rush_generation_history_real_y1_y2_y3():
    pbp_3yr = _fake_pbp_3yr_prior()
    history = resolve_pass_rush_generation_history(
        pbp_3yr, target_season=2024, team="Buffalo Bills",
    )
    assert history.y1["sack_rate"] == pytest.approx(0.08, abs=0.01)
    assert history.y1["blitz_rate"] == pytest.approx(0.30, abs=0.01)


def test_resolve_pass_rush_generation_history_raises_on_missing_team():
    pbp_3yr = _fake_pbp_3yr_prior()
    with pytest.raises(ValueError, match="No real Pass Rush Generation data"):
        resolve_pass_rush_generation_history(pbp_3yr, target_season=2024, team="Denver Broncos")


def test_resolve_pass_rush_generation_league_stats_and_score():
    pbp_3yr = _fake_pbp_3yr_prior()
    stats = resolve_pass_rush_generation_league_stats(pbp_3yr, 2024, PLACEHOLDER_CONSTANTS)
    assert set(stats.keys()) == {"sack_rate", "pressure_proxy", "blitz_rate"}

    real_constants = PassRushGenerationConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        weights={"sack_rate": 0.5, "pressure_proxy": 0.35, "blitz_rate": 0.15},
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    buf_history = resolve_pass_rush_generation_history(pbp_3yr, 2024, "Buffalo Bills")
    mia_history = resolve_pass_rush_generation_history(pbp_3yr, 2024, "Miami Dolphins")
    buf_result = compute_pass_rush_generation_index(buf_history, real_constants)
    mia_result = compute_pass_rush_generation_index(mia_history, real_constants)
    # BUF generates real pressure at a higher rate on every real metric -- must score higher.
    assert buf_result.score > mia_result.score
