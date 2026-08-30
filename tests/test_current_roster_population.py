import pandas as pd

from nflverse_pull.current_roster import merge_with_historical_fallback, resolve_scored_population

CURRENT_STARTER_COLS = ["Team", "Position", "Player Name", "Player ID", "Depth Order", "Source"]


def _current_starters(rows):
    return pd.DataFrame(rows, columns=CURRENT_STARTER_COLS)


def _overrides(rows):
    return pd.DataFrame(rows, columns=["Team", "Manual Starter Override", "Manual Backup Override"])


def test_resolve_population_uses_pulled_data_when_no_override():
    current = _current_starters([
        ["Buffalo Bills", "QB", "J.Allen", "P1", 1, "depth_charts"],
        ["Buffalo Bills", "QB", "M.Trubisky", "P2", 2, "depth_charts"],
    ])
    overrides = _overrides([["Buffalo Bills", None, None]])

    out = resolve_scored_population(current, overrides, "QB")

    assert len(out) == 2
    starter = out[out["Role"] == "Starter"].iloc[0]
    assert starter["Player Name"] == "J.Allen"
    assert starter["Player ID"] == "P1"
    assert starter["Source"] == "depth_charts"


def test_resolve_population_manual_override_takes_precedence():
    current = _current_starters([
        ["Buffalo Bills", "QB", "J.Allen", "P1", 1, "depth_charts"],
        ["Buffalo Bills", "QB", "M.Trubisky", "P2", 2, "depth_charts"],
        # The override target is on SOME team's depth chart (a backup elsewhere getting
        # promoted per a beat-writer report the pull hasn't caught up to yet).
        ["Miami Dolphins", "QB", "T.Tagovailoa", "P3", 1, "depth_charts"],
    ])
    overrides = _overrides([["Buffalo Bills", None, "T.Tagovailoa"]])

    out = resolve_scored_population(current, overrides, "QB")

    backup = out[(out["Team"] == "Buffalo Bills") & (out["Role"] == "Backup")].iloc[0]
    assert backup["Player Name"] == "T.Tagovailoa"
    assert backup["Player ID"] == "P3"  # resolved via the other team's pulled row
    assert backup["Source"] == "override"
    # The starter slot is untouched -- override was blank for it.
    starter = out[(out["Team"] == "Buffalo Bills") & (out["Role"] == "Starter")].iloc[0]
    assert starter["Player Name"] == "J.Allen"


def test_resolve_population_unresolvable_override_gets_null_id_and_is_flagged():
    current = _current_starters([
        ["Buffalo Bills", "QB", "J.Allen", "P1", 1, "depth_charts"],
    ])
    overrides = _overrides([["Buffalo Bills", None, "Some Undrafted Rookie Nobody Pulled Yet"]])

    out = resolve_scored_population(current, overrides, "QB")

    backup = out[(out["Team"] == "Buffalo Bills") & (out["Role"] == "Backup")].iloc[0]
    assert backup["Player Name"] == "Some Undrafted Rookie Nobody Pulled Yet"
    assert pd.isna(backup["Player ID"])
    assert "unresolved" in backup["Source"]


def test_resolve_population_includes_a_true_zero_history_rookie():
    """
    A true rookie has NO historical pbp-derived stats -- but current_starters.csv (the
    depth-chart pull) always carries a real Player ID for him regardless, since a depth
    chart lists whoever's actually on the roster today, not just players with career stats.
    This function doesn't look at historical data at all, so such a player flows through
    exactly like any other current starter/backup -- proving he's a genuine scoring
    candidate rather than silently invisible, which the old historical-attempts-only
    population could never produce (it only ever considered players who already had a
    qualifying season). The downstream Section 3 formula chain (already built and
    hand-verified for QB Index) is what turns his presence here into a real Rookie-Baseline-
    driven row once this population is wired in.
    """
    current = _current_starters([
        ["Buffalo Bills", "RB", "R.Rookie", "P_NEW", 1, "depth_charts"],
    ])
    overrides = _overrides([])

    out = resolve_scored_population(current, overrides, "RB")

    assert len(out) == 1
    rookie = out.iloc[0]
    assert rookie["Player Name"] == "R.Rookie"
    assert rookie["Player ID"] == "P_NEW"
    assert rookie["Role"] == "Starter"


def test_resolve_population_labels_wr_roles_as_wr1_wr2_wr3():
    current = _current_starters([
        ["Buffalo Bills", "WR", "K.Coleman", "P1", 1, "depth_charts"],
        ["Buffalo Bills", "WR", "K.Shakir", "P2", 2, "depth_charts"],
        ["Buffalo Bills", "WR", "C.Samuel", "P3", 3, "depth_charts"],
    ])
    overrides = _overrides([])

    out = resolve_scored_population(current, overrides, "WR").set_index("Role")

    assert set(out.index) == {"WR1", "WR2", "WR3"}
    assert out.loc["WR1", "Player Name"] == "K.Coleman"
    assert out.loc["WR2", "Player Name"] == "K.Shakir"
    assert out.loc["WR3", "Player Name"] == "C.Samuel"
    # Sorted by role priority (WR1, WR2, WR3), not alphabetically.
    assert list(out.reset_index()["Role"]) == ["WR1", "WR2", "WR3"]


def test_resolve_population_labels_te_role_as_te1():
    current = _current_starters([
        ["Kansas City Chiefs", "TE", "T.Kelce", "P1", 1, "depth_charts"],
    ])
    out = resolve_scored_population(current, _overrides([]), "TE")

    assert len(out) == 1
    assert out.iloc[0]["Role"] == "TE1"


def test_resolve_population_labels_pk_role_as_k1():
    current = _current_starters([
        ["Kansas City Chiefs", "PK", "H.Butker", "P1", 1, "depth_charts"],
    ])
    out = resolve_scored_population(current, _overrides([]), "PK")

    assert len(out) == 1
    assert out.iloc[0]["Role"] == "K1"


def test_resolve_population_labels_each_ol_spot_by_its_own_name():
    for pos in ("LT", "LG", "C", "RG", "RT"):
        current = _current_starters([
            ["Kansas City Chiefs", pos, "Some Lineman", "P1", 1, "depth_charts"],
        ])
        out = resolve_scored_population(current, _overrides([]), pos)
        assert len(out) == 1
        assert out.iloc[0]["Role"] == pos


def test_resolve_population_override_generalizes_to_wr_roles():
    # claude_code_spec_consolidated_fixes.md Part 2: override columns aren't limited to
    # Starter/Backup -- "Manual WR2 Override" must take precedence on the WR2 slot.
    current = _current_starters([
        ["Buffalo Bills", "WR", "K.Coleman", "P1", 1, "depth_charts"],
        ["Buffalo Bills", "WR", "K.Shakir", "P2", 2, "depth_charts"],
        ["Buffalo Bills", "WR", "C.Samuel", "P3", 3, "depth_charts"],
        ["Miami Dolphins", "WR", "J.Waddle", "P4", 1, "depth_charts"],
    ])
    overrides = pd.DataFrame([
        {"Team": "Buffalo Bills", "Manual WR2 Override": "J.Waddle"},
    ])

    out = resolve_scored_population(current, overrides, "WR")
    buf = out[out["Team"] == "Buffalo Bills"].set_index("Role")

    assert buf.loc["WR2", "Player Name"] == "J.Waddle"
    assert buf.loc["WR2", "Player ID"] == "P4"
    assert buf.loc["WR2", "Source"] == "override"
    # WR1/WR3 untouched -- override was only supplied for WR2.
    assert buf.loc["WR1", "Player Name"] == "K.Coleman"
    assert buf.loc["WR3", "Player Name"] == "C.Samuel"


def test_resolve_population_override_generalizes_to_ol_roles():
    current = _current_starters([
        ["Kansas City Chiefs", "LT", "Some.Lineman", "P1", 1, "depth_charts"],
    ])
    overrides = pd.DataFrame([
        {"Team": "Kansas City Chiefs", "Manual LT Override": "Replacement.Lineman"},
    ])

    out = resolve_scored_population(current, overrides, "LT")

    row = out[(out["Team"] == "Kansas City Chiefs") & (out["Role"] == "LT")].iloc[0]
    assert row["Player Name"] == "Replacement.Lineman"
    assert pd.isna(row["Player ID"])  # not on any pulled depth chart -- unresolved
    assert "unresolved" in row["Source"]


def test_resolve_population_missing_override_column_is_a_no_op():
    # An overrides table built for a position with fewer roles (or no override table at
    # all, i.e. an empty DataFrame) must not error just because this position's role
    # columns aren't present.
    current = _current_starters([
        ["Buffalo Bills", "TE", "T.Kelce", "P1", 1, "depth_charts"],
    ])
    overrides = pd.DataFrame([{"Team": "Buffalo Bills"}])

    out = resolve_scored_population(current, overrides, "TE")

    assert len(out) == 1
    assert out.iloc[0]["Player Name"] == "T.Kelce"


def test_attach_experience_joins_real_years_exp_by_player_id():
    from nflverse_pull.current_roster import attach_experience

    population = pd.DataFrame([
        {"Team": "Buffalo Bills", "Role": "LT", "Player Name": "D.Dawkins",
         "Player ID": "P1", "Source": "depth_charts"},
        {"Team": "Buffalo Bills", "Role": "C", "Player Name": "R.Rookie",
         "Player ID": "P2", "Source": "depth_charts"},
        # P3 has no roster row at all -- must get None, not a guessed value.
        {"Team": "Buffalo Bills", "Role": "RT", "Player Name": "Mystery Player",
         "Player ID": "P3", "Source": "depth_charts"},
    ])
    rosters = pd.DataFrame([
        {"player_id": "P1", "years_exp": 9},
        {"player_id": "P2", "years_exp": 0},
    ])

    out = attach_experience(population, rosters).set_index("Player ID")

    assert out.loc["P1", "Years of NFL Experience"] == 9
    assert out.loc["P1", "Is Rookie"] is False
    assert out.loc["P2", "Years of NFL Experience"] == 0
    assert out.loc["P2", "Is Rookie"] is True
    assert pd.isna(out.loc["P3", "Years of NFL Experience"])
    assert out.loc["P3", "Is Rookie"] is None


def test_attach_real_rookie_season_uses_real_entry_year_not_pull_window():
    from nflverse_pull.current_roster import attach_real_rookie_season

    # A real veteran (entry_year=2017) whose first PULLED season happens to be 2023 -- the
    # OLD proxy (first season observed in the window) would wrongly call this a rookie
    # season; the real entry_year fix must not.
    season_stats = pd.DataFrame([
        {"Player ID": "MAHOMES", "Season": 2023, "Is Rookie Season": True},  # old proxy's bug
        {"Player ID": "MAHOMES", "Season": 2024, "Is Rookie Season": False},
        # A real rookie (entry_year=2024): correctly True only in his real entry season.
        {"Player ID": "ROOKIE", "Season": 2024, "Is Rookie Season": True},
        {"Player ID": "ROOKIE", "Season": 2025, "Is Rookie Season": True},  # old proxy's bug
        # No roster match at all -- must default to False, not carry over the old value.
        {"Player ID": "MYSTERY", "Season": 2024, "Is Rookie Season": True},
    ])
    rosters = pd.DataFrame([
        {"player_id": "MAHOMES", "season": 2023, "entry_year": 2017},
        {"player_id": "MAHOMES", "season": 2024, "entry_year": 2017},
        {"player_id": "ROOKIE", "season": 2024, "entry_year": 2024},
        {"player_id": "ROOKIE", "season": 2025, "entry_year": 2024},
    ])

    out = attach_real_rookie_season(season_stats, rosters)

    result = dict(zip(zip(out["Player ID"], out["Season"]), out["Is Rookie Season"]))
    assert result[("MAHOMES", 2023)] is False
    assert result[("MAHOMES", 2024)] is False
    assert result[("ROOKIE", 2024)] is True
    assert result[("ROOKIE", 2025)] is False
    assert result[("MYSTERY", 2024)] is False


def _historical(rows):
    return pd.DataFrame(rows, columns=["Team", "Role", "Player Name", "Player ID"])


def test_merge_fallback_leaves_a_fully_populated_team_untouched():
    current = pd.DataFrame([
        {"Team": "Buffalo Bills", "Role": "Starter", "Player Name": "J.Allen",
         "Player ID": "P1", "Source": "depth_charts"},
        {"Team": "Buffalo Bills", "Role": "Backup", "Player Name": "M.Trubisky",
         "Player ID": "P2", "Source": "depth_charts"},
    ])
    historical = _historical([
        ["Buffalo Bills", "Starter", "J.Allen", "P1"],
        ["Buffalo Bills", "Backup", "M.Trubisky", "P2"],
    ])

    out = merge_with_historical_fallback(current, historical)

    assert len(out) == 2
    assert set(out["Source"]) == {"depth_charts"}  # nothing fell back


def test_merge_fallback_fills_a_team_missing_from_current_population():
    # Miami has no current-roster row at all (e.g. the depth-chart pull had a gap) -- the
    # historical proxy should fill BOTH of its roles, tagged so it's visible that it did.
    current = pd.DataFrame([
        {"Team": "Buffalo Bills", "Role": "Starter", "Player Name": "J.Allen",
         "Player ID": "P1", "Source": "depth_charts"},
    ])
    historical = _historical([
        ["Buffalo Bills", "Starter", "J.Allen", "P1"],
        ["Miami Dolphins", "Starter", "T.Tagovailoa", "P3"],
        ["Miami Dolphins", "Backup", "T.Huntley", "P4"],
    ])

    out = merge_with_historical_fallback(current, historical)

    assert len(out) == 3
    miami = out[out["Team"] == "Miami Dolphins"].set_index("Role")
    assert miami.loc["Starter", "Player Name"] == "T.Tagovailoa"
    assert miami.loc["Backup", "Player Name"] == "T.Huntley"
    assert "historical-proxy fallback" in miami.loc["Starter", "Source"]
    # Buffalo's real current-roster row is untouched, not replaced by the historical proxy.
    buf_starter = out[(out["Team"] == "Buffalo Bills") & (out["Role"] == "Starter")].iloc[0]
    assert buf_starter["Source"] == "depth_charts"


def test_merge_fallback_fills_only_the_missing_role_not_the_present_one():
    # Buffalo has a current-roster Starter but no Backup slot -- only Backup should fall
    # back; the real current Starter must never be overwritten by the historical proxy.
    current = pd.DataFrame([
        {"Team": "Buffalo Bills", "Role": "Starter", "Player Name": "New.Starter",
         "Player ID": "P_NEW", "Source": "depth_charts"},
    ])
    historical = _historical([
        ["Buffalo Bills", "Starter", "Old.Starter", "P_OLD"],
        ["Buffalo Bills", "Backup", "Old.Backup", "P_OLD2"],
    ])

    out = merge_with_historical_fallback(current, historical).set_index("Role")

    assert out.loc["Starter", "Player Name"] == "New.Starter"  # NOT overwritten
    assert out.loc["Backup", "Player Name"] == "Old.Backup"  # filled via fallback
    assert "historical-proxy fallback" in out.loc["Backup", "Source"]
