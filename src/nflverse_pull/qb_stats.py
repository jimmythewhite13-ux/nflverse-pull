"""
Pulls per-QB-season passing efficiency (EPA/play, CPOE, ANY/A) from nflverse play-by-play
data and identifies each team's Starter/Backup QB by season. Feeds the workbook's "QB
Index" tab (see claude_code_spec_qb_index.md).

Reuses efficiency.py's fetch_pbp() -- pbp is a heavy pull, don't re-fetch it separately.
Same fetch/pure-transform split as pull.py / efficiency.py.

Schema note (verified against the installed nfl_data_py package before writing this, per
the spec's own instruction -- column names have drifted before): `passer_player_id` and
`passer_player_name` are null on scramble plays (a qb_dropback, but not a `pass_attempt`),
even though the QB obviously has an identity on that play. `passer_id` / `passer` stay
populated across every dropback type (attempt, sack, scramble), so those are what this
module groups and names by -- not the more "obvious" passer_player_id/passer_player_name,
which would silently drop every scramble from a QB's own stat line.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES

# Below this many dropbacks in a season, a QB-season is mop-up duty or an injury-shortened
# stint and is OMITTED entirely from that QB's history (not zero-filled) -- same as a
# missing year is handled by the YoY Baseline Engine's SUMIFS-returns-0-if-absent pattern.
MIN_QUALIFYING_DROPBACKS = 100

# ANY/A (Adjusted Net Yards per Attempt) constants.
ANY_A_TD_BONUS = 20
ANY_A_INT_PENALTY = 45

SEASON_STATS_COLUMNS = [
    "Team", "Season", "Player Name", "Player ID", "Dropbacks", "EPA/Play", "CPOE", "ANY/A",
    "Is Rookie Season",
]


def compute_team_season_qb_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. One row per QB per season per team -- a QB who played for
    two teams in a season gets one row per team here (see compute_qb_roles() for how a
    single season-of-record team gets picked for roster/role purposes downstream).

    Columns: Team | Season | Player Name | Player ID | Dropbacks | EPA/Play | CPOE | ANY/A |
    Is Rookie Season
    """
    reg = pbp[pbp["season_type"] == "REG"]

    if "qb_dropback" in reg.columns:
        dropbacks = reg[reg["qb_dropback"] == 1]
    else:
        # Fallback if the column is ever renamed/removed upstream -- covers the same three
        # play types qb_dropback does (attempts, sacks, scrambles).
        dropbacks = reg[
            (reg["pass_attempt"] == 1) | (reg["sack"] == 1) | (reg["qb_scramble"] == 1)
        ]
    dropbacks = dropbacks[dropbacks["passer_id"].notna()]

    attempts = dropbacks[dropbacks["pass_attempt"] == 1]
    sacks = dropbacks[dropbacks["sack"] == 1]

    group_cols = ["passer_id", "season", "posteam"]

    dropback_count = dropbacks.groupby(group_cols).size().rename("Dropbacks")
    epa_play = dropbacks.groupby(group_cols)["epa"].mean().rename("EPA/Play")
    # CPOE is only defined for thrown passes -- sacks/scrambles have no completion to grade.
    cpoe = attempts.groupby(group_cols)["cpoe"].mean().rename("CPOE")
    # `passer` (short display name, e.g. "K.Murray") stays populated on every dropback type,
    # unlike passer_player_name -- take the most common spelling per group as a safety net
    # against the rare mid-season name-field hiccup.
    player_name = (
        dropbacks.groupby(group_cols)["passer"]
        .agg(lambda s: s.mode().iat[0])
        .rename("Player Name")
    )

    att_yards = attempts.groupby(group_cols)["passing_yards"].sum()
    att_count = attempts.groupby(group_cols).size()
    att_td = attempts.groupby(group_cols)["pass_touchdown"].sum()
    att_int = attempts.groupby(group_cols)["interception"].sum()
    # Sack yardage lives in yards_gained (already negative), not passing_yards -- same
    # pattern efficiency.py's team-level NY/A calc uses, reused here rather than
    # reimplemented differently.
    sack_yards = sacks.groupby(group_cols)["yards_gained"].sum()
    sack_count = sacks.groupby(group_cols).size()

    any_a_numerator = (
        att_yards.add(sack_yards, fill_value=0)
        + ANY_A_TD_BONUS * att_td
        - ANY_A_INT_PENALTY * att_int
    )
    any_a_denominator = att_count.add(sack_count, fill_value=0)
    any_a = (any_a_numerator / any_a_denominator).rename("ANY/A")

    out = (
        dropback_count.to_frame()
        .join(epa_play)
        .join(cpoe)
        .join(any_a)
        .join(player_name)
        .reset_index()
    )
    out = out.rename(columns={"passer_id": "Player ID", "season": "Season", "posteam": "team_abbr"})

    # Minimum sample filter -- below-threshold seasons are dropped, not zero-filled.
    out = out[out["Dropbacks"] >= MIN_QUALIFYING_DROPBACKS].copy()

    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team_abbr"].map(TEAM_NAMES)

    # Rookie-season proxy: the first season (across every team-row) this player_id appears
    # with a qualifying sample -- NOT the first season they appear in raw pbp at all (which
    # could be a below-threshold cup-of-coffee stint that got filtered above), and NOT
    # cross-referenced against actual draft-year data. nfl_data_py's import_ids() carries a
    # real draft_year column if this proxy needs upgrading later; using the pbp-observed
    # proxy here is a documented simplification, not an oversight.
    first_qualifying_season = out.groupby("Player ID")["Season"].transform("min")
    out["Is Rookie Season"] = out["Season"] == first_qualifying_season

    out = out.sort_values(
        ["Team", "Season", "Dropbacks"], ascending=[True, True, False]
    ).reset_index(drop=True)
    return out[SEASON_STATS_COLUMNS]


def compute_qb_roles(season_stats: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Resolves each (Player ID, Season) to a single season-of-
    record team -- the team they had the most dropbacks with that season, for a QB who
    played for two teams in one season -- then ranks QBs within that team-season by
    Dropbacks: highest = Starter, second-highest = Backup, everyone else = Other.

    Output: Team | Season | Player Name | Player ID | Role | Dropbacks
    """
    idx = season_stats.groupby(["Player ID", "Season"])["Dropbacks"].idxmax()
    season_of_record = season_stats.loc[idx].copy()

    rank = season_of_record.groupby(["Team", "Season"])["Dropbacks"].rank(
        method="first", ascending=False
    )
    season_of_record["Role"] = rank.map({1: "Starter", 2: "Backup"}).fillna("Other")

    out = season_of_record[["Team", "Season", "Player Name", "Player ID", "Role", "Dropbacks"]]
    return out.sort_values(
        ["Team", "Season", "Dropbacks"], ascending=[True, True, False]
    ).reset_index(drop=True)


def main(
    years: list[int] | None = None,
    stats_output_path: str = "team_season_qb_stats.csv",
    roles_output_path: str = "team_qb_roles.csv",
) -> pd.DataFrame:
    from nflverse_pull.efficiency import fetch_pbp

    years = years or [2023, 2024, 2025]
    pbp = fetch_pbp(years)

    stats = compute_team_season_qb_stats(pbp)
    stats.to_csv(stats_output_path, index=False)
    print(stats.head(10))
    print(f"\nSaved {len(stats)} rows to {stats_output_path}")

    roles = compute_qb_roles(stats)
    roles.to_csv(roles_output_path, index=False)
    print(f"Saved {len(roles)} rows to {roles_output_path}")

    return stats


if __name__ == "__main__":
    import sys

    cli_years = [int(a) for a in sys.argv[1:]] or None
    main(years=cli_years)
