import pandas as pd
import pytest

from nflverse_pull.rb_stats import (
    MIN_QUALIFYING_CARRIES,
    SEASON_STATS_COLUMNS,
    compute_team_season_rb_stats,
)


def _run_rows(n, epa, success, yards, rusher_id, rusher_name, season, posteam):
    return [
        {"season_type": "REG", "play_type": "run", "posteam": posteam,
         "rusher_player_id": rusher_id, "rusher_player_name": rusher_name,
         "rusher_id": rusher_id, "rusher": rusher_name,
         "season": season, "epa": epa, "success": success, "yards_gained": yards}
        for _ in range(n)
    ]


def _fake_pbp():
    """
    RB1 "A.Back" (BUF, 2025), 50 carries total (exactly MIN_QUALIFYING_CARRIES):
      - 40 carries: epa=0.1, success=1, yards_gained=5
      - 10 carries: epa=-0.3, success=0, yards_gained=1

    Rushing EPA/Play = (40*0.1 + 10*-0.3) / 50 = (4.0 - 3.0) / 50 = 0.02
    Rushing Success Rate = 40 / 50 = 0.8
    YPC = (40*5 + 10*1) / 50 = 210 / 50 = 4.2

    RB2 "B.Mop" (BUF, 2025): 49 carries only -- one below the 50-carry threshold, must be
    excluded entirely (not zero-filled).
    """
    rb1 = (
        _run_rows(40, 0.1, 1, 5, "00-1111111", "A.Back", 2025, "BUF")
        + _run_rows(10, -0.3, 0, 1, "00-1111111", "A.Back", 2025, "BUF")
    )
    rb2 = _run_rows(49, 0.0, 1, 3, "00-2222222", "B.Mop", 2025, "BUF")
    return pd.DataFrame(rb1 + rb2)


def test_rb_stats_computes_expected_metrics_and_excludes_below_threshold():
    out = compute_team_season_rb_stats(_fake_pbp())

    assert list(out.columns) == SEASON_STATS_COLUMNS
    assert MIN_QUALIFYING_CARRIES == 50

    assert len(out) == 1  # RB2 (49 carries) excluded
    rb1 = out.iloc[0]

    assert rb1["Player Name"] == "A.Back"
    assert rb1["Team"] == "Buffalo Bills"
    assert rb1["Carries"] == 50
    assert rb1["Rushing EPA/Play"] == pytest.approx(0.02)
    assert rb1["Rushing Success Rate"] == pytest.approx(0.8)
    assert rb1["YPC"] == pytest.approx(4.2)


def test_rb_stats_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame(_run_rows(50, 0.1, 1, 5, "00-9999999", "Z.Zed", 2025, "ZZZ"))
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_rb_stats(df)


def test_rb_stats_qb_scramble_null_pattern_does_not_break_grouping():
    # A QB scramble on a run play has rusher_id/rusher null but rusher_player_id/
    # rusher_player_name populated (the real nflverse quirk verified before writing this
    # module) -- confirm grouping on the latter still works and doesn't silently drop rows.
    rows = _run_rows(50, 0.1, 1, 5, "00-3333333", "Q.Scrambler", 2025, "MIA")
    for r in rows:
        r["rusher_id"] = None
        r["rusher"] = None
    out = compute_team_season_rb_stats(pd.DataFrame(rows))
    assert len(out) == 1
    assert out.iloc[0]["Player Name"] == "Q.Scrambler"


def test_rb_stats_flags_rookie_season_as_first_qualifying_season():
    below_threshold_2024 = _run_rows(30, 0.0, 0, 3, "00-4444444", "R.Young", 2024, "MIA")
    qualifying_2025 = _run_rows(50, 0.0, 0, 3, "00-4444444", "R.Young", 2025, "MIA")
    pbp = pd.DataFrame(below_threshold_2024 + qualifying_2025)

    out = compute_team_season_rb_stats(pbp)

    assert list(out["Season"]) == [2025]  # 2024 excluded, not zero-filled
    assert out.iloc[0]["Is Rookie Season"]
