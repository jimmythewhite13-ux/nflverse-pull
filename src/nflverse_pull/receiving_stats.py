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
