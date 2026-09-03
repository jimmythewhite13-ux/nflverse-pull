"""
Tests for prediction_audit/historical/run_defense_matchup_historical.py -- pure logic, no
network. Team-level, no role resolution -- focus is real Y1/Y2/Y3 assembly and real
league-wide stats feeding a full real score with the correct partial-inversion direction
(Stuff Rate deliberately NOT inverted, unlike the other 4 metrics).
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.run_defense_matchup import (  # noqa: E402
    RunDefenseMatchupConstants,
    compute_run_defense_matchup,
)
from prediction_audit.historical.run_defense_matchup_historical import (  # noqa: E402
    resolve_run_defense_matchup_history,
    resolve_run_defense_matchup_league_stats,
)

PLACEHOLDER_CONSTANTS = RunDefenseMatchupConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    weights={"epa_rush": 0.3, "run_success": 0.25, "ypc": 0.2, "explosive_run": 0.15,
             "stuff_rate": 0.1},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(
        ["epa_rush", "run_success", "ypc", "explosive_run", "stuff_rate"], 0.0,
    ),
    league_std=dict.fromkeys(
        ["epa_rush", "run_success", "ypc", "explosive_run", "stuff_rate"], 1.0,
    ),
)


def _run_row(season, defteam, posteam, epa, success, yards_gained, stuffed):
    return {
        "season": season, "season_type": "REG", "defteam": defteam, "posteam": posteam,
        "play_type": "run", "epa": epa, "success": success, "yards_gained": yards_gained,
        "run_gap": "guard", "tackled_for_loss": 1 if stuffed else 0,
        "yards_after_catch": 0, "pass_attempt": 0, "sack": 0, "complete_pass": 0,
    }


def _make_team_season(season, n_plays, defteam, posteam, epa, success_rate, yards,
                       explosive_rate, stuff_rate):
    rows = []
    n_success = round(n_plays * success_rate)
    n_explosive = round(n_plays * explosive_rate)
    n_stuffed = round(n_plays * stuff_rate)
    for i in range(n_plays):
        real_yards = 0 if i < n_stuffed else ((15 + yards) if i < n_explosive else yards)
        rows.append(_run_row(
            season, defteam, posteam, epa, success=1 if i < n_success else 0,
            yards_gained=real_yards, stuffed=i < n_stuffed,
        ))
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows += _make_team_season(season, 200, "BUF", "MIA", -0.06, 0.38, 4.0, 0.08, 0.22)
        rows += _make_team_season(season, 200, "MIA", "BUF", 0.05, 0.46, 5.2, 0.15, 0.14)
    return pd.DataFrame(rows)


def test_resolve_run_defense_matchup_history_real_y1_y2_y3():
    pbp_3yr = _fake_pbp_3yr_prior()
    history = resolve_run_defense_matchup_history(
        pbp_3yr, target_season=2024, team="Buffalo Bills",
    )
    assert history.y1["epa_rush"] == pytest.approx(-0.06, abs=0.01)


def test_resolve_run_defense_matchup_history_raises_on_missing_team():
    pbp_3yr = _fake_pbp_3yr_prior()
    with pytest.raises(ValueError, match="No real Run Defense data"):
        resolve_run_defense_matchup_history(pbp_3yr, target_season=2024, team="Denver Broncos")


def test_resolve_run_defense_matchup_league_stats_and_score_direction():
    pbp_3yr = _fake_pbp_3yr_prior()
    stats = resolve_run_defense_matchup_league_stats(pbp_3yr, 2024, PLACEHOLDER_CONSTANTS)
    assert set(stats.keys()) == {
        "epa_rush", "run_success", "ypc", "explosive_run", "stuff_rate",
    }

    real_constants = RunDefenseMatchupConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        weights={"epa_rush": 0.3, "run_success": 0.25, "ypc": 0.2, "explosive_run": 0.15,
                 "stuff_rate": 0.1},
        score_baseline=50, points_per_sd=10,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    buf_history = resolve_run_defense_matchup_history(pbp_3yr, 2024, "Buffalo Bills")
    mia_history = resolve_run_defense_matchup_history(pbp_3yr, 2024, "Miami Dolphins")
    buf_result = compute_run_defense_matchup(buf_history, real_constants)
    mia_result = compute_run_defense_matchup(mia_history, real_constants)
    # BUF allows less AND stuffs more (better real run defense on every metric) -- must score
    # higher than MIA after the real mixed-inversion handling.
    assert buf_result.score > mia_result.score
