import pandas as pd
import pytest

from nflverse_pull.pull import TEAM_NAMES, transform_to_team_season


def test_team_names_covers_all_32_teams():
    assert len(TEAM_NAMES) == 32
    assert len(set(TEAM_NAMES.values())) == 32  # no duplicate full names


def test_team_names_known_mappings():
    assert TEAM_NAMES["BUF"] == "Buffalo Bills"
    assert TEAM_NAMES["SF"] == "San Francisco 49ers"
    assert TEAM_NAMES["LA"] == "Los Angeles Rams"
    assert TEAM_NAMES["LAC"] == "Los Angeles Chargers"


def _fake_schedule():
    # Two teams, one season, two games: BUF beats MIA 24-10 at home,
    # then MIA beats BUF 20-17 at home (BUF away). Also include a non-REG
    # game and an unplayed future game to confirm both get filtered out.
    return pd.DataFrame([
        {"season": 2025, "game_type": "REG", "home_team": "BUF", "away_team": "MIA",
         "home_score": 24, "away_score": 10},
        {"season": 2025, "game_type": "REG", "home_team": "MIA", "away_team": "BUF",
         "home_score": 20, "away_score": 17},
        {"season": 2025, "game_type": "POST", "home_team": "BUF", "away_team": "MIA",
         "home_score": 30, "away_score": 27},  # postseason -- must be excluded
        {"season": 2025, "game_type": "REG", "home_team": "BUF", "away_team": "NYJ",
         "home_score": None, "away_score": None},  # not yet played -- must be excluded
    ])


def test_transform_computes_correct_ppg():
    out = transform_to_team_season(_fake_schedule())

    buf = out[out["Team"] == "Buffalo Bills"].iloc[0]
    mia = out[out["Team"] == "Miami Dolphins"].iloc[0]

    # BUF: scored 24 (home) and 17 (away) -> avg 20.5; allowed 10 and 20 -> avg 15.0
    assert buf["Off PPG"] == pytest.approx(20.5)
    assert buf["Def PPG"] == pytest.approx(15.0)

    # MIA: scored 10 (away) and 20 (home) -> avg 15.0; allowed 24 and 17 -> avg 20.5
    assert mia["Off PPG"] == pytest.approx(15.0)
    assert mia["Def PPG"] == pytest.approx(20.5)


def test_transform_excludes_postseason_and_unplayed_games():
    out = transform_to_team_season(_fake_schedule())
    # Only BUF and MIA should appear -- NYJ's row had no score and must be dropped
    assert set(out["Team"]) == {"Buffalo Bills", "Miami Dolphins"}


def test_transform_output_shape_and_columns():
    out = transform_to_team_season(_fake_schedule())
    assert list(out.columns) == ["Team", "Season", "Off PPG", "Def PPG"]
    assert len(out) == 2  # one row per team for the single season present


def test_transform_rounds_ppg_to_one_decimal_place():
    # BUF scores 10, 10, 11 across three games (avg 31/3 = 10.333...) and allows
    # 5 every time (avg 5.0, already exact). Only the offense average actually
    # needs rounding, which none of the other fixtures exercise since they all
    # land on clean halves.
    sched = pd.DataFrame([
        {"season": 2025, "game_type": "REG", "home_team": "BUF", "away_team": "MIA",
         "home_score": 10, "away_score": 5},
        {"season": 2025, "game_type": "REG", "home_team": "BUF", "away_team": "MIA",
         "home_score": 10, "away_score": 5},
        {"season": 2025, "game_type": "REG", "home_team": "BUF", "away_team": "MIA",
         "home_score": 11, "away_score": 5},
    ])

    out = transform_to_team_season(sched)
    buf = out[out["Team"] == "Buffalo Bills"].iloc[0]

    assert buf["Off PPG"] == pytest.approx(10.3)
    assert buf["Def PPG"] == pytest.approx(5.0)


def test_transform_raises_on_missing_columns():
    bad_df = pd.DataFrame([{"season": 2025, "home_team": "BUF"}])  # missing required columns
    with pytest.raises(ValueError, match="missing expected columns"):
        transform_to_team_season(bad_df)


def test_transform_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([
        {"season": 2025, "game_type": "REG", "home_team": "ZZZ", "away_team": "MIA",
         "home_score": 20, "away_score": 10},
    ])
    with pytest.raises(ValueError, match="No full-name mapping"):
        transform_to_team_season(df)
