"""
Pulls REAL, free, publicly available team-level offensive line metrics from Pro Football
Reference (via nfl_data_py.import_seasonal_pfr) -- Pass_Protection and Run_Blocking, as
requested. Feeds the workbook's "Offensive Line Index" tab.

Why PFR instead of individual per-lineman grades (LT/LG/C/RG/RT skill numbers): checked
before writing this, per project convention -- there is no free, public, per-lineman
performance grade anywhere in nfl_data_py or any other real data source this project has
access to. That's exactly PFF's proprietary domain (confirmed: PFF IDs exist in nflverse's
own player-ID crosswalk for cross-referencing, but not PFF's actual grade VALUES, which
require a paid subscription this project doesn't have). ESPN's Pass Block Win Rate / Run
Block Win Rate are real free TEAM-level metrics, but aren't available through nfl_data_py
or any documented free API -- would need scraping ESPN's site, which this project doesn't
do anywhere else. PFR's charted stats ARE available live through nfl_data_py and give a
real, legitimate, TEAM-level proxy for both pass protection and run blocking:

- Pass_Protection = 100 - team's pass-attempt-weighted pressure rate allowed (PFR charts
  pressure/hit/hurry against the QB, not the blocker who allowed it -- but rolled up to
  team level, "how often was this team's QB pressured" is a real, honest pass-protection
  signal, same category of proxy as CPOE standing in for QB accuracy).
- Run_Blocking = team's attempt-weighted Yards Before Contact per Attempt (YBC/Att) -- a
  well-established, real run-blocking proxy (how much room did the line create before the
  runner was touched), also charted per-carry by PFR and rolled up to team level.

Both are genuinely TEAM-level stats, not per-player -- there is no "who's the starting
LT's own Pass_Protection number" here, unlike every other position in this project. See
current_roster.py for the separate, real INDIVIDUAL-level data this tab also uses (which
starter, and their real NFL experience) -- that's identity/availability data, not a
fabricated per-player skill grade.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES


def fetch_pfr_pass(years: list[int]) -> pd.DataFrame:
    """Network call -- PFR's per-QB season passing/pressure charting."""
    import nfl_data_py as nfl

    return nfl.import_seasonal_pfr("pass", years)


def fetch_pfr_rush(years: list[int]) -> pd.DataFrame:
    """Network call -- PFR's per-RB season rushing/yards-before-contact charting."""
    import nfl_data_py as nfl

    return nfl.import_seasonal_pfr("rush", years)


# PFR quirk verified live before writing this (not assumed): the 2023 'pass' dataset alone
# uses "LAR"/"LVR" where every other year/dataset (2024/2025 pass, all 3 years of rush) uses
# "LA"/"LV" -- an inconsistency in PFR's own team-abbreviation history, not a bug in this
# module. Remapped here so both eras join against TEAM_NAMES correctly.
_PFR_TEAM_REMAP = {"LAR": "LA", "LVR": "LV"}

# A player traded mid-season gets a "2TM"/"3TM" aggregate row IN ADDITION TO his real
# per-team split rows (verified live: a 2024 2TM passer's MIA + NYG rows summed exactly to
# his 2TM row's totals) -- excluding the aggregate avoids double-counting, not data loss.
_PFR_MULTI_TEAM_CODES = {"2TM", "3TM"}


def compute_team_season_oline_stats(
    pfr_pass: pd.DataFrame, pfr_rush: pd.DataFrame
) -> pd.DataFrame:
    """
    Pure function, no network. One row per TEAM per season (not per player -- see module
    docstring for why this position's real data is inherently team-level).

    Columns: Team | Season | Pass_Protection | Run_Blocking
    """
    pass_df = pfr_pass.copy()
    pass_df = pass_df[~pass_df["team"].isin(_PFR_MULTI_TEAM_CODES)]
    pass_df["team"] = pass_df["team"].replace(_PFR_TEAM_REMAP)
    pass_df = pass_df[pass_df["pass_attempts"] > 0]
    pass_df["pressured"] = pass_df["times_pressured"].fillna(0)
    # Attempt-weighted team pressure rate: sum(times_pressured) / sum(pass_attempts) across
    # every QB who threw for that team that season, not a simple average-of-QB-rates (which
    # would let a 5-attempt mop-up appearance count as much as a full starter's season).
    pass_team = pass_df.groupby(["team", "season"]).agg(
        total_attempts=("pass_attempts", "sum"), total_pressured=("pressured", "sum")
    ).reset_index()
    pass_team["Pass_Protection"] = 100 * (
        1 - pass_team["total_pressured"] / pass_team["total_attempts"]
    )

    rush_df = pfr_rush.copy()
    rush_df = rush_df[~rush_df["tm"].isin(_PFR_MULTI_TEAM_CODES)]
    rush_df["tm"] = rush_df["tm"].replace(_PFR_TEAM_REMAP)
    rush_df = rush_df[rush_df["att"] > 0]
    rush_df["ybc"] = rush_df["ybc"].fillna(0)
    # Attempt-weighted team Yards Before Contact per Attempt, same weighting logic as above.
    rush_team = rush_df.groupby(["tm", "season"]).agg(
        total_att=("att", "sum"), total_ybc=("ybc", "sum")
    ).reset_index()
    rush_team["Run_Blocking"] = rush_team["total_ybc"] / rush_team["total_att"]
    rush_team = rush_team.rename(columns={"tm": "team"})

    out = pass_team[["team", "season", "Pass_Protection"]].merge(
        rush_team[["team", "season", "Run_Blocking"]], on=["team", "season"], how="outer"
    )
    out = out.rename(columns={"season": "Season"})

    unmapped = sorted(set(out["team"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team"].map(TEAM_NAMES)

    out = out.sort_values(["Team", "Season"]).reset_index(drop=True)
    return out[["Team", "Season", "Pass_Protection", "Run_Blocking"]]


def main(
    years: list[int] | None = None, output_path: str = "team_season_oline_stats.csv"
) -> pd.DataFrame:
    years = years or [2023, 2024, 2025]
    pfr_pass = fetch_pfr_pass(years)
    pfr_rush = fetch_pfr_rush(years)

    stats = compute_team_season_oline_stats(pfr_pass, pfr_rush)
    stats.to_csv(output_path, index=False)
    print(stats.head(10))
    print(f"\nSaved {len(stats)} rows to {output_path}")
    return stats


if __name__ == "__main__":
    import sys

    cli_years = [int(a) for a in sys.argv[1:]] or None
    main(years=cli_years)
