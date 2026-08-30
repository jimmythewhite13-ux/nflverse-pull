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
