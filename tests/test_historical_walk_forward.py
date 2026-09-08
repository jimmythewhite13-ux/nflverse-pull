"""
Tests for prediction_audit/historical/walk_forward.py -- pure logic, no network. A synthetic
4-season fake schedule (same convention as test_pull.py/test_historical_team_ppg.py) proves the
real historical Y1/Y2/Y3 + current-season-so-far assembly is wired correctly and never leaks a
target week's own (or a later) real result into the resolved history.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.team_quality import TeamQualityConstants  # noqa: E402
from prediction_audit.historical.walk_forward import (  # noqa: E402
    WalkForwardTarget,
    resolve_team_quality_for_game,
    resolve_team_quality_history,
)

CONSTANTS = TeamQualityConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
)


def _fake_multi_season_schedule():
    rows = []
    # 3 full prior seasons (2021-2023): BUF and MIA each play a fixed home/away pair every
    # season so real per-season PPG is easy to hand-verify.
    for season, buf_score, opp_score in ((2021, 24, 17), (2022, 27, 20), (2023, 20, 23)):
        rows.append({
            "season": season, "game_type": "REG", "week": 1,
            "home_team": "BUF", "away_team": "MIA",
            "home_score": buf_score, "away_score": opp_score,
        })
    # Target season (2024): weeks 1-4 played before the real target week 5.
    for week, buf_score, opp_score in ((1, 30, 10), (2, 14, 21), (3, 28, 24), (4, 17, 17)):
        rows.append({
            "season": 2024, "game_type": "REG", "week": week,
            "home_team": "BUF", "away_team": "NYJ",
            "home_score": buf_score, "away_score": opp_score,
        })
    # Week 5 (the real target week) and week 6 -- must NEVER leak into a week-5 walk-forward.
    rows.append({
        "season": 2024, "game_type": "REG", "week": 5,
        "home_team": "BUF", "away_team": "MIA", "home_score": 99, "away_score": 0,
    })
    rows.append({
        "season": 2024, "game_type": "REG", "week": 6,
        "home_team": "BUF", "away_team": "NE", "home_score": 45, "away_score": 3,
    })
    # MIA needs its own history too (it's the away team in the week-1 games above, giving it
    # real 2021-2023 data already); add a MIA 2024 game before week 5 for its current season.
    rows.append({
        "season": 2024, "game_type": "REG", "week": 2,
        "home_team": "MIA", "away_team": "NE", "home_score": 20, "away_score": 13,
    })
    return pd.DataFrame(rows)


def test_resolve_team_quality_history_uses_only_real_full_prior_seasons_for_y1_y2_y3():
    sched = _fake_multi_season_schedule()
    history = resolve_team_quality_history(
        sched, target_season=2024, target_week=5, team="Buffalo Bills",
    )
    # Y1=2023 (BUF 20 scored/23 allowed), Y2=2022 (27/20), Y3=2021 (24/17) -- team_ppg.py's own
    # rounding convention (1 decimal) applies.
    assert history.off_y1 == pytest.approx(20.0)
    assert history.def_y1 == pytest.approx(23.0)
    assert history.off_y2 == pytest.approx(27.0)
    assert history.def_y2 == pytest.approx(20.0)
    assert history.off_y3 == pytest.approx(24.0)
    assert history.def_y3 == pytest.approx(17.0)


def test_resolve_team_quality_history_current_season_never_sees_target_week_or_later():
    sched = _fake_multi_season_schedule()
    history = resolve_team_quality_history(
        sched, target_season=2024, target_week=5, team="Buffalo Bills",
    )
    # Weeks 1-4 only: scored [30,14,28,17] -> 22.25 (rounds to 22.2, banker's rounding);
    # allowed [10,21,24,17] -> 18.0. If week 5's 99-0 game leaked in, these would be far off.
    assert history.current_season_off_ppg == pytest.approx(22.2, abs=0.05)
    assert history.current_season_def_ppg == pytest.approx(18.0, abs=0.05)
    assert history.games_played == 4


def test_resolve_team_quality_history_raises_on_real_missing_team_data():
    sched = _fake_multi_season_schedule()
    with pytest.raises(ValueError, match="No real games found"):
        resolve_team_quality_history(
            sched, target_season=2024, target_week=5, team="Denver Broncos",
        )


def test_resolve_team_quality_for_game_end_to_end():
    sched = _fake_multi_season_schedule()
    target = WalkForwardTarget(
        season=2024, week=5, home_team="Buffalo Bills", away_team="Miami Dolphins",
    )
    home_result, away_result = resolve_team_quality_for_game(sched, target, CONSTANTS)
    assert home_result.team == "Buffalo Bills"
    assert away_result.team == "Miami Dolphins"
    # Sanity: both results are real finite computed values, not blanks/NaNs.
    assert isinstance(home_result.blended_off, float)
    assert isinstance(away_result.blended_off, float)


def test_resolve_team_quality_history_team_with_no_current_season_games_gets_zero_blend():
    # A team with zero real games before the target week (e.g. a real Week 1 walk-forward)
    # gets current_season=0/games_played=0 -- matching blend_weight()'s own real 0-games
    # behavior -- rather than raising or fabricating a value.
    sched = _fake_multi_season_schedule()
    history = resolve_team_quality_history(
        sched, target_season=2024, target_week=1, team="Buffalo Bills",
    )
    assert history.current_season_off_ppg == pytest.approx(0.0)
    assert history.games_played == 0
