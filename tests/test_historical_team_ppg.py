"""
Tests for prediction_audit/historical/team_ppg.py -- pure logic, no network (same fake-schedule
convention as test_pull.py). Focus: the real no-future-information guard (`through_week`) is
strict (`<`, not `<=`), and full-season aggregation matches nflverse_pull.pull's own already-
proven transform_to_team_season() exactly.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nflverse_pull.pull import transform_to_team_season  # noqa: E402
from prediction_audit.historical.team_ppg import (  # noqa: E402
    league_average_ppg,
    team_season_ppg,
)


def _fake_schedule():
    # BUF: wk1 home 24-10 (scored 24, allowed 10), wk2 away 17-20 at MIA (scored 17, allowed 20),
    # wk3 home 30-14 vs NYJ. MIA: wk2 home 20-17 vs BUF only.
    return pd.DataFrame([
        {"season": 2023, "game_type": "REG", "week": 1, "home_team": "BUF", "away_team": "NYJ",
         "home_score": 24, "away_score": 10},
        {"season": 2023, "game_type": "REG", "week": 2, "home_team": "MIA", "away_team": "BUF",
         "home_score": 20, "away_score": 17},
        {"season": 2023, "game_type": "REG", "week": 3, "home_team": "BUF", "away_team": "NYJ",
         "home_score": 30, "away_score": 14},
        {"season": 2023, "game_type": "POST", "week": 20, "home_team": "BUF", "away_team": "MIA",
         "home_score": 40, "away_score": 3},  # postseason -- must be excluded
        {"season": 2022, "game_type": "REG", "week": 1, "home_team": "BUF", "away_team": "NYJ",
         "home_score": 16, "away_score": 9},  # different season -- must be excluded
    ])


def test_through_week_excludes_the_target_week_itself():
    # A week-3 walk-forward prediction must NOT see week 3's own result.
    through_3 = team_season_ppg(_fake_schedule(), season=2023, through_week=3)
    buf = through_3[through_3["Team"] == "Buffalo Bills"].iloc[0]
    # Only weeks 1-2 count: scored [24, 17] -> 20.5; allowed [10, 20] -> 15.0
    assert buf["Off PPG"] == pytest.approx(20.5)
    assert buf["Def PPG"] == pytest.approx(15.0)
    assert buf["Games Played"] == 2


def test_through_week_1_means_zero_real_games_seen():
    through_1 = team_season_ppg(_fake_schedule(), season=2023, through_week=1)
    assert "Buffalo Bills" not in set(through_1["Team"])


def test_full_season_none_through_week_includes_everything_real_in_that_season():
    full = team_season_ppg(_fake_schedule(), season=2023, through_week=None)
    buf = full[full["Team"] == "Buffalo Bills"].iloc[0]
    # weeks 1-3 (postseason/2022 excluded): scored [24,17,30]->23.67; allowed [10,20,14]->14.67
    assert buf["Off PPG"] == pytest.approx(23.7, abs=0.05)
    assert buf["Def PPG"] == pytest.approx(14.7, abs=0.05)
    assert buf["Games Played"] == 3


def test_full_season_matches_transform_to_team_season_exactly():
    sched = _fake_schedule()
    mine = team_season_ppg(sched, season=2023, through_week=None)
    reference = transform_to_team_season(sched)
    reference_2023 = reference[reference["Season"] == 2023]
    buf_mine = mine[mine["Team"] == "Buffalo Bills"].iloc[0]
    buf_ref = reference_2023[reference_2023["Team"] == "Buffalo Bills"].iloc[0]
    assert buf_mine["Off PPG"] == pytest.approx(buf_ref["Off PPG"])
    assert buf_mine["Def PPG"] == pytest.approx(buf_ref["Def PPG"])


def test_different_season_never_leaks_in():
    through_3 = team_season_ppg(_fake_schedule(), season=2023, through_week=3)
    buf = through_3[through_3["Team"] == "Buffalo Bills"].iloc[0]
    # If the real 2022 week-1 game (16-9) leaked in, Off PPG would shift from 20.5.
    assert buf["Off PPG"] == pytest.approx(20.5)


def test_postseason_never_leaks_in():
    full = team_season_ppg(_fake_schedule(), season=2023, through_week=None)
    buf = full[full["Team"] == "Buffalo Bills"].iloc[0]
    # If the real postseason game (40-3) leaked in, Games Played would be 4, not 3.
    assert buf["Games Played"] == 3


def test_team_with_zero_real_games_in_slice_is_absent_not_fabricated():
    through_1 = team_season_ppg(_fake_schedule(), season=2023, through_week=1)
    assert "New York Jets" not in set(through_1["Team"])


def test_league_average_ppg():
    full = team_season_ppg(_fake_schedule(), season=2023, through_week=None)
    avg = league_average_ppg(full)
    assert avg["off"] == pytest.approx(full["Off PPG"].mean())
    assert avg["def"] == pytest.approx(full["Def PPG"].mean())


def test_league_average_ppg_raises_on_empty_input():
    empty = team_season_ppg(_fake_schedule(), season=2023, through_week=1)
    with pytest.raises(ValueError):
        league_average_ppg(empty)


def test_historical_relocated_franchise_abbreviations_resolve_to_current_name():
    # Real historical abbreviations nflverse's own schedule data uses for seasons before each
    # real franchise relocation -- must resolve to the CURRENT franchise name (real continuity),
    # not raise "no mapping" the way an unmapped abbreviation correctly does elsewhere.
    sched = pd.DataFrame([
        {"season": 2019, "game_type": "REG", "week": 1, "home_team": "OAK", "away_team": "DEN",
         "home_score": 24, "away_score": 16},
        {"season": 2016, "game_type": "REG", "week": 1, "home_team": "SD", "away_team": "KC",
         "home_score": 27, "away_score": 24},
        {"season": 2015, "game_type": "REG", "week": 1, "home_team": "STL", "away_team": "SEA",
         "home_score": 34, "away_score": 31},
    ])
    oak = team_season_ppg(sched, season=2019)
    assert "Las Vegas Raiders" in set(oak["Team"])
    sd = team_season_ppg(sched, season=2016)
    assert "Los Angeles Chargers" in set(sd["Team"])
    stl = team_season_ppg(sched, season=2015)
    assert "Los Angeles Rams" in set(stl["Team"])
