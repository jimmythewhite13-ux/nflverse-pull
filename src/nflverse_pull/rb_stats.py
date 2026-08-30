"""
Pulls per-RB-season rushing efficiency (Rushing EPA/Play, Rushing Success Rate, YPC) from
nflverse play-by-play data. Same fetch/transform split as qb_stats.py (reuses
efficiency.py's fetch_pbp() -- pbp is a heavy pull, don't re-fetch it separately). See
claude_code_spec_rb_index.md.

Schema note (verified against the installed nfl_data_py package before writing this, per
the spec's own instruction): rushing plays have the OPPOSITE null pattern from passing
plays. On a QB scramble/run, `rusher_id`/`rusher` are null while `rusher_player_id`/
`rusher_player_name` stay populated -- the reverse of qb_stats.py's passer_id/
passer_player_id finding. This groups on rusher_player_id/rusher_player_name accordingly.

Also verified: `rushing_yards` is null on 33 of 14895 real 2025 run plays (fumble/penalty
edge cases) while `yards_gained` is never null and agrees with rushing_yards everywhere it
IS populated -- used yards_gained for YPC to avoid silently dropping those plays, and for
consistency with efficiency.py's team-level NY/A, which uses the same column.

Rush Yards Over Expected per Attempt (RYOE/Att): real, OFFICIAL NFL Next Gen Stats data
(nfl_data_py.import_ngs_data("rushing", years)), not derived from pbp -- NGS's own tracking-
data model of expected yards per carry based on defender positioning at handoff, isolating
the RUNNER's own skill from blocking/scheme more precisely than EPA or YPC can. Verified
live before adding this: `week == 0` rows are real season aggregates (not something to sum
from weekly rows), `player_gsis_id` matches this project's existing Player ID format
exactly, and NGS applies its OWN (higher) qualifying-volume threshold than this module's
MIN_QUALIFYING_CARRIES=50 -- real 2025 check found 51 NGS-tracked RBs (min 92 carries) vs.
78 RBs this module considers qualifying, meaning some real, qualifying-here players won't
have a real RYOE value. Handled as a genuinely missing data point (left blank downstream),
not zero-filled or assumed.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES

# RBs get committee'd, injured, and rotated more than QBs get benched -- a lower minimum
# sample threshold than QB's 100 dropbacks is appropriate. Below this, a RB-season is
# OMITTED entirely from that player's history (not zero-filled), same pattern as QB.
MIN_QUALIFYING_CARRIES = 50

SEASON_STATS_COLUMNS = [
    "Team", "Season", "Player Name", "Player ID", "Carries", "Rushing EPA/Play",
    "Rushing Success Rate", "YPC", "Is Rookie Season",
]


def compute_team_season_rb_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. One row per RB per season per team -- same shape and
    conventions as qb_stats.compute_team_season_qb_stats().

    Columns: Team | Season | Player Name | Player ID | Carries | Rushing EPA/Play |
    Rushing Success Rate | YPC | Is Rookie Season
    """
    reg = pbp[pbp["season_type"] == "REG"]

    runs = reg[reg["play_type"] == "run"]
    runs = runs[runs["rusher_player_id"].notna()]

    group_cols = ["rusher_player_id", "season", "posteam"]

    carries = runs.groupby(group_cols).size().rename("Carries")
    rushing_epa = runs.groupby(group_cols)["epa"].mean().rename("Rushing EPA/Play")
    # Success is already a 0/1 flag per play (epa > 0), same column efficiency.py's team-
    # level Success Rate uses -- its mean over a group is exactly "share of positive-EPA
    # rush attempts", matching the spec's definition directly.
    success_rate = runs.groupby(group_cols)["success"].mean().rename("Rushing Success Rate")
    ypc = runs.groupby(group_cols)["yards_gained"].mean().rename("YPC")
    player_name = (
        runs.groupby(group_cols)["rusher_player_name"]
        .agg(lambda s: s.mode().iat[0])
        .rename("Player Name")
    )

    out = (
        carries.to_frame()
        .join(rushing_epa)
        .join(success_rate)
        .join(ypc)
        .join(player_name)
        .reset_index()
    )
    out = out.rename(columns={
        "rusher_player_id": "Player ID", "season": "Season", "posteam": "team_abbr",
    })

    out = out[out["Carries"] >= MIN_QUALIFYING_CARRIES].copy()

    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team_abbr"].map(TEAM_NAMES)

    # Rookie-season proxy: identical convention to qb_stats.py -- the first season (across
    # every team-row) this player_id appears with a qualifying sample, not their first raw
    # pbp appearance (which could be a below-threshold cup of coffee).
    first_qualifying_season = out.groupby("Player ID")["Season"].transform("min")
    out["Is Rookie Season"] = out["Season"] == first_qualifying_season

    out = out.sort_values(
        ["Team", "Season", "Carries"], ascending=[True, True, False]
    ).reset_index(drop=True)
    return out[SEASON_STATS_COLUMNS]


def compute_historical_rb_roles(season_stats: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Historical, attempts-ranking-based Role per (Player ID,
    Season) -- same pattern as qb_stats.compute_qb_roles(), ranking by Carries instead of
    Dropbacks. Per the spec: this is ONLY used to label each PAST season's role for Section
    1/2 (e.g. so the league-average-among-Starters+Backups filter makes sense historically);
    it is explicitly NOT used to determine the CURRENT Starter/Backup for Section 3/5/6 or
    Team Ratings -- that comes from current_roster.py's live depth-chart data instead.

    Output: Team | Season | Player Name | Player ID | Role | Carries
    """
    rank = season_stats.groupby(["Team", "Season"])["Carries"].rank(method="first", ascending=False)
    out = season_stats.copy()
    out["Role"] = rank.map({1: "Starter", 2: "Backup"}).fillna("Other")
    return out[["Team", "Season", "Player Name", "Player ID", "Role", "Carries"]]


def compute_carry_share(population: pd.DataFrame, season_stats: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. For each team with BOTH a Starter and a Backup in
    `population` (current-roster-identified -- see current_roster.resolve_scored_population,
    Part B of claude_code_spec_rb_index.md), finds each player's most recent season's
    Carries in `season_stats` and computes:

        Carry Share (Y-1) = Starter's carries / (Starter + Backup carries)

    The committee-detection signal the spec calls for: near 0.5 means a genuine committee
    backfield (Replacement Value means less there), near 1.0 means a clear bell-cow. A
    player with zero Section 1 rows (a true rookie) contributes 0 carries here, which still
    produces a meaningful share rather than an error (e.g. 1.0 if the incumbent has all the
    recent carries and the new arrival has none yet).

    Output: Team | Carry Share (Y-1) | Starter Carries (Y-1) | Backup Carries (Y-1)
    """

    def _most_recent_carries(player_id: str) -> int:
        rows = season_stats[season_stats["Player ID"] == player_id]
        if len(rows) == 0:
            return 0
        return int(rows.sort_values("Season", ascending=False).iloc[0]["Carries"])

    out_rows = []
    for team in population["Team"].unique():
        team_pop = population[population["Team"] == team]
        starter = team_pop[team_pop["Role"] == "Starter"]
        backup = team_pop[team_pop["Role"] == "Backup"]
        if len(starter) == 0 or len(backup) == 0:
            continue
        starter_carries = _most_recent_carries(starter.iloc[0]["Player ID"])
        backup_carries = _most_recent_carries(backup.iloc[0]["Player ID"])
        total = starter_carries + backup_carries
        share = starter_carries / total if total > 0 else None
        out_rows.append({
            "Team": team, "Carry Share (Y-1)": share,
            "Starter Carries (Y-1)": starter_carries, "Backup Carries (Y-1)": backup_carries,
        })
    return pd.DataFrame(
        out_rows,
        columns=["Team", "Carry Share (Y-1)", "Starter Carries (Y-1)", "Backup Carries (Y-1)"],
    )


def fetch_ngs_rushing(years: list[int]) -> pd.DataFrame:
    """Network call -- real, official NFL Next Gen Stats rushing data (weekly + season-
    aggregate rows; compute_player_season_ryoe filters to the real season aggregates)."""
    import nfl_data_py as nfl

    return nfl.import_ngs_data("rushing", years)


# NGS quirk verified live before writing this (not assumed): NGS uses "LAR" for the Rams
# consistently across 2023-2025 (unlike this project's own TEAM_NAMES, and unlike PFR's own
# inconsistent-across-years LAR/LVR quirk documented in oline_stats.py) -- the Raiders'
# "LV" matches TEAM_NAMES correctly in NGS, so only LAR needs remapping here.
_NGS_TEAM_REMAP = {"LAR": "LA"}


def compute_player_season_ryoe(ngs_rushing: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real per-player season Rush Yards Over Expected per Attempt,
    from NFL Next Gen Stats' own season-aggregate rows (`week == 0` -- verified live this is
    the real seasonal total, not something to sum from weekly rows).

    Columns: Player ID | Season | Team | RYOE/Att
    """
    season = ngs_rushing[ngs_rushing["week"] == 0].copy()
    season = season[season["player_gsis_id"].notna()]
    season["team_abbr"] = season["team_abbr"].replace(_NGS_TEAM_REMAP)

    unmapped = sorted(set(season["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")

    out = pd.DataFrame({
        "Player ID": season["player_gsis_id"],
        "Season": season["season"],
        "Team": season["team_abbr"].map(TEAM_NAMES),
        "RYOE/Att": season["rush_yards_over_expected_per_att"],
    })
    return out.reset_index(drop=True)


def main(
    years: list[int] | None = None, output_path: str = "team_season_rb_stats.csv"
) -> pd.DataFrame:
    from nflverse_pull.efficiency import fetch_pbp

    years = years or [2023, 2024, 2025]
    pbp = fetch_pbp(years)

    stats = compute_team_season_rb_stats(pbp)
    stats.to_csv(output_path, index=False)
    print(stats.head(10))
    print(f"\nSaved {len(stats)} rows to {output_path}")
    return stats


if __name__ == "__main__":
    import sys

    cli_years = [int(a) for a in sys.argv[1:]] or None
    main(years=cli_years)
