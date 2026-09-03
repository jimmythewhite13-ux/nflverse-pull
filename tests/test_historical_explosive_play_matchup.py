"""
Tests for prediction_audit/historical/explosive_play_matchup_historical.py -- pure logic, no
network. Combines pass + run play fixtures (same shapes as test_historical_pass_defense_
matchup.py / test_historical_run_defense_matchup.py, since this module composes those two
already-built resolvers), extended with real air_yards/yards_after_catch for the deep-pass/
YAC metrics this tab adds on top.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.explosive_play_matchup import (  # noqa: E402
    ExplosivePlayMatchupConstants,
    compute_explosive_play_matchup,
)
from prediction_audit.engine.pass_defense_matchup import PassDefenseMatchupConstants  # noqa: E402
from prediction_audit.engine.run_defense_matchup import RunDefenseMatchupConstants  # noqa: E402
from prediction_audit.historical.explosive_play_matchup_historical import (  # noqa: E402
    resolve_explosive_play_matchup_history,
    resolve_explosive_play_matchup_league_stats,
)

PD_CONSTANTS = PassDefenseMatchupConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    weights={"epa_dropback": 0.3, "pass_success": 0.25, "completion_pct": 0.15, "nya": 0.15,
             "explosive_pass": 0.15},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(
        ["epa_dropback", "pass_success", "completion_pct", "nya", "explosive_pass"], 0.0,
    ),
    league_std=dict.fromkeys(
        ["epa_dropback", "pass_success", "completion_pct", "nya", "explosive_pass"], 1.0,
    ),
)
RD_CONSTANTS = RunDefenseMatchupConstants(
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
EP_PLACEHOLDER = ExplosivePlayMatchupConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    league_avg_pass_off=0.0, league_std_pass_off=1.0,
    league_avg_run_off=0.0, league_std_run_off=1.0,
    league_avg_deep_pass_allowed=0.0, league_std_deep_pass_allowed=1.0,
    league_avg_yac_allowed=0.0, league_std_yac_allowed=1.0,
    pass_prevention_w_explosive_pass_allowed=0.5, pass_prevention_w_deep_pass_allowed=0.3,
    pass_prevention_w_yac_allowed=0.2,
)


def _pass_row(season, defteam, posteam, epa, success, complete, yards_gained, air_yards,
              yac, sack=0):
    return {
        "season": season, "season_type": "REG", "defteam": defteam, "posteam": posteam,
        "play_type": "pass", "pass_attempt": 1, "sack": sack, "epa": epa, "success": success,
        "complete_pass": complete, "yards_gained": yards_gained,
        "passing_yards": yards_gained if not sack else 0, "pass_oe": 0.0,
        "air_yards": air_yards, "yards_after_catch": yac if complete else 0,
    }


def _run_row(season, defteam, posteam, epa, success, yards_gained, stuffed):
    return {
        "season": season, "season_type": "REG", "defteam": defteam, "posteam": posteam,
        "play_type": "run", "epa": epa, "success": success, "yards_gained": yards_gained,
        "tackled_for_loss": 1 if stuffed else 0, "pass_attempt": 0, "sack": 0,
        "complete_pass": 0, "air_yards": 0, "yards_after_catch": 0,
    }


def _make_team_pass_season(season, n_plays, defteam, posteam, epa, success_rate, comp_pct,
                            explosive_rate, deep_rate, deep_comp_rate, yac):
    """Deep plays (air_yards>=20, real DEEP_PASS_AIR_YARDS threshold) are a SEPARATE,
    non-overlapping index range from the general pass population, each with its own real,
    independently-controlled completion rate -- avoids the two rates bleeding into each
    other's real counts."""
    rows = []
    n_deep = round(n_plays * deep_rate)
    n_general = n_plays - n_deep
    n_success = round(n_plays * success_rate)
    n_general_complete = round(n_general * comp_pct)
    n_explosive = round(n_general * explosive_rate)
    n_deep_comp = round(n_deep * deep_comp_rate)

    idx = 0
    for i in range(n_general):
        rows.append(_pass_row(
            season, defteam, posteam, epa,
            success=1 if idx < n_success else 0,
            complete=1 if i < n_general_complete else 0,
            yards_gained=(20 + 6) if i < n_explosive else 6,
            air_yards=5, yac=yac,
        ))
        idx += 1
    for i in range(n_deep):
        rows.append(_pass_row(
            season, defteam, posteam, epa,
            success=1 if idx < n_success else 0,
            complete=1 if i < n_deep_comp else 0,
            yards_gained=6, air_yards=25, yac=yac,
        ))
        idx += 1
    return rows


def _make_team_run_season(season, n_plays, defteam, posteam, epa, success_rate,
                           explosive_rate, stuff_rate):
    rows = []
    n_success = round(n_plays * success_rate)
    n_explosive = round(n_plays * explosive_rate)
    n_stuffed = round(n_plays * stuff_rate)
    for i in range(n_plays):
        real_yards = 0 if i < n_stuffed else ((15 + 4) if i < n_explosive else 4)
        rows.append(_run_row(
            season, defteam, posteam, epa, success=1 if i < n_success else 0,
            yards_gained=real_yards, stuffed=i < n_stuffed,
        ))
    return rows


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        # BUF: strong pass offense, strong pass/run defense.
        rows += _make_team_pass_season(
            season, 200, "MIA", "BUF", 0.10, 0.50, 0.65, 0.18, 0.15, 0.30, 4.0,
        )
        rows += _make_team_pass_season(
            season, 200, "BUF", "MIA", -0.05, 0.42, 0.62, 0.10, 0.12, 0.40, 6.0,
        )
        rows += _make_team_run_season(season, 200, "MIA", "BUF", 0.05, 0.46, 0.15, 0.14)
        rows += _make_team_run_season(season, 200, "BUF", "MIA", -0.06, 0.38, 0.08, 0.22)
    return pd.DataFrame(rows)


def test_resolve_explosive_play_matchup_history_real_y1_y2_y3():
    pbp_3yr = _fake_pbp_3yr_prior()
    history = resolve_explosive_play_matchup_history(
        pbp_3yr, target_season=2024, team="Buffalo Bills",
        pass_defense_constants=PD_CONSTANTS, run_defense_constants=RD_CONSTANTS,
    )
    # Explosive Pass Rate (Off) is computed over ALL real pass plays (real
    # compute_team_season_matchup_metrics convention), not just the non-deep subset the
    # fixture's own explosive_rate parameter targets: 31 explosive / 200 total = 0.155.
    assert history.pass_off_y1 == pytest.approx(0.155, abs=0.01)
    assert isinstance(history.explosive_pass_allowed_z_ref, float)
    assert isinstance(history.explosive_run_allowed_z_ref, float)


def test_resolve_explosive_play_matchup_history_raises_on_missing_team():
    pbp_3yr = _fake_pbp_3yr_prior()
    with pytest.raises(ValueError):
        resolve_explosive_play_matchup_history(
            pbp_3yr, target_season=2024, team="Denver Broncos",
            pass_defense_constants=PD_CONSTANTS, run_defense_constants=RD_CONSTANTS,
        )


def test_resolve_explosive_play_matchup_league_stats_and_full_result():
    pbp_3yr = _fake_pbp_3yr_prior()
    stats = resolve_explosive_play_matchup_league_stats(
        pbp_3yr, 2024, PD_CONSTANTS, RD_CONSTANTS, EP_PLACEHOLDER,
    )
    assert set(stats.keys()) == {"pass_off", "run_off", "deep_pass_allowed", "yac_allowed"}

    real_constants = ExplosivePlayMatchupConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        league_avg_pass_off=stats["pass_off"]["avg"], league_std_pass_off=stats["pass_off"]["std"],
        league_avg_run_off=stats["run_off"]["avg"], league_std_run_off=stats["run_off"]["std"],
        league_avg_deep_pass_allowed=stats["deep_pass_allowed"]["avg"],
        league_std_deep_pass_allowed=stats["deep_pass_allowed"]["std"],
        league_avg_yac_allowed=stats["yac_allowed"]["avg"],
        league_std_yac_allowed=stats["yac_allowed"]["std"],
        pass_prevention_w_explosive_pass_allowed=0.5, pass_prevention_w_deep_pass_allowed=0.3,
        pass_prevention_w_yac_allowed=0.2,
    )
    history = resolve_explosive_play_matchup_history(
        pbp_3yr, 2024, "Buffalo Bills", PD_CONSTANTS, RD_CONSTANTS,
    )
    result = compute_explosive_play_matchup(history, real_constants)
    assert isinstance(result.pass_prevention_composite_z, float)
    assert isinstance(result.run_prevention_z, float)
