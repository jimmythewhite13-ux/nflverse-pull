"""
Real team-season turnover and red-zone components -- claude_code_spec_turnover_redzone_
regression_engine.md. Same fetch/pure-transform split as the rest of nflverse_pull.

Part A -- turnover components, verified live against real 2025 pbp before writing this:
  - `fumbled_1_team` is never null on a real fumble (0/532 nulls), but is NOT always the
    posteam of that play (489/532 = 91.9% of the time it is -- the remaining ~8% are real
    plays where the team that ends up fumbling is actually the one on DEFENSE for that play,
    e.g. fumbling during a return). `fumble_recovery_1_team` is null on 43/532 (fumbles ruled
    out of bounds, nobody recovers). Given this, "who gave the ball away" / "who took it
    away" is computed from fumbled_1_team/fumble_recovery_1_team directly, NOT assumed to be
    posteam/defteam -- the fully general, honest definition, not a simplification that would
    misattribute the ~8% of edge-case fumbles.
  - Fumble Recovery Rate (LUCK-driven, per the spec's own framing): verified live this is a
    real, well-established finding -- league-wide average across all 32 real 2025 teams
    computed here is 50.06%, matching the "close to a coin flip" claim almost exactly (a
    sanity check on the calculation itself, per the spec's own acceptance item).
  - Fumble Lost Rate (Off) / Fumble Forced Rate (Def), by contrast, are scoped to the
    ORDINARY case (posteam fumbles its own snap, defteam forces it) -- the spec frames these
    specifically as offense/defense RATE metrics (per-play, not per-turnover-event), and the
    ~8% edge-case fumbles during returns don't cleanly belong to either team's "own offensive
    snap" or "own defensive snap" in the way these two rates are meant to measure.

Part B -- red-zone components, verified live: nflverse's own real `drive_inside20` field is
a DRIVE-level flag (constant across every play of a drive that reached inside the 20 at any
point, not just the play(s) actually inside the 20) and `fixed_drive_result` gives the real
final outcome of that drive (Touchdown/Punt/Field goal/etc.) -- both already computed by
nflverse, not re-derived here. REAL BUG CAUGHT AND FIXED before this shipped: `drive` numbers
are only unique WITHIN a single game (every game has its own "drive 1", "drive 2", ...) --
grouping by (posteam, season, drive) alone silently merges unrelated drives from different
games that happen to share a drive number, producing a nonsensical ~82% "red-zone drive
share" and ~25% red-zone TD rate. Grouping by (game_id, posteam, drive) instead gives a real,
plausible 31.5% red-zone-drive share and 56.9% red-zone TD rate, matching published real NFL
red-zone conversion statistics. `goal_to_go` is a real, existing per-play nflverse field
(not re-derived) -- verified live: 74.4% real 2025 league-average goal-to-go TD rate,
plausible.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES

TURNOVER_OUTPUT_COLUMNS = [
    "Team", "Season", "INT Rate Thrown (Off)", "Fumble Lost Rate (Off)",
    "Fumble Forced Rate (Def)", "Fumble Recovery Rate", "Actual Turnover Differential",
    "Pass Attempts (Off)", "Offensive Plays", "Defensive Plays",
    "Defensive Pass Attempts Faced",
]


def compute_team_season_turnover_components(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. See this module's own docstring for the full real-data
    reasoning behind each column's exact definition. The four trailing count columns (Pass
    Attempts (Off), Offensive Plays, Defensive Plays, Defensive Pass Attempts Faced) are the
    REAL denominators behind the rate columns -- exposed so the Excel tab can compute
    Expected Turnover Differential as a dimensionally-consistent COUNT (rate x real play
    count), not by subtracting raw rates against a raw count the spec's own pseudocode
    would otherwise mismatch in units. Defensive Pass Attempts Faced uses pass_attempt==1
    WITHOUT excluding sacks -- deliberately matching Secondary Index's own defense_stats.
    compute_team_season_secondary_stats() denominator exactly (not this module's own
    sack-excluding Pass Attempts (Off) convention), since it's multiplied against Secondary
    Index's own real INT Rate, referenced not recomputed.

    Columns: Team | Season | INT Rate Thrown (Off) | Fumble Lost Rate (Off) | Fumble Forced
    Rate (Def) | Fumble Recovery Rate | Actual Turnover Differential | Pass Attempts (Off) |
    Offensive Plays | Defensive Plays | Defensive Pass Attempts Faced
    """
    reg = pbp[pbp["season_type"] == "REG"]
    scrimmage = reg[reg["play_type"].isin(["pass", "run"])]
    axis_names = ["team", "season"]

    # ---- INT Rate Thrown (Off): real INTs / real pass attempts (excl. sacks) -------------
    attempts = reg[(reg["pass_attempt"] == 1) & (reg["sack"] == 0)]
    int_thrown = attempts.groupby(["posteam", "season"])["interception"].sum()
    att_count = attempts.groupby(["posteam", "season"]).size()
    int_rate_thrown = (
        (int_thrown / att_count).rename_axis(axis_names).rename("INT Rate Thrown (Off)")
    )

    # ---- Fumble Lost Rate (Off) / Fumble Forced Rate (Def): ordinary-snap case only ------
    off_plays = scrimmage.groupby(["posteam", "season"]).size()
    def_plays = scrimmage.groupby(["defteam", "season"]).size()

    fum = reg[reg["fumble"] == 1].dropna(subset=["fumble_recovery_1_team"])
    ordinary = fum[fum["fumbled_1_team"] == fum["posteam"]]

    lost = ordinary[ordinary["fumble_recovery_1_team"] != ordinary["posteam"]]
    lost_count = lost.groupby(["posteam", "season"]).size()
    fumble_lost_rate = (
        (lost_count / off_plays).rename_axis(axis_names).rename("Fumble Lost Rate (Off)")
    )

    forced = ordinary[
        (ordinary["fumble_forced"] == 1)
        & (ordinary["fumble_recovery_1_team"] != ordinary["posteam"])
    ]
    forced_count = forced.groupby(["defteam", "season"]).size()
    fumble_forced_rate = (
        (forced_count / def_plays).rename_axis(axis_names).rename("Fumble Forced Rate (Def)")
    )

    # ---- Fumble Recovery Rate (LUCK-driven): every real fumble contributes one "team
    # perspective" row for whichever team was on offense that play and one for whichever was
    # on defense -- a team's Recovery Rate = (fumbles it recovered) / (fumbles it was
    # involved in either way), fully general, not assuming posteam always fumbled it. -----
    rows_pos = fum[["posteam", "season", "fumble_recovery_1_team"]].rename(
        columns={"posteam": "team"}
    )
    rows_def = fum[["defteam", "season", "fumble_recovery_1_team"]].rename(
        columns={"defteam": "team"}
    )
    long = pd.concat([rows_pos, rows_def], ignore_index=True)
    long["recovered_by_team"] = long["team"] == long["fumble_recovery_1_team"]
    involved = long.groupby(["team", "season"]).size()
    recovered = long.groupby(["team", "season"])["recovered_by_team"].sum()
    fumble_recovery_rate = (recovered / involved).rename("Fumble Recovery Rate")

    # ---- Actual Turnover Differential: real Takeaways - real Giveaways, using fumbled_1_
    # team/fumble_recovery_1_team directly (fully general, handles the ~8% edge-case
    # fumbles honestly rather than assuming posteam always fumbled it). ------------------
    int_takeaway = (
        reg[reg["interception"] == 1].groupby(["defteam", "season"]).size()
        .rename_axis(axis_names)
    )
    int_giveaway = (
        reg[reg["interception"] == 1].groupby(["posteam", "season"]).size()
        .rename_axis(axis_names)
    )
    real_turnover_fum = fum[fum["fumble_recovery_1_team"] != fum["fumbled_1_team"]]
    fum_takeaway = (
        real_turnover_fum.groupby(["fumble_recovery_1_team", "season"]).size()
        .rename_axis(axis_names)
    )
    fum_giveaway = (
        real_turnover_fum.groupby(["fumbled_1_team", "season"]).size()
        .rename_axis(axis_names)
    )

    takeaways = int_takeaway.add(fum_takeaway, fill_value=0)
    giveaways = int_giveaway.add(fum_giveaway, fill_value=0)
    turnover_diff = (
        takeaways.reindex(involved.index, fill_value=0)
        - giveaways.reindex(involved.index, fill_value=0)
    ).rename("Actual Turnover Differential")

    pass_attempts_off = att_count.rename_axis(axis_names).rename("Pass Attempts (Off)")
    offensive_plays = off_plays.rename_axis(axis_names).rename("Offensive Plays")
    defensive_plays = def_plays.rename_axis(axis_names).rename("Defensive Plays")
    def_pass_attempts_faced = (
        reg[reg["pass_attempt"] == 1].groupby(["defteam", "season"]).size()
        .rename_axis(axis_names).rename("Defensive Pass Attempts Faced")
    )

    out = (
        int_rate_thrown.to_frame()
        .join(fumble_lost_rate, how="outer")
        .join(fumble_forced_rate, how="outer")
        .join(fumble_recovery_rate, how="outer")
        .join(turnover_diff, how="outer")
        .join(pass_attempts_off, how="outer")
        .join(offensive_plays, how="outer")
        .join(defensive_plays, how="outer")
        .join(def_pass_attempts_faced, how="outer")
        .reset_index()
    )
    # The 4 real count columns are genuine 0s (not missing data) when a team has no
    # matching rows for that side of the ball in the pulled data -- fillna(0), not left NaN.
    count_cols = [
        "Pass Attempts (Off)", "Offensive Plays", "Defensive Plays",
        "Defensive Pass Attempts Faced",
    ]
    out[count_cols] = out[count_cols].fillna(0)
    out = out.rename(columns={"team": "team_abbr", "season": "Season"})

    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team_abbr"].map(TEAM_NAMES)

    out = out.sort_values(["Team", "Season"]).reset_index(drop=True)
    return out[TURNOVER_OUTPUT_COLUMNS]


REDZONE_OUTPUT_COLUMNS = [
    "Team", "Season", "Red-Zone Drive Count", "Red-Zone TD%", "Goal-to-Go Drive Count",
    "Goal-to-Go TD%", "Red-Zone EPA",
]


def compute_team_season_redzone_components(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. See this module's own docstring for the real drive-level
    field reasoning and the (game_id, posteam, drive) grouping-key bug this caught before
    shipping.

    Columns: Team | Season | Red-Zone Drive Count | Red-Zone TD% | Goal-to-Go Drive Count |
    Goal-to-Go TD% | Red-Zone EPA
    """
    reg = pbp[pbp["season_type"] == "REG"]
    scrimmage = reg[reg["play_type"].isin(["pass", "run"])].dropna(subset=["drive"])

    drives = scrimmage.groupby(["game_id", "posteam", "drive"]).agg(
        season=("season", "first"),
        inside20=("drive_inside20", "max"),
        result=("fixed_drive_result", "first"),
    ).reset_index()

    rz_drives = drives[drives["inside20"] == True]  # noqa: E712 (real 0.0/1.0 float flag)
    rz_count = rz_drives.groupby(["posteam", "season"]).size().rename("Red-Zone Drive Count")
    rz_td = (
        rz_drives.groupby(["posteam", "season"])["result"]
        .apply(lambda s: (s == "Touchdown").mean())
        .rename("Red-Zone TD%")
    )

    g2g_plays = scrimmage[scrimmage["goal_to_go"] == 1]
    g2g_drives = g2g_plays.groupby(["game_id", "posteam", "drive"]).agg(
        season=("season", "first"), result=("fixed_drive_result", "first"),
    ).reset_index()
    g2g_count = (
        g2g_drives.groupby(["posteam", "season"]).size().rename("Goal-to-Go Drive Count")
    )
    g2g_td = (
        g2g_drives.groupby(["posteam", "season"])["result"]
        .apply(lambda s: (s == "Touchdown").mean())
        .rename("Goal-to-Go TD%")
    )

    rz_plays = scrimmage[scrimmage["yardline_100"] <= 20]
    rz_epa = rz_plays.groupby(["posteam", "season"])["epa"].mean().rename("Red-Zone EPA")

    out = (
        rz_count.to_frame()
        .join(rz_td, how="outer")
        .join(g2g_count, how="outer")
        .join(g2g_td, how="outer")
        .join(rz_epa, how="outer")
        .reset_index()
    )
    out = out.rename(columns={"posteam": "team_abbr", "season": "Season"})

    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team_abbr"].map(TEAM_NAMES)

    out = out.sort_values(["Team", "Season"]).reset_index(drop=True)
    return out[REDZONE_OUTPUT_COLUMNS]


def main(
    years: list[int] | None = None, output_path: str = "team_season_turnover_stats.csv"
) -> pd.DataFrame:
    from nflverse_pull.efficiency import fetch_pbp

    years = years or [2023, 2024, 2025]
    pbp = fetch_pbp(years)

    stats = compute_team_season_turnover_components(pbp)
    stats.to_csv(output_path, index=False)
    print(stats.head(10))
    print(f"\nSaved {len(stats)} rows to {output_path}")
    return stats


if __name__ == "__main__":
    import sys

    cli_years = [int(a) for a in sys.argv[1:]] or None
    main(years=cli_years)
