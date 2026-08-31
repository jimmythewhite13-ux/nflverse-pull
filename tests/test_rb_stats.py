import pandas as pd
import pytest

from nflverse_pull.rb_stats import (
    MIN_QUALIFYING_CARRIES,
    SEASON_STATS_COLUMNS,
    compute_carry_share,
    compute_player_season_red_zone_carry_share,
    compute_player_season_ryoe,
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


def _population(rows):
    return pd.DataFrame(rows, columns=["Team", "Role", "Player Name", "Player ID"])


def _season_stats_for_carries(rows):
    # Minimal season_stats stand-in: just the columns compute_carry_share actually reads.
    return pd.DataFrame(rows, columns=["Player ID", "Season", "Carries"])


def test_carry_share_flags_a_clear_bell_cow():
    population = _population([
        ["Buffalo Bills", "Starter", "R.Lead", "P1"],
        ["Buffalo Bills", "Backup", "R.Change", "P2"],
    ])
    season_stats = _season_stats_for_carries([
        ["P1", 2025, 210], ["P2", 2025, 90],  # 70/30 split
    ])

    out = compute_carry_share(population, season_stats).set_index("Team")
    assert out.loc["Buffalo Bills", "Carry Share (Y-1)"] == pytest.approx(0.7)


def test_carry_share_flags_a_genuine_committee():
    population = _population([
        ["Miami Dolphins", "Starter", "R.One", "P3"],
        ["Miami Dolphins", "Backup", "R.Two", "P4"],
    ])
    season_stats = _season_stats_for_carries([
        ["P3", 2025, 110], ["P4", 2025, 90],  # near 55/45
    ])

    out = compute_carry_share(population, season_stats).set_index("Team")
    assert out.loc["Miami Dolphins", "Carry Share (Y-1)"] == pytest.approx(110 / 200)


def test_carry_share_handles_a_true_zero_history_rookie_backup():
    # The backup is a true rookie with no Section 1 rows at all -- must not error, and
    # correctly gives the incumbent starter a 1.0 share (all of the recent carries).
    population = _population([
        ["Buffalo Bills", "Starter", "R.Incumbent", "P1"],
        ["Buffalo Bills", "Backup", "R.Rookie", "P_NEW"],
    ])
    season_stats = _season_stats_for_carries([["P1", 2025, 150]])  # P_NEW has no rows

    out = compute_carry_share(population, season_stats).set_index("Team")
    assert out.loc["Buffalo Bills", "Carry Share (Y-1)"] == pytest.approx(1.0)
    assert out.loc["Buffalo Bills", "Backup Carries (Y-1)"] == 0


def test_carry_share_skips_team_missing_a_role():
    population = _population([["Buffalo Bills", "Starter", "R.Solo", "P1"]])  # no backup
    out = compute_carry_share(population, _season_stats_for_carries([]))
    assert len(out) == 0


def test_historical_rb_roles_ranks_by_carries_within_team_season():
    from nflverse_pull.rb_stats import compute_historical_rb_roles

    team, season = "Buffalo Bills", 2025

    def _row(name, player_id, carries):
        return {"Team": team, "Season": season, "Player Name": name,
                "Player ID": player_id, "Carries": carries}

    season_stats = pd.DataFrame([
        _row("R.Lead", "P1", 200),
        _row("R.Change", "P2", 80),
        _row("R.Third", "P3", 55),
    ])
    out = compute_historical_rb_roles(season_stats).set_index("Player ID")
    assert out.loc["P1", "Role"] == "Starter"
    assert out.loc["P2", "Role"] == "Backup"
    assert out.loc["P3", "Role"] == "Other"


def _ngs_row(player_id, season, team_abbr, week, ryoe_per_att):
    return {
        "player_gsis_id": player_id, "season": season, "team_abbr": team_abbr,
        "week": week, "rush_yards_over_expected_per_att": ryoe_per_att,
    }


def test_ryoe_uses_real_season_aggregate_rows_only():
    # week=0 is the real season aggregate; weekly rows (week=1, 2...) must be ignored, not
    # summed or averaged manually -- NGS already computes the season total itself.
    rows = [
        _ngs_row("P1", 2025, "BUF", 0, 0.45),
        _ngs_row("P1", 2025, "BUF", 1, 0.10),
        _ngs_row("P1", 2025, "BUF", 2, 0.80),
    ]
    out = compute_player_season_ryoe(pd.DataFrame(rows)).set_index("Player ID")
    assert len(out) == 1
    assert out.loc["P1", "RYOE/Att"] == pytest.approx(0.45)
    assert out.loc["P1", "Team"] == "Buffalo Bills"
    assert out.loc["P1", "Season"] == 2025


def test_ryoe_remaps_ngs_lar_to_la():
    # Verified live before writing this: NGS uses "LAR" for the Rams consistently across
    # 2023-2025 (a different quirk from PFR's own inconsistent-across-years LAR/LVR).
    rows = [_ngs_row("P1", 2025, "LAR", 0, 0.5)]
    out = compute_player_season_ryoe(pd.DataFrame(rows))
    assert out.iloc[0]["Team"] == "Los Angeles Rams"


def test_ryoe_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([_ngs_row("P1", 2025, "ZZZ", 0, 0.5)])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_player_season_ryoe(df)


def test_ryoe_skips_rows_with_no_real_player_id():
    # A row with no player_gsis_id (a data gap) must not produce a phantom None-keyed row.
    rows = [_ngs_row(None, 2025, "BUF", 0, 0.5), _ngs_row("P1", 2025, "BUF", 0, 0.3)]
    out = compute_player_season_ryoe(pd.DataFrame(rows))
    assert len(out) == 1
    assert out.iloc[0]["Player ID"] == "P1"


def _rz_run_row(posteam, season, yardline_100, rusher_id):
    return {
        "season_type": "REG", "play_type": "run", "posteam": posteam, "season": season,
        "yardline_100": yardline_100, "rusher_player_id": rusher_id,
    }


def test_red_zone_carry_share_computes_share_of_team_rz_carries():
    # BUF: 3 real red-zone carries total -- P1 gets 2, P2 gets 1.
    rows = [
        _rz_run_row("BUF", 2025, 15, "P1"),
        _rz_run_row("BUF", 2025, 10, "P1"),
        _rz_run_row("BUF", 2025, 5, "P2"),
        _rz_run_row("BUF", 2025, 45, "P1"),  # outside red zone -- excluded
    ]
    out = compute_player_season_red_zone_carry_share(pd.DataFrame(rows)).set_index("Player ID")
    assert out.loc["P1", "Red-Zone Carry Share"] == pytest.approx(2 / 3)
    assert out.loc["P2", "Red-Zone Carry Share"] == pytest.approx(1 / 3)
    assert out.loc["P1", "Team"] == "Buffalo Bills"


def test_red_zone_carry_share_excludes_non_run_plays_and_missing_rusher_id():
    rows = [
        _rz_run_row("BUF", 2025, 10, "P1"),
        {**_rz_run_row("BUF", 2025, 8, "P1"), "play_type": "pass"},
        _rz_run_row("BUF", 2025, 12, None),
    ]
    out = compute_player_season_red_zone_carry_share(pd.DataFrame(rows)).set_index("Player ID")
    assert list(out.index) == ["P1"]
    assert out.loc["P1", "Red-Zone Carry Share"] == pytest.approx(1.0)


def test_red_zone_carry_share_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([_rz_run_row("ZZZ", 2025, 10, "P1")])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_player_season_red_zone_carry_share(df)
