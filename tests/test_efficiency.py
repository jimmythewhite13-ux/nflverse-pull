import pandas as pd
import pytest

from nflverse_pull.efficiency import (
    compute_league_stats,
    compute_raw_efficiency,
    compute_weighted_efficiency,
)


def _fake_pbp():
    # BUF offense vs MIA defense: a run, a completed pass, an incomplete pass, and a sack.
    # MIA offense vs BUF defense: a run and a completed pass.
    # Plus one postseason play and one non-scrimmage play (kickoff) that must both be
    # excluded from every metric.
    rows = [
        {"season_type": "REG", "play_type": "run", "posteam": "BUF", "defteam": "MIA",
         "epa": 1.0, "success": 1, "pass_attempt": 0, "sack": 0,
         "passing_yards": None, "yards_gained": 5, "pass_oe": -20},
        {"season_type": "REG", "play_type": "pass", "posteam": "BUF", "defteam": "MIA",
         "epa": -1.0, "success": 0, "pass_attempt": 1, "sack": 0,
         "passing_yards": 0, "yards_gained": 0, "pass_oe": 10},
        {"season_type": "REG", "play_type": "pass", "posteam": "BUF", "defteam": "MIA",
         "epa": 2.0, "success": 1, "pass_attempt": 1, "sack": 0,
         "passing_yards": 20, "yards_gained": 20, "pass_oe": 30},
        {"season_type": "REG", "play_type": "pass", "posteam": "BUF", "defteam": "MIA",
         "epa": -2.0, "success": 0, "pass_attempt": 0, "sack": 1,
         "passing_yards": None, "yards_gained": -7, "pass_oe": 40},
        {"season_type": "REG", "play_type": "run", "posteam": "MIA", "defteam": "BUF",
         "epa": -0.5, "success": 1, "pass_attempt": 0, "sack": 0,
         "passing_yards": None, "yards_gained": 2, "pass_oe": -10},
        {"season_type": "REG", "play_type": "pass", "posteam": "MIA", "defteam": "BUF",
         "epa": 1.5, "success": 1, "pass_attempt": 1, "sack": 0,
         "passing_yards": 8, "yards_gained": 8, "pass_oe": 5},
        # Must be excluded -- postseason.
        {"season_type": "POST", "play_type": "pass", "posteam": "BUF", "defteam": "MIA",
         "epa": 999, "success": 1, "pass_attempt": 1, "sack": 0,
         "passing_yards": 999, "yards_gained": 999, "pass_oe": 999},
        # Must be excluded -- not a pass or run play.
        {"season_type": "REG", "play_type": "kickoff", "posteam": "BUF", "defteam": "MIA",
         "epa": -999, "success": 0, "pass_attempt": 0, "sack": 0,
         "passing_yards": None, "yards_gained": 0, "pass_oe": None},
    ]
    return pd.DataFrame(rows)


def test_raw_efficiency_computes_expected_metrics():
    raw = compute_raw_efficiency(_fake_pbp())

    buf = raw[raw["Team"] == "Buffalo Bills"].iloc[0]
    mia = raw[raw["Team"] == "Miami Dolphins"].iloc[0]

    # BUF offense: epa (1.0, -1.0, 2.0, -2.0) -> mean 0.0; success (1,0,1,0) -> mean 0.5
    assert buf["epa_off"] == pytest.approx(0.0)
    assert buf["success_off"] == pytest.approx(0.5)
    # NY/A: (0 + 20 pass yards - 7 sack yards) / (2 attempts + 1 sack) = 13/3
    assert buf["nya_off"] == pytest.approx(13 / 3)
    # PROE: mean(-20, 10, 30, 40) / 100 = 15/100
    assert buf["proe"] == pytest.approx(0.15)

    # MIA defense allowed mirrors the same four BUF plays (only opponent in the fixture).
    assert mia["epa_def"] == pytest.approx(0.0)
    assert mia["success_def"] == pytest.approx(0.5)
    assert mia["nya_def"] == pytest.approx(13 / 3)

    # MIA offense: epa (-0.5, 1.5) -> mean 0.5; success (1,1) -> mean 1.0;
    # one 8-yard completion, no sacks -> NY/A 8.0
    assert mia["epa_off"] == pytest.approx(0.5)
    assert mia["success_off"] == pytest.approx(1.0)
    assert mia["nya_off"] == pytest.approx(8.0)
    assert buf["epa_def"] == pytest.approx(0.5)
    assert buf["success_def"] == pytest.approx(1.0)
    assert buf["nya_def"] == pytest.approx(8.0)


def test_raw_efficiency_output_shape_and_columns():
    raw = compute_raw_efficiency(_fake_pbp())
    assert list(raw.columns) == [
        "Team", "epa_off", "epa_def", "success_off", "success_def", "nya_off", "nya_def", "proe",
    ]
    assert len(raw) == 2  # only BUF and MIA appear in the fixture


def test_raw_efficiency_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([
        {"season_type": "REG", "play_type": "pass", "posteam": "ZZZ", "defteam": "MIA",
         "epa": 1.0, "success": 1, "pass_attempt": 1, "sack": 0,
         "passing_yards": 10, "yards_gained": 10, "pass_oe": 5},
    ])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_raw_efficiency(df)


def test_league_stats_match_manual_mean_and_population_std():
    raw = compute_raw_efficiency(_fake_pbp())
    stats = compute_league_stats(raw)

    epa_off_values = raw["epa_off"].tolist()  # [0.0, 0.5] for this fixture
    assert stats.loc["epa_off", "mean"] == pytest.approx(sum(epa_off_values) / 2)
    assert stats.loc["epa_off", "std"] == pytest.approx(pd.Series(epa_off_values).std(ddof=0))


def test_weighted_efficiency_league_average_is_zero():
    # A Z-scored, weighted-sum-of-Z-scores column always averages to 0 across the league
    # it was scored against -- true for any number of teams, not just this 2-team fixture.
    raw = compute_raw_efficiency(_fake_pbp())
    weighted = compute_weighted_efficiency(raw)
    assert weighted["Weighted Efficiency Adjustment"].mean() == pytest.approx(0.0, abs=1e-9)


def test_weighted_efficiency_carries_proe_unweighted():
    raw = compute_raw_efficiency(_fake_pbp())
    weighted = compute_weighted_efficiency(raw)
    buf = weighted[weighted["Team"] == "Buffalo Bills"].iloc[0]
    assert buf["PROE"] == pytest.approx(0.15)
