import pandas as pd
import pytest

from nflverse_pull.efficiency import (
    EXPLOSIVE_PASS_YARDS,
    EXPLOSIVE_RUN_YARDS,
    MATCHUP_SEASON_OUTPUT_COLUMNS,
    SEASON_OUTPUT_COLUMNS,
    compute_league_stats,
    compute_raw_efficiency,
    compute_team_season_efficiency,
    compute_team_season_matchup_metrics,
    compute_weighted_efficiency,
)


def _fake_pbp():
    # BUF offense vs MIA defense: a run, a completed pass, an incomplete pass, and a sack.
    # MIA offense vs BUF defense: a run and a completed pass.
    # Plus one postseason play and one non-scrimmage play (kickoff) that must both be
    # excluded from every metric. All plays are season 2025 -- compute_raw_efficiency()
    # ignores the season column (it pools), compute_team_season_efficiency() uses it.
    rows = [
        {"season_type": "REG", "play_type": "run", "posteam": "BUF", "defteam": "MIA",
         "season": 2025, "epa": 1.0, "success": 1, "pass_attempt": 0, "sack": 0,
         "passing_yards": None, "yards_gained": 5, "pass_oe": -20},
        {"season_type": "REG", "play_type": "pass", "posteam": "BUF", "defteam": "MIA",
         "season": 2025, "epa": -1.0, "success": 0, "pass_attempt": 1, "sack": 0,
         "passing_yards": 0, "yards_gained": 0, "pass_oe": 10},
        {"season_type": "REG", "play_type": "pass", "posteam": "BUF", "defteam": "MIA",
         "season": 2025, "epa": 2.0, "success": 1, "pass_attempt": 1, "sack": 0,
         "passing_yards": 20, "yards_gained": 20, "pass_oe": 30},
        {"season_type": "REG", "play_type": "pass", "posteam": "BUF", "defteam": "MIA",
         "season": 2025, "epa": -2.0, "success": 0, "pass_attempt": 0, "sack": 1,
         "passing_yards": None, "yards_gained": -7, "pass_oe": 40},
        {"season_type": "REG", "play_type": "run", "posteam": "MIA", "defteam": "BUF",
         "season": 2025, "epa": -0.5, "success": 1, "pass_attempt": 0, "sack": 0,
         "passing_yards": None, "yards_gained": 2, "pass_oe": -10},
        {"season_type": "REG", "play_type": "pass", "posteam": "MIA", "defteam": "BUF",
         "season": 2025, "epa": 1.5, "success": 1, "pass_attempt": 1, "sack": 0,
         "passing_yards": 8, "yards_gained": 8, "pass_oe": 5},
        # Must be excluded -- postseason.
        {"season_type": "POST", "play_type": "pass", "posteam": "BUF", "defteam": "MIA",
         "season": 2025, "epa": 999, "success": 1, "pass_attempt": 1, "sack": 0,
         "passing_yards": 999, "yards_gained": 999, "pass_oe": 999},
        # Must be excluded -- not a pass or run play.
        {"season_type": "REG", "play_type": "kickoff", "posteam": "BUF", "defteam": "MIA",
         "season": 2025, "epa": -999, "success": 0, "pass_attempt": 0, "sack": 0,
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


def test_team_season_efficiency_computes_one_row_per_team_per_season():
    # Add a single 2024 BUF-offense play on top of the fixture's all-2025 plays, to confirm
    # seasons are kept separate rather than pooled together.
    row_2024 = pd.DataFrame([
        {"season_type": "REG", "play_type": "run", "posteam": "BUF", "defteam": "MIA",
         "season": 2024, "epa": 3.0, "success": 1, "pass_attempt": 0, "sack": 0,
         "passing_yards": None, "yards_gained": 4, "pass_oe": -5},
    ])
    pbp = pd.concat([_fake_pbp(), row_2024], ignore_index=True)

    out = compute_team_season_efficiency(pbp)

    assert list(out.columns) == SEASON_OUTPUT_COLUMNS

    buf_2025 = out[(out["Team"] == "Buffalo Bills") & (out["Season"] == 2025)].iloc[0]
    buf_2024 = out[(out["Team"] == "Buffalo Bills") & (out["Season"] == 2024)].iloc[0]

    # 2025 matches the pooled compute_raw_efficiency() result for the same plays.
    assert buf_2025["EPA/Play (Off)"] == pytest.approx(0.0)
    assert buf_2025["Success Rate (Off)"] == pytest.approx(0.5)
    assert buf_2025["NY/A (Off)"] == pytest.approx(13 / 3)
    assert buf_2025["PROE (Off)"] == pytest.approx(0.15)
    # 2024 is the single extra play, kept as its own row.
    assert buf_2024["EPA/Play (Off)"] == pytest.approx(3.0)
    assert buf_2024["Success Rate (Off)"] == pytest.approx(1.0)


def test_team_season_efficiency_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([
        {"season_type": "REG", "play_type": "pass", "posteam": "ZZZ", "defteam": "MIA",
         "season": 2025, "epa": 1.0, "success": 1, "pass_attempt": 1, "sack": 0,
         "passing_yards": 10, "yards_gained": 10, "pass_oe": 5},
    ])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_efficiency(df)


def _matchup_row(posteam, defteam, season, play_type, yards_gained, pass_attempt=0, sack=0,
                  complete_pass=None, epa=0.0, success=0):
    return {
        "season_type": "REG", "play_type": play_type, "posteam": posteam, "defteam": defteam,
        "season": season, "yards_gained": yards_gained, "pass_attempt": pass_attempt,
        "sack": sack, "complete_pass": complete_pass, "epa": epa, "success": success,
    }


def _fake_matchup_pbp():
    """
    BUF offense vs MIA defense, 2025:
      - 4 real pass attempts (sack=0): 2 completions (10 yd/epa 1.0/success 1, 20 yd/epa
        2.0/success 1 -- the 20-yd one is explosive, EXPLOSIVE_PASS_YARDS=15), 2
        incompletions (0 yd/epa -1.0/success 0 each).
        Completion % Allowed (MIA) = 2/4 = 0.5.
        Explosive Pass Rate (Off, BUF) -- denominator is ALL play_type=="pass" rows,
        which includes the 1 sack below (5 total) = 1/5 = 0.2.
        EPA/Dropback Allowed (MIA) = mean(1.0, 2.0, -1.0, -1.0, sack's -3.0) = -0.4.
        Pass Success Rate Allowed (MIA) = mean(1, 1, 0, 0, sack's 0) = 2/5 = 0.4.
      - 1 sack (play_type=="pass", pass_attempt=0, sack=1, -7 yards, epa=-3.0, success=0) --
        excluded from Completion % (not a real attempt), included in Explosive Pass Rate's
        AND EPA/Dropback Allowed's denominator (a real dropback outcome).
      - 3 runs: 12 yd/epa 1.5/success 1 (explosive, EXPLOSIVE_RUN_YARDS=10), 3 yd/epa
        0.1/success 0 (neither), -1 yd/epa -1.2/success 0 (stuffed).
        Explosive Run Rate (Off, BUF) = 1/3. Stuff Rate (Off, BUF) = 1/3.
        EPA/Rush Allowed (MIA) = mean(1.5, 0.1, -1.2) = 0.1333...
        Run Success Rate Allowed (MIA) = mean(1, 0, 0) = 1/3.
        Yards/Carry Allowed (MIA) = mean(12, 3, -1) = 14/3.
    """
    rows = [
        _matchup_row("BUF", "MIA", 2025, "pass", 10, pass_attempt=1, complete_pass=1,
                     epa=1.0, success=1),
        _matchup_row("BUF", "MIA", 2025, "pass", 20, pass_attempt=1, complete_pass=1,
                     epa=2.0, success=1),
        _matchup_row("BUF", "MIA", 2025, "pass", 0, pass_attempt=1, complete_pass=0,
                     epa=-1.0, success=0),
        _matchup_row("BUF", "MIA", 2025, "pass", 0, pass_attempt=1, complete_pass=0,
                     epa=-1.0, success=0),
        _matchup_row("BUF", "MIA", 2025, "pass", -7, pass_attempt=0, sack=1,
                     epa=-3.0, success=0),
        _matchup_row("BUF", "MIA", 2025, "run", 12, epa=1.5, success=1),
        _matchup_row("BUF", "MIA", 2025, "run", 3, epa=0.1, success=0),
        _matchup_row("BUF", "MIA", 2025, "run", -1, epa=-1.2, success=0),
    ]
    return pd.DataFrame(rows)


def test_matchup_metrics_epa_dropback_and_pass_success_allowed_include_sacks():
    out = compute_team_season_matchup_metrics(_fake_matchup_pbp())
    mia = out[out["Team"] == "Miami Dolphins"].iloc[0]
    assert mia["EPA/Dropback Allowed (Def)"] == pytest.approx((1.0 + 2.0 - 1.0 - 1.0 - 3.0) / 5)
    assert mia["Pass Success Rate Allowed (Def)"] == pytest.approx(2 / 5)


def test_matchup_metrics_epa_rush_success_and_ypc_allowed():
    out = compute_team_season_matchup_metrics(_fake_matchup_pbp())
    mia = out[out["Team"] == "Miami Dolphins"].iloc[0]
    assert mia["EPA/Rush Allowed (Def)"] == pytest.approx((1.5 + 0.1 - 1.2) / 3)
    assert mia["Run Success Rate Allowed (Def)"] == pytest.approx(1 / 3)
    assert mia["Yards/Carry Allowed (Def)"] == pytest.approx((12 + 3 - 1) / 3)


def test_matchup_metrics_computes_completion_pct_allowed_excluding_sacks():
    out = compute_team_season_matchup_metrics(_fake_matchup_pbp())
    assert list(out.columns) == MATCHUP_SEASON_OUTPUT_COLUMNS
    mia = out[out["Team"] == "Miami Dolphins"].iloc[0]
    assert mia["Completion % Allowed (Def)"] == pytest.approx(0.5)


def test_matchup_metrics_explosive_pass_rate_denominator_includes_sacks():
    # Denominator is play_type=="pass" (5 rows: 4 attempts + 1 sack), not just real attempts
    # -- a sack dilutes the rate the same way a 0-yard incompletion does.
    out = compute_team_season_matchup_metrics(_fake_matchup_pbp())
    buf = out[out["Team"] == "Buffalo Bills"].iloc[0]
    assert buf["Explosive Pass Rate (Off)"] == pytest.approx(1 / 5)
    mia_def = out[out["Team"] == "Miami Dolphins"].iloc[0]
    assert mia_def["Explosive Pass Rate Allowed (Def)"] == pytest.approx(1 / 5)


def test_matchup_metrics_explosive_run_rate_and_stuff_rate():
    out = compute_team_season_matchup_metrics(_fake_matchup_pbp())
    buf = out[out["Team"] == "Buffalo Bills"].iloc[0]
    assert buf["Explosive Run Rate (Off)"] == pytest.approx(1 / 3)
    assert buf["Stuff Rate (Off)"] == pytest.approx(1 / 3)
    mia = out[out["Team"] == "Miami Dolphins"].iloc[0]
    assert mia["Explosive Run Rate Allowed (Def)"] == pytest.approx(1 / 3)
    assert mia["Stuff Rate Allowed (Def)"] == pytest.approx(1 / 3)


def test_matchup_metrics_thresholds_are_named_constants():
    assert EXPLOSIVE_PASS_YARDS == 15
    assert EXPLOSIVE_RUN_YARDS == 10


def test_matchup_metrics_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([_matchup_row("ZZZ", "MIA", 2025, "run", 5)])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_matchup_metrics(df)
