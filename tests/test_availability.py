import math

import pandas as pd
import pytest

from nflverse_pull.availability import (
    STADIUM_COORDS,
    _haversine_miles,
    compute_player_injury_history,
    compute_team_game_log,
)


def test_haversine_one_degree_of_latitude_is_about_69_miles():
    # A pure north-south separation of exactly 1 degree of latitude (same longitude) has a
    # great-circle distance independent of where on Earth it is: 2*pi*R/360, R=3958.8 mi.
    expected = 2 * math.pi * 3958.8 / 360
    assert _haversine_miles((40.0, -75.0), (41.0, -75.0)) == pytest.approx(expected, rel=1e-6)


def test_haversine_same_point_is_zero():
    coord = STADIUM_COORDS["KC"]
    assert _haversine_miles(coord, coord) == pytest.approx(0.0, abs=1e-9)


def test_team_game_log_home_game_is_zero_miles_away_game_is_symmetric():
    sched = pd.DataFrame([
        {"season": 2025, "week": 1, "game_type": "REG", "gameday": "2025-09-07",
         "home_team": "KC", "away_team": "BAL", "home_score": 27, "away_score": 20},
        {"season": 2025, "week": 1, "game_type": "POST", "gameday": "2025-09-08",
         "home_team": "KC", "away_team": "SEA", "home_score": 10, "away_score": 7},
    ])
    out = compute_team_game_log(sched)

    # Postseason game excluded, only the one REG game -> 2 rows (KC home, BAL away).
    assert len(out) == 2
    kc = out[out["Team"] == "Kansas City Chiefs"].iloc[0]
    bal = out[out["Team"] == "Baltimore Ravens"].iloc[0]

    assert kc["Miles Traveled (This Game)"] == pytest.approx(0.0)
    expected_dist = _haversine_miles(STADIUM_COORDS["BAL"], STADIUM_COORDS["KC"])
    assert bal["Miles Traveled (This Game)"] == pytest.approx(expected_dist)
    assert expected_dist > 500  # sanity bound -- KC/BAL are genuinely far apart


def test_team_game_log_raises_on_unmapped_team_abbreviation():
    sched = pd.DataFrame([
        {"season": 2025, "week": 1, "game_type": "REG", "gameday": "2025-09-07",
         "home_team": "ZZZ", "away_team": "BAL", "home_score": 27, "away_score": 20},
    ])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_game_log(sched)


def _injury_row(gsis_id, season, week, status):
    return {"gsis_id": gsis_id, "season": season, "week": week, "report_status": status}


def test_player_injury_history_counts_out_and_doubtful_and_tracks_most_recent_out():
    """
    Player A: Doubtful in (2023, wk3), Out in (2024, wk5), Out in (2025, wk10),
    Questionable (must NOT count) in (2025, wk11).
    Expected: Out/Doubtful Weeks (3-Yr) = 3 (wk3 Doubtful + wk5 Out + wk10 Out; wk11
    Questionable excluded). Most Recent Out = (2025, 10) -- the later of the two Out rows.

    Player B: no injury rows at all -- count 0, recency blank (never omitted as a row).
    Player C: only a 'Questionable' row -- count 0 (Questionable isn't Out/Doubtful).
    """
    rows = [
        _injury_row("QB_A", 2023, 3, "Doubtful"),
        _injury_row("QB_A", 2024, 5, "Out"),
        _injury_row("QB_A", 2025, 10, "Out"),
        _injury_row("QB_A", 2025, 11, "Questionable"),
        _injury_row("QB_C", 2025, 2, "Questionable"),
    ]
    injuries = pd.DataFrame(rows)

    out = compute_player_injury_history(injuries, {"QB_A", "QB_B", "QB_C"})
    out = out.set_index("Player ID")

    assert out.loc["QB_A", "Out/Doubtful Weeks (3-Yr)"] == 3
    assert out.loc["QB_A", "Most Recent Out Season"] == 2025
    assert out.loc["QB_A", "Most Recent Out Week"] == 10

    assert out.loc["QB_B", "Out/Doubtful Weeks (3-Yr)"] == 0
    assert pd.isna(out.loc["QB_B", "Most Recent Out Season"])

    assert out.loc["QB_C", "Out/Doubtful Weeks (3-Yr)"] == 0
    assert pd.isna(out.loc["QB_C", "Most Recent Out Season"])
