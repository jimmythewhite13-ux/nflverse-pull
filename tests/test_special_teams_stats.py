import pandas as pd
import pytest

from nflverse_pull.special_teams_stats import (
    MIN_QUALIFYING_KR_RETURNS,
    MIN_QUALIFYING_PR_RETURNS,
    MIN_QUALIFYING_PUNTS,
    compute_player_season_punting_rates,
    compute_player_season_punting_stats,
    compute_player_season_return_rates,
    compute_player_season_return_stats,
    compute_team_season_special_teams_stats,
)


def _punt(posteam, season, distance, return_yards=0, blocked=0, punter=None):
    return {
        "season_type": "REG", "posteam": posteam, "season": season,
        "punt_attempt": 1, "punt_blocked": blocked,
        "kick_distance": distance, "return_yards": return_yards,
        "punter_player_id": punter,
        "kickoff_attempt": 0, "kickoff_returner_player_id": None,
        "punt_returner_player_id": None, "defteam": None,
    }


def _return(defteam, season, return_yards, kind, player=None):
    row = {
        "season_type": "REG", "defteam": defteam, "season": season,
        "return_yards": return_yards, "punt_attempt": 0, "kickoff_attempt": 0,
        "punt_blocked": 0, "posteam": None, "kick_distance": None,
        "punter_player_id": None,
        "kickoff_returner_player_id": None, "punt_returner_player_id": None,
    }
    row[f"{kind}_returner_player_id"] = player
    return row


def test_team_special_teams_stats_computes_expected_averages():
    """
    BUF punts, 2025: 3 real punts (blocked one excluded):
      45 yards, 5 return yards -> net 40
      40 yards, 0 return yards -> net 40
      50 yards, 10 return yards -> net 40 (a 4th "punt" is blocked, excluded entirely)
    Net Punt Average = 40.0

    BUF returns, 2025: 2 kickoff returns (20, 30) + 1 punt return (10)
    Return Average = (20+30+10)/3 = 20.0
    """
    rows = [
        _punt("BUF", 2025, 45, 5),
        _punt("BUF", 2025, 40, 0),
        _punt("BUF", 2025, 50, 10),
        _punt("BUF", 2025, 60, 0, blocked=1),  # excluded
        _return("BUF", 2025, 20, "kickoff", player="RK1"),
        _return("BUF", 2025, 30, "kickoff", player="RK1"),
        _return("BUF", 2025, 10, "punt", player="RP1"),
    ]
    out = compute_team_season_special_teams_stats(pd.DataFrame(rows)).set_index("Team")
    row = out.loc["Buffalo Bills"]
    assert row["Net Punt Average"] == pytest.approx(40.0)
    assert row["Return Average"] == pytest.approx(20.0)


def test_team_special_teams_stats_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([_punt("ZZZ", 2025, 45, 5)])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_special_teams_stats(df)


def test_player_punting_stats_hand_computed():
    rows = [
        _punt("BUF", 2025, 45, 5, punter="P1"),
        _punt("BUF", 2025, 40, 0, punter="P1"),
        _punt("BUF", 2025, 60, 0, blocked=1, punter="P1"),  # excluded
    ]
    out = compute_player_season_punting_stats(pd.DataFrame(rows)).set_index("Player ID")
    assert out.loc["P1", "Net Punt Average"] == pytest.approx((40 + 40) / 2)
    assert out.loc["P1", "Punts"] == 2
    assert out.loc["P1", "Team"] == "Buffalo Bills"


def test_player_return_stats_tracks_kr_and_pr_separately():
    rows = [
        _return("BUF", 2025, 20, "kickoff", player="RK1"),
        _return("BUF", 2025, 30, "kickoff", player="RK1"),
        _return("BUF", 2025, 8, "punt", player="RP1"),
    ]
    out = compute_player_season_return_stats(pd.DataFrame(rows)).set_index("Player ID")
    assert out.loc["RK1", "KR Average"] == pytest.approx(25.0)
    assert out.loc["RK1", "KR Returns"] == 2
    assert pd.isna(out.loc["RK1", "PR Average"])  # never returned a punt -- not zero
    assert out.loc["RP1", "PR Average"] == pytest.approx(8.0)
    assert pd.isna(out.loc["RP1", "KR Average"])


def test_punting_rates_excludes_below_threshold_and_attaches_rookie_flag():
    assert MIN_QUALIFYING_PUNTS == 20
    rows = (
        [_punt("BUF", 2025, 45, 5, punter="P1")] * 20  # qualifies
        + [_punt("MIA", 2025, 40, 0, punter="P2")] * 5  # below threshold -- excluded
    )
    rosters = pd.DataFrame([{"player_id": "P1", "season": 2025, "entry_year": 2020}])

    out = compute_player_season_punting_rates(pd.DataFrame(rows), rosters)
    assert len(out) == 1  # P2 excluded, not zero-filled
    assert out.iloc[0]["Player ID"] == "P1"
    assert out.iloc[0]["Punts"] == 20
    assert out.iloc[0]["Is Rookie Season"] == False  # noqa: E712 (numpy bool from merge)


def test_return_rates_qualify_kr_and_pr_independently():
    assert MIN_QUALIFYING_KR_RETURNS == 5
    assert MIN_QUALIFYING_PR_RETURNS == 10
    rows = (
        [_return("BUF", 2025, 20, "kickoff", player="RK1")] * 5  # KR qualifies
        + [_return("BUF", 2025, 8, "punt", player="RK1")] * 3  # PR below threshold
        + [_return("MIA", 2025, 10, "punt", player="RP1")] * 10  # PR qualifies
    )
    rosters = pd.DataFrame([
        {"player_id": "RK1", "season": 2025, "entry_year": 2025},  # real rookie season
        {"player_id": "RP1", "season": 2025, "entry_year": 2020},
    ])

    out = compute_player_season_return_rates(pd.DataFrame(rows), rosters).set_index("Player ID")
    assert out.loc["RK1", "KR Returns"] == 5
    assert pd.isna(out.loc["RK1", "PR Average"])  # 3 real PR returns, below the 10 floor
    assert out.loc["RK1", "Is Rookie Season"] == True  # noqa: E712 (numpy bool from merge)
    assert out.loc["RP1", "PR Returns"] == 10
    assert pd.isna(out.loc["RP1", "KR Average"])  # never returned a kickoff -- not zero


def test_return_rates_drops_player_season_qualifying_on_neither_side():
    rows = [_return("BUF", 2025, 20, "kickoff", player="RK1")] * 2  # below both floors
    rosters = pd.DataFrame(columns=["player_id", "season", "entry_year"])

    out = compute_player_season_return_rates(pd.DataFrame(rows), rosters)
    assert len(out) == 0
