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

NGS passing context (Avg Time to Throw, Aggressiveness %): real, OFFICIAL NFL Next Gen Stats
data (nfl_data_py.import_ngs_data("passing", years)), not derived from pbp -- NGS's own
tracking-data measures of pocket-process speed and willingness to throw into tight coverage.
Deliberately CONTEXT ONLY, never scored: unlike RB Index's RYOE/Att (a real skill-isolation
signal with an unambiguous "higher is better" direction), neither of these has one -- a fast
release can mean decisive processing or an offense that scripts quick, low-value throws; high
Aggressiveness can mean elite arm talent or recklessness. NGS's own official Completion % Over
Expectation (`completion_percentage_above_expectation`) was deliberately NOT added here even
though it exists in the same real dataset: this tab's existing CPOE column (from pbp's own
`cpoe`) already measures the same underlying skill from a different model, and adding NGS's
version as a second scored metric would double-count accuracy in the weighted composite rather
than add a genuinely new signal (verified live before deciding this: pbp's mean cpoe and NGS's
own completion_percentage_above_expectation for the same real QB-season, e.g. Caleb Williams
2025, are close but not identical -- -3.51 vs. -6.87 -- different models of the same skill, not
different skills). Verified live before adding this: NGS passing applies its OWN, higher
qualifying-volume threshold (2023-2025 minimum real attempts: 136-160) than this module's
MIN_QUALIFYING_DROPBACKS=100, so some real, qualifying QB-seasons here won't have real NGS
context -- handled as a genuinely missing data point (left blank), not zero-filled or assumed,
same pattern as everywhere else in this project.

Success Rate / Explosive Pass Rate / Sack Rate / TD / INT (claude_code_spec_qb_environment_
model.md Part A): compute_player_season_qb_extended_stats(). Success Rate and Explosive Pass
Rate use the SAME play_type=="pass" population (includes sacks as a real negative dropback
outcome, excludes scrambles) efficiency.py's own team-level Pass Success Rate / Explosive
Pass Rate (EXPLOSIVE_PASS_YARDS, imported not redefined) already use, for internal
consistency rather than a new convention. Sack Rate uses the BROADER qb_dropback population
(includes scrambles) this module's own EPA/Play already uses -- the standard "sacks per real
dropback" definition. TD/INT Ratio is CONTEXT ONLY, never scored, per the spec's own explicit
instruction not to double-count a signal ANY/A's formula (+20*TD-45*INT) already includes --
blank when INT=0 for that QB-season (division genuinely undefined), not a fabricated infinity
or a silent 0. Sack Rate is likewise NOT a scored Talent metric -- see
claude_code_spec_qb_environment_model.md Part A/C for why it's tracked separately instead
(taking a sack isn't inherently a skill deficiency; it matters specifically combined with a
bad pass-protection environment, a different question).
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.efficiency import EXPLOSIVE_PASS_YARDS
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


def compute_player_season_qb_extended_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real per-QB-season Success Rate, Explosive Pass Rate, Sack
    Rate, TD, INT, TD/INT Ratio -- see this module's own docstring for each metric's exact
    population/denominator and why TD/INT Ratio and Sack Rate are unscored. Meant to be
    LEFT-JOINED onto compute_team_season_qb_stats()'s own output by (Player ID, Season,
    Team) -- not filtered by MIN_QUALIFYING_DROPBACKS itself (that filter already applies
    via the join, since this covers every real dropback in the pulled years).

    Columns: Player ID | Season | Team | Success Rate | Explosive Pass Rate | Sack Rate |
    TD | INT | TD/INT Ratio
    """
    reg = pbp[pbp["season_type"] == "REG"]

    if "qb_dropback" in reg.columns:
        dropbacks = reg[reg["qb_dropback"] == 1]
    else:
        dropbacks = reg[
            (reg["pass_attempt"] == 1) | (reg["sack"] == 1) | (reg["qb_scramble"] == 1)
        ]
    dropbacks = dropbacks[dropbacks["passer_id"].notna()].copy()

    group_cols = ["passer_id", "season", "posteam"]
    dropback_count = dropbacks.groupby(group_cols).size()

    # Sack Rate: sacks / ALL real dropbacks (the broader qb_dropback population, matching
    # this module's own EPA/Play denominator) -- computed from the SAME groupby object as
    # dropback_count (not a separately-filtered subset), so every group gets a real 0 sack
    # count rather than a missing one that would need reindexing.
    dropbacks["is_sack"] = dropbacks["sack"] == 1
    sack_count = dropbacks.groupby(group_cols)["is_sack"].sum()
    sack_rate = (sack_count / dropback_count).rename("Sack Rate")

    # Success Rate / Explosive Pass Rate: play_type=="pass" only (includes sacks, excludes
    # scrambles) -- matches efficiency.py's own team-level convention for these two metrics
    # specifically (different from EPA/Play's broader qb_dropback denominator above).
    pass_plays = dropbacks[dropbacks["play_type"] == "pass"].copy()
    pass_plays["explosive"] = pass_plays["yards_gained"] >= EXPLOSIVE_PASS_YARDS
    success_rate = pass_plays.groupby(group_cols)["success"].mean().rename("Success Rate")
    explosive_rate = (
        pass_plays.groupby(group_cols)["explosive"].mean().rename("Explosive Pass Rate")
    )

    attempts = dropbacks[dropbacks["pass_attempt"] == 1]
    td = attempts.groupby(group_cols)["pass_touchdown"].sum().rename("TD")
    interceptions = attempts.groupby(group_cols)["interception"].sum().rename("INT")

    out = (
        dropback_count.rename("_dropbacks").to_frame()
        .join(success_rate)
        .join(explosive_rate)
        .join(sack_rate)
        .join(td)
        .join(interceptions)
        .reset_index()
    )
    out = out.rename(columns={
        "passer_id": "Player ID", "season": "Season", "posteam": "team_abbr",
    })

    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team_abbr"].map(TEAM_NAMES)

    out["TD/INT Ratio"] = [
        (t / i) if i > 0 else None for t, i in zip(out["TD"], out["INT"], strict=True)
    ]

    return out[[
        "Player ID", "Season", "Team", "Success Rate", "Explosive Pass Rate", "Sack Rate",
        "TD", "INT", "TD/INT Ratio",
    ]]


def fetch_ngs_passing(years: list[int]) -> pd.DataFrame:
    """Network call -- real, official NFL Next Gen Stats passing data (weekly + season-
    aggregate rows; compute_player_season_qb_ngs_context filters to the real season
    aggregates)."""
    import nfl_data_py as nfl

    return nfl.import_ngs_data("passing", years)


# NGS quirk verified live before writing this (not assumed, same check already done for
# rb_stats.py's RYOE pull): NGS uses "LAR" for the Rams consistently across 2023-2025 --
# the Raiders' "LV" matches TEAM_NAMES correctly, so only LAR needs remapping here.
_NGS_TEAM_REMAP = {"LAR": "LA"}


def compute_player_season_qb_ngs_context(ngs_passing: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real per-player season Avg Time to Throw and Aggressiveness
    %, from NFL Next Gen Stats' own season-aggregate rows (`week == 0` -- verified live this
    is the real seasonal total, not something to average from weekly rows). CONTEXT ONLY --
    see this module's own docstring for why neither metric is scored.

    NGS's own `aggressiveness` field is a raw percentage NUMBER (e.g. 12.4 meaning 12.4%,
    verified live), not a 0-1 fraction like every rate/percentage elsewhere in this project
    (Reception Success Rate, FG%, Blitz Rate, ...) -- divided by 100 here so it's on the same
    0-1 scale and Excel's "0.00%" number format displays it correctly downstream.

    Columns: Player ID | Season | Team | Avg Time to Throw | Aggressiveness
    """
    season = ngs_passing[ngs_passing["week"] == 0].copy()
    season = season[season["player_gsis_id"].notna()]
    season["team_abbr"] = season["team_abbr"].replace(_NGS_TEAM_REMAP)

    unmapped = sorted(set(season["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")

    out = pd.DataFrame({
        "Player ID": season["player_gsis_id"],
        "Season": season["season"],
        "Team": season["team_abbr"].map(TEAM_NAMES),
        "Avg Time to Throw": season["avg_time_to_throw"],
        "Aggressiveness": season["aggressiveness"] / 100.0,
    })
    return out.reset_index(drop=True)


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
