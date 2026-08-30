"""
Pulls REAL, free, publicly available team-level offensive line metrics -- Pro Football
Reference (via nfl_data_py.import_seasonal_pfr) for Pass_Protection and Run_Blocking, plus
FTN Data's real per-play charting (via nfl_data_py.import_ftn_data) for a fault-adjusted
sack rate. Feeds the workbook's "Offensive Line Index" tab.

Provenance note on the FTN data (claude_code_spec_ftn_fix.md): confirmed by reading
nfl_data_py's own source and a live unauthenticated pull that `import_ftn_data` fetches a
public parquet file from nflverse's own GitHub Releases -- no API key, login, or
subscription check anywhere in the code path. This is FTN Data's own real charting,
released under a CC-BY-SA 4.0 Creative Commons license specifically for open publication
via nflverse (per that function's own docstring) -- NOT FTN Fantasy's paid subscription
product, which this project has no access to and does not use anywhere.

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

Sack-Free Rate (Fault-Adjusted): PFR's Pass_Protection (pressure rate) blames the O-line for
every sack, even ones charted as the QB's own fault (held the ball too long, etc.) -- a real
gap identified once FTN Data's real, free per-play charting (via nflverse) was found to carry
`is_qb_fault_sack`. Checked live before building this: FTN's real charting matched 100% of
2025's real sack plays (1,287/1,287, joined via game_id/play_id), with 445 (34.6%) charted
as the QB's own fault -- a substantial, real signal worth correcting for, not noise.
Sack-Free Rate (Fault-Adjusted) = 1 - (real sacks NOT charted as QB-fault / real pass plays
faced), framed as a "higher is better" clean-pocket rate for consistency with every other
metric in this project (same inversion convention Pass_Protection itself already uses).
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


def fetch_ftn(years: list[int]) -> pd.DataFrame:
    """Network call -- FTN Data's real per-play charting (blitz/box counts, sack fault,
    play-action, drops, etc.), released free under CC-BY-SA 4.0 via nflverse's GitHub
    Releases -- no API key or subscription required (verified live; see this module's own
    docstring)."""
    import nfl_data_py as nfl

    return nfl.import_ftn_data(years)


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


def compute_team_season_sack_fault_stats(pbp: pd.DataFrame, ftn: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real, fault-adjusted sack rate per team-season, joining
    nflverse pbp (real sack plays) against FTN Data's real charting (is_qb_fault_sack) by
    game_id/play_id. Team-level, attributed to `posteam` (the team whose O-line is being
    evaluated) -- the same direction Pass_Protection already uses, and the OPPOSITE of
    defense_stats.py's Sack Rate (which attributes to `defteam`, the team that caused it).

    Columns: Team | Season | Sack-Free Rate (Fault-Adjusted)
    """
    reg = pbp[pbp["season_type"] == "REG"].copy()
    reg = reg[reg["posteam"].notna()]
    reg["play_id"] = reg["play_id"].astype("Int64")

    ftn_join = ftn[["nflverse_game_id", "nflverse_play_id", "is_qb_fault_sack"]].copy()
    ftn_join["nflverse_play_id"] = ftn_join["nflverse_play_id"].astype("Int64")

    merged = reg.merge(
        ftn_join, left_on=["game_id", "play_id"],
        right_on=["nflverse_game_id", "nflverse_play_id"], how="left",
    )

    pass_faced = merged[merged["pass_attempt"] == 1]
    pass_denom = pass_faced.groupby(["posteam", "season"]).size().rename("pass_plays_faced")

    # A sack not charted as the QB's own fault (including a sack FTN didn't charge at all,
    # i.e. is_qb_fault_sack is NaN -- treated as NOT proven QB-fault, so it still counts
    # against the line by default, same conservative-default spirit as every other honest
    # fallback in this project) is attributed to the O-line here.
    sacks = merged[merged["sack"] == 1].copy()
    sacks["ol_fault"] = sacks["is_qb_fault_sack"] != True  # noqa: E712
    ol_fault_sacks = sacks.groupby(["posteam", "season"])["ol_fault"].sum().rename("ol_fault_sacks")

    out = pass_denom.to_frame().join(ol_fault_sacks).reset_index()
    out["ol_fault_sacks"] = out["ol_fault_sacks"].fillna(0)
    out = out.rename(columns={"posteam": "team", "season": "Season"})
    out["Sack-Free Rate (Fault-Adjusted)"] = 1 - out["ol_fault_sacks"] / out["pass_plays_faced"]

    unmapped = sorted(set(out["team"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team"].map(TEAM_NAMES)

    out = out.sort_values(["Team", "Season"]).reset_index(drop=True)
    return out[["Team", "Season", "Sack-Free Rate (Fault-Adjusted)"]]


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
