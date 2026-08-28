import pandas as pd

from nflverse_pull.current_roster import resolve_scored_population

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
