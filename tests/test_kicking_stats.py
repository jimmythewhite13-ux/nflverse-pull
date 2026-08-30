import pandas as pd
import pytest

from nflverse_pull.kicking_stats import (
    DISTANCE_BUCKET_SIZE,
    MIN_QUALIFYING_FG_ATTEMPTS,
    SEASON_STATS_COLUMNS,
    compute_team_season_kicking_stats,
)


def _fg_rows(n, made, distance, kicker_id, kicker_name, season, posteam):
    return [
        {"season_type": "REG", "play_type": "field_goal", "posteam": posteam,
         "kicker_player_id": kicker_id, "kicker_player_name": kicker_name,
         "season": season, "field_goal_result": "made" if made else "missed",
         "kick_distance": distance}
        for _ in range(n)
    ]


def _xp_rows(n, good, kicker_id, kicker_name, season, posteam):
    return [
        {"season_type": "REG", "play_type": "extra_point", "posteam": posteam,
         "kicker_player_id": kicker_id, "kicker_player_name": kicker_name,
         "season": season, "extra_point_result": "good" if good else "failed"}
        for _ in range(n)
    ]


def _fake_pbp():
    """
    K1 "A.Kicker" (BUF, 2025), 20 FG attempts (above MIN_QUALIFYING_FG_ATTEMPTS=15):
      - 10 attempts at 40 yards (bucket 40): all made
      - 10 attempts at 50 yards (bucket 50): 5 made, 5 missed
    Plus 18 XP attempts, 16 good.

    League-wide bucket rates (built from ALL rows, i.e. just this one kicker here):
      bucket 40: 10/10 made = 1.0 expected
      bucket 50: 5/10 made = 0.5 expected

    FG% Over Expected = mean of (made[1/0] - expected) across all 20 attempts:
      10 attempts @ bucket 40: made=1, expected=1.0 -> 0 each (10 x 0 = 0)
      5 attempts @ bucket 50 made: made=1, expected=0.5 -> 0.5 each (5 x 0.5 = 2.5)
      5 attempts @ bucket 50 missed: made=0, expected=0.5 -> -0.5 each (5 x -0.5 = -2.5)
      sum = 0, / 20 = 0.0 (a kicker who exactly matches the league's own distance-implied
      rate nets to zero over-expected, by construction of this fixture)
    FG% = 15/20 = 0.75
    XP% = 16/18 = 0.8888...

    K2 "B.Short" (BUF, 2025): 14 FG attempts only -- one below the 15-attempt threshold,
    must be excluded entirely (not zero-filled).
    """
    k1 = (
        _fg_rows(10, True, 40, "00-1111111", "A.Kicker", 2025, "BUF")
        + _fg_rows(5, True, 50, "00-1111111", "A.Kicker", 2025, "BUF")
        + _fg_rows(5, False, 50, "00-1111111", "A.Kicker", 2025, "BUF")
        + _xp_rows(16, True, "00-1111111", "A.Kicker", 2025, "BUF")
        + _xp_rows(2, False, "00-1111111", "A.Kicker", 2025, "BUF")
    )
    k2 = _fg_rows(14, True, 30, "00-2222222", "B.Short", 2025, "BUF")
    return pd.DataFrame(k1 + k2)


def test_kicking_stats_computes_expected_metrics_and_excludes_below_threshold():
    out = compute_team_season_kicking_stats(_fake_pbp())

    assert list(out.columns) == SEASON_STATS_COLUMNS
    assert MIN_QUALIFYING_FG_ATTEMPTS == 15
    assert DISTANCE_BUCKET_SIZE == 5

    assert len(out) == 1  # K2 (14 attempts) excluded
    k1 = out.iloc[0]

    assert k1["Player Name"] == "A.Kicker"
    assert k1["Team"] == "Buffalo Bills"
    assert k1["FG Attempts"] == 20
    assert k1["FG% Over Expected"] == pytest.approx(0.0)
    assert k1["FG%"] == pytest.approx(0.75)
    assert k1["XP%"] == pytest.approx(16 / 18)


def test_kicking_stats_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame(_fg_rows(15, True, 40, "00-9999999", "Z.Zed", 2025, "ZZZ"))
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_kicking_stats(df)


def test_kicking_stats_rewards_a_kicker_who_beats_the_league_distance_baseline():
    # Two kickers both attempt 50-yarders (bucket rate = 50% across both combined), but
    # A.Better makes all of his while B.Worse misses all of his -- A.Better's FG% Over
    # Expected must be positive, B.Worse's must be negative, by the same magnitude.
    better = _fg_rows(15, True, 50, "00-3333333", "A.Better", 2025, "MIA")
    worse = _fg_rows(15, False, 50, "00-4444444", "B.Worse", 2025, "NYJ")
    out = compute_team_season_kicking_stats(pd.DataFrame(better + worse)).set_index("Player Name")

    assert out.loc["A.Better", "FG% Over Expected"] == pytest.approx(0.5)
    assert out.loc["B.Worse", "FG% Over Expected"] == pytest.approx(-0.5)


def test_kicking_stats_flags_rookie_season_as_first_qualifying_season():
    below_threshold_2024 = _fg_rows(10, True, 30, "00-5555555", "R.Young", 2024, "MIA")
    qualifying_2025 = _fg_rows(15, True, 30, "00-5555555", "R.Young", 2025, "MIA")
    pbp = pd.DataFrame(below_threshold_2024 + qualifying_2025)

    out = compute_team_season_kicking_stats(pbp)

    assert list(out["Season"]) == [2025]  # 2024 excluded, not zero-filled
    assert out.iloc[0]["Is Rookie Season"]
