"""
Pulls per-receiver-season receiving efficiency (Receiving EPA/Target, Reception Success
Rate, YPT) from nflverse play-by-play data. Feeds the workbook's "WR/TE Value Index" tab
(Phase 2 of the multi-phase roadmap in claude_code_spec_rb_index.md -- no separate written
spec exists for this phase; designed directly, mirroring rb_stats.py's own pattern).

Reuses efficiency.py's fetch_pbp() -- pbp is a heavy pull, don't re-fetch it separately.
Same fetch/transform split as qb_stats.py / rb_stats.py.

Deliberately NOT filtered to WR/TE here -- same convention as qb_stats.py (any passer, even
a trick-play WR, is included) and rb_stats.py (any rusher, even a WR end-around): position
identity for POPULATION/scoring purposes comes entirely from current_roster.py's depth-chart
lookup, not from this module. A RB's receiving stats flow through here too; they're simply
never looked up by the WR/TE tab's current-roster population, which only ever resolves WR
and TE roles.

Schema note (verified against the installed nfl_data_py package before writing this, per
project convention -- column names have drifted before): nflverse's `pass_attempt` flag is
TRUE on a sack too (1,287 of 18,822 real 2025 pass_attempt rows were also sack=1 -- an
"intended dropback" flag, not "ball was thrown"). A "target" here is therefore
`pass_attempt == 1 AND sack == 0 AND receiver_player_id notna` -- excludes sacks (no
receiver exists on one) and excludes the ~836 real 2025 rows where pass_attempt=1, sack=0,
but no receiver was ever credited (throwaways, spikes, intentional grounding -- always
incomplete, never a real target). `receiver_player_id` vs `receiver_id` was also checked:
unlike the passer_id/rusher_id quirks, these two are functionally identical on real target
plays (1 mismatch out of 17,535 real 2025 targets) -- receiver_player_id/receiver_player_name
are used here for consistency with the other stats modules' "_player_" convention.

Avg Separation / YAC Over Expectation: real, OFFICIAL NFL Next Gen Stats data
(nfl_data_py.import_ngs_data("receiving", years)), not derived from pbp -- NGS's own
tracking-data measures of route-running/get-open skill (average yards of separation from the
nearest defender at the moment of catch) and after-catch playmaking isolated from the type of
catch (actual YAC minus a model's expected YAC given the catch's context). Unlike QB Index's
NGS context additions, BOTH of these are SCORED here (same treatment as RB Index's RYOE/Att):
each has an unambiguous "higher is better" direction and measures a real skill this tab's
existing 3 metrics (EPA/Target, Success Rate, YPT -- all outcome/value measures) don't isolate
on their own. Verified live before adding this: NGS receiving applies its OWN, higher
qualifying-volume threshold (2023-2025 minimum real targets: 45) than this module's own
MIN_QUALIFYING_TARGETS=40, so some real, qualifying receiver-seasons here won't have real NGS
values -- handled as a genuinely missing data point (left blank), not zero-filled or assumed,
same pattern as RYOE/Att and everywhere else in this project.

Pass-Play Snap Participation % / Red-Zone Target Share (claude_code_spec_route_redzone_usage.md
-- "Route Participation" in that spec's own title, renamed here per an explicit finding
reported to and confirmed by the user): a real "how often is this player actually involved"
signal, distinct from the efficiency metrics above (which measure value GIVEN opportunity, not
how much opportunity exists).

HONESTY NOTE on Pass-Play Snap Participation %: the spec asked for true "Route Participation"
(routes run / team pass plays). Verified live before building this: no free source has that.
nflverse's real `route` pbp column (FTN-charted, confirmed genuinely free) is the route TYPE
of the TARGETED receiver only on plays where a target happened -- it says nothing about the
other ~10 offensive players on that same play, let alone plays where this player wasn't
targeted at all. NFL Next Gen Stats' receiving data (already used above for Avg Separation/
YAC Over Expectation) has no route-count field either. What IS real and free: nflverse's own
participation data (`offense_players`, verified live: 0 nulls on 2025's real pass plays)
lists every player literally on the field for a given play. Pass-Play Snap Participation % =
(real pass plays this player was on the field for) / (team's total real pass plays that
season) -- a genuine, defensible proxy for "how much this player is used in the passing game,"
but NOT confirmed route-running (a player on the field to pass-block, or on a called run-pass-
option, still counts here). Same "real proxy, honestly distinguished from the ideal" treatment
as this project's "Pressure Proxy" (= QB Hit Rate) on Pass Defense Matchup.

Red-Zone Target Share = real red-zone targets (yardline_100<=20, using this module's own
existing "target" definition: pass_attempt==1 AND sack==0 AND receiver_player_id notna, for
internal consistency) / team's total real red-zone targets that season. Unlike Avg Separation/
YAC Over Expectation, there's no separate qualifying threshold here -- a qualifying (>=
MIN_QUALIFYING_TARGETS) receiver-season with zero real red-zone targets gets a real 0.0, not a
blank; the denominator (team red-zone target volume) is never zero for a real team-season.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES

# WR3/TE1 volume is naturally lower than a bell-cow RB's carries or a starting QB's
# dropbacks -- a lower minimum sample threshold than RB's 50 carries is appropriate. Below
# this, a receiver-season is OMITTED entirely from that player's history (not zero-filled),
# same pattern as every other stats module in this project.
MIN_QUALIFYING_TARGETS = 40

SEASON_STATS_COLUMNS = [
    "Team", "Season", "Player Name", "Player ID", "Targets", "Receiving EPA/Target",
    "Reception Success Rate", "YPT", "Is Rookie Season",
]


def compute_team_season_receiving_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. One row per receiver per season per team -- same shape and
    conventions as qb_stats.compute_team_season_qb_stats() / rb_stats.
    compute_team_season_rb_stats().

    Columns: Team | Season | Player Name | Player ID | Targets | Receiving EPA/Target |
    Reception Success Rate | YPT | Is Rookie Season
    """
    reg = pbp[pbp["season_type"] == "REG"]

    targets = reg[(reg["pass_attempt"] == 1) & (reg["sack"] == 0)]
    targets = targets[targets["receiver_player_id"].notna()]

    group_cols = ["receiver_player_id", "season", "posteam"]

    target_count = targets.groupby(group_cols).size().rename("Targets")
    epa = targets.groupby(group_cols)["epa"].mean().rename("Receiving EPA/Target")
    # Success is already a 0/1 flag per play (epa > 0), same column every other stats module
    # in this project uses -- its mean over a group is "share of positive-EPA targets".
    success = targets.groupby(group_cols)["success"].mean().rename("Reception Success Rate")
    ypt = targets.groupby(group_cols)["yards_gained"].mean().rename("YPT")
    player_name = (
        targets.groupby(group_cols)["receiver_player_name"]
        .agg(lambda s: s.mode().iat[0])
        .rename("Player Name")
    )

    out = (
        target_count.to_frame()
        .join(epa)
        .join(success)
        .join(ypt)
        .join(player_name)
        .reset_index()
    )
    out = out.rename(columns={
        "receiver_player_id": "Player ID", "season": "Season", "posteam": "team_abbr",
    })

    out = out[out["Targets"] >= MIN_QUALIFYING_TARGETS].copy()

    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team_abbr"].map(TEAM_NAMES)

    # Rookie-season proxy: identical convention to every other stats module in this
    # project -- the first season (across every team-row) this player_id appears with a
    # qualifying sample, not their first raw pbp appearance.
    first_qualifying_season = out.groupby("Player ID")["Season"].transform("min")
    out["Is Rookie Season"] = out["Season"] == first_qualifying_season

    out = out.sort_values(
        ["Team", "Season", "Targets"], ascending=[True, True, False]
    ).reset_index(drop=True)
    return out[SEASON_STATS_COLUMNS]


def fetch_ngs_receiving(years: list[int]) -> pd.DataFrame:
    """Network call -- real, official NFL Next Gen Stats receiving data (weekly + season-
    aggregate rows; compute_player_season_ngs_receiving filters to the real season
    aggregates)."""
    import nfl_data_py as nfl

    return nfl.import_ngs_data("receiving", years)


# NGS quirk verified live before writing this (same check already done for qb_stats.py's
# and rb_stats.py's own NGS pulls): NGS uses "LAR" for the Rams consistently across
# 2023-2025 -- the Raiders' "LV" matches TEAM_NAMES correctly, so only LAR needs remapping.
_NGS_TEAM_REMAP = {"LAR": "LA"}


def compute_player_season_ngs_receiving(ngs_receiving: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real per-player season Avg Separation and YAC Over
    Expectation, from NFL Next Gen Stats' own season-aggregate rows (`week == 0` --
    verified live this is the real seasonal total, not something to average from weekly
    rows). Both SCORED metrics -- see this module's own docstring for why.

    YAC Over Expectation = avg_yac - avg_expected_yac (NGS provides both separately; this
    module computes the difference itself since NGS doesn't ship it as a single column).

    Columns: Player ID | Season | Team | Avg Separation | YAC Over Expectation
    """
    season = ngs_receiving[ngs_receiving["week"] == 0].copy()
    season = season[season["player_gsis_id"].notna()]
    season["team_abbr"] = season["team_abbr"].replace(_NGS_TEAM_REMAP)

    unmapped = sorted(set(season["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")

    out = pd.DataFrame({
        "Player ID": season["player_gsis_id"],
        "Season": season["season"],
        "Team": season["team_abbr"].map(TEAM_NAMES),
        "Avg Separation": season["avg_separation"],
        "YAC Over Expectation": season["avg_yac"] - season["avg_expected_yac"],
    })
    return out.reset_index(drop=True)


def compute_player_season_pass_play_participation(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real "Pass-Play Snap Participation %" -- see this module's own
    docstring for the honesty note on why this is a real, defensible PROXY for route
    participation, not a confirmed route-run count (no free source has that).

    Columns: Player ID | Season | Team | Pass-Play Snap Participation %
    """
    reg = pbp[(pbp["season_type"] == "REG") & (pbp["play_type"] == "pass")]
    reg = reg[reg["offense_players"].notna()]

    team_totals = reg.groupby(["season", "posteam"]).size().rename("Team Pass Plays")

    exploded = reg[["season", "posteam", "offense_players"]].copy()
    exploded["Player ID"] = exploded["offense_players"].str.split(";")
    exploded = exploded.explode("Player ID")
    on_field = (
        exploded.groupby(["Player ID", "season", "posteam"]).size()
        .rename("Pass Plays On Field")
    )

    out = on_field.reset_index().merge(
        team_totals.reset_index(), on=["season", "posteam"], how="left"
    )
    out = out.rename(columns={"season": "Season", "posteam": "team_abbr"})

    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team_abbr"].map(TEAM_NAMES)
    out["Pass-Play Snap Participation %"] = out["Pass Plays On Field"] / out["Team Pass Plays"]

    return out[["Player ID", "Season", "Team", "Pass-Play Snap Participation %"]]


def compute_player_season_red_zone_target_share(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real Red-Zone Target Share (yardline_100<=20; same "target"
    definition this module's own compute_team_season_receiving_stats already uses --
    pass_attempt==1 AND sack==0 AND receiver_player_id notna -- for internal consistency).

    Columns: Player ID | Season | Team | Red-Zone Target Share
    """
    reg = pbp[(pbp["season_type"] == "REG") & (pbp["yardline_100"] <= 20)]
    targets = reg[(reg["pass_attempt"] == 1) & (reg["sack"] == 0)]
    targets = targets[targets["receiver_player_id"].notna()]

    group_cols = ["receiver_player_id", "season", "posteam"]
    rz_targets = targets.groupby(group_cols).size().rename("RZ Targets")
    team_rz_targets = (
        targets.groupby(["season", "posteam"]).size().rename("Team RZ Targets")
    )

    out = rz_targets.reset_index().merge(
        team_rz_targets.reset_index(), on=["season", "posteam"], how="left"
    )
    out = out.rename(columns={
        "receiver_player_id": "Player ID", "season": "Season", "posteam": "team_abbr",
    })

    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team_abbr"].map(TEAM_NAMES)
    out["Red-Zone Target Share"] = out["RZ Targets"] / out["Team RZ Targets"]

    return out[["Player ID", "Season", "Team", "Red-Zone Target Share"]]


def main(
    years: list[int] | None = None, output_path: str = "team_season_receiving_stats.csv"
) -> pd.DataFrame:
    from nflverse_pull.efficiency import fetch_pbp

    years = years or [2023, 2024, 2025]
    pbp = fetch_pbp(years)

    stats = compute_team_season_receiving_stats(pbp)
    stats.to_csv(output_path, index=False)
    print(stats.head(10))
    print(f"\nSaved {len(stats)} rows to {output_path}")
    return stats


if __name__ == "__main__":
    import sys

    cli_years = [int(a) for a in sys.argv[1:]] or None
    main(years=cli_years)
