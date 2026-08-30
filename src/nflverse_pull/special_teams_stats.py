"""
Pulls REAL special-teams counting/average stats from nflverse play-by-play data -- team-
level rates (Net Punt Average, Return Average) and individual per-player season averages.
Feeds the workbook's "Special Teams Index" tab (punting + return game -- placekicking is
already covered separately by "Kicking Index").

Same real-data-only approach as every other position tab in this project (see oline_stats.py
/ defense_stats.py docstrings for the full reasoning against invented per-position grades).

Schema, verified live before writing this: `punt_attempt`, `kickoff_attempt` are real 0/1
flags; `kick_distance` is populated on every real, non-blocked punt (never null); `punter_
player_id`, `kickoff_returner_player_id`, `punt_returner_player_id` are the real individual
attribution columns; `return_yards` is the real yardage gained on that specific return (0 on
a touchback/fair catch/out-of-bounds, not null). `posteam` is the team that PUNTED (for
punting stats); `defteam` is the team RETURNING (for return stats) -- the reverse of which
column matters for front-seven/secondary defensive stats, since here the "offense" of
special teams is the kicking team on a punt, not the team on offense in the normal sense.

Net Punt Average = (kick_distance - return_yards) per punt, excluding blocked punts (no
real kick_distance/return concept applies to a block, same exclusion the NFL's own official
net-average stat uses). KNOWN SIMPLIFICATION, documented not hidden: this does NOT apply a
touchback adjustment the way the NFL's official net-punting stat does (a touchback is
capped at effectively landing at the 20-yard line in official stats; this module instead
just uses the real kick_distance as charted, which can overstate a bomb into the end zone
that produces a touchback). A more precise version would need the actual line-of-scrimmage
yardline to compute touchback-adjusted distance -- left as a documented future refinement,
not attempted here.

Return Average = real return_yards per real return, kickoff and punt returns tracked
separately (a team's KR1 and PR1 are often different players).
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES


def compute_team_season_special_teams_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. One row per TEAM per season -- team-level, same pattern as
    oline_stats.py / defense_stats.py's team functions.

    Columns: Team | Season | Net Punt Average | Return Average
    """
    reg = pbp[pbp["season_type"] == "REG"]

    punts = reg[(reg["punt_attempt"] == 1) & (reg["punt_blocked"] != 1)]
    punts = punts[punts["posteam"].notna()]
    net_yards = punts["kick_distance"] - punts["return_yards"].fillna(0)
    punt_team = (
        net_yards.groupby([punts["posteam"], punts["season"]])
        .mean()
        .rename("Net Punt Average")
    )
    punt_team.index.names = ["team", "Season"]

    kr = reg[reg["kickoff_returner_player_id"].notna()]
    pr = reg[reg["punt_returner_player_id"].notna()]
    kr_sum = kr.groupby(["defteam", "season"])["return_yards"].sum()
    kr_count = kr.groupby(["defteam", "season"]).size()
    pr_sum = pr.groupby(["defteam", "season"])["return_yards"].sum()
    pr_count = pr.groupby(["defteam", "season"]).size()

    return_totals = pd.DataFrame({
        "yards": kr_sum.add(pr_sum, fill_value=0),
        "count": kr_count.add(pr_count, fill_value=0),
    })
    return_totals.index.names = ["team", "Season"]
    return_avg = (return_totals["yards"] / return_totals["count"]).rename("Return Average")

    out = punt_team.to_frame().join(return_avg, how="outer").reset_index()

    unmapped = sorted(set(out["team"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team"].map(TEAM_NAMES)

    out = out.sort_values(["Team", "Season"]).reset_index(drop=True)
    return out[["Team", "Season", "Net Punt Average", "Return Average"]]


def compute_player_season_punting_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real per-punter season average -- Section 6's individual
    layer for the punter.

    Columns: Player ID | Season | Team | Net Punt Average | Punts
    """
    reg = pbp[pbp["season_type"] == "REG"]
    punts = reg[(reg["punt_attempt"] == 1) & (reg["punt_blocked"] != 1)]
    punts = punts[punts["punter_player_id"].notna()]

    net_yards = punts["kick_distance"] - punts["return_yards"].fillna(0)
    group_cols = ["punter_player_id", "season", "posteam"]
    avg = net_yards.groupby(
        [punts[c] for c in group_cols]
    ).mean().rename("Net Punt Average")
    count = punts.groupby(group_cols).size().rename("Punts")

    out = avg.to_frame().join(count).reset_index()
    out = out.rename(columns={
        "punter_player_id": "Player ID", "season": "Season", "posteam": "team",
    })

    unmapped = sorted(set(out["team"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team"].map(TEAM_NAMES)

    return out[["Player ID", "Season", "Team", "Net Punt Average", "Punts"]]


def compute_player_season_return_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real per-returner season averages -- Section 6's individual
    layer for the kick returner and punt returner (often different players, tracked
    separately -- a player only gets a row for the role(s) he actually returned in).

    Columns: Player ID | Season | Team | KR Average | KR Returns | PR Average | PR Returns
    """
    reg = pbp[pbp["season_type"] == "REG"]

    def _side(df: pd.DataFrame, id_col: str, avg_label: str, count_label: str) -> pd.DataFrame:
        sub = df[df[id_col].notna()]
        group_cols = [id_col, "season", "defteam"]
        avg = sub.groupby(group_cols)["return_yards"].mean().rename(avg_label)
        count = sub.groupby(group_cols).size().rename(count_label)
        out = avg.to_frame().join(count).reset_index()
        return out.rename(columns={id_col: "player_id", "season": "Season", "defteam": "team"})

    kr = _side(reg, "kickoff_returner_player_id", "KR Average", "KR Returns")
    pr = _side(reg, "punt_returner_player_id", "PR Average", "PR Returns")

    combined = kr.merge(pr, on=["player_id", "Season", "team"], how="outer")

    unmapped = sorted(set(combined["team"].dropna()) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    combined["Team"] = combined["team"].map(TEAM_NAMES)
    combined = combined.rename(columns={"player_id": "Player ID"})

    return combined[
        ["Player ID", "Season", "Team", "KR Average", "KR Returns", "PR Average", "PR Returns"]
    ]


def main(
    years: list[int] | None = None, output_path: str = "team_season_special_teams_stats.csv"
) -> pd.DataFrame:
    from nflverse_pull.efficiency import fetch_pbp

    years = years or [2023, 2024, 2025]
    pbp = fetch_pbp(years)

    stats = compute_team_season_special_teams_stats(pbp)
    stats.to_csv(output_path, index=False)
    print(stats.head(10))
    print(f"\nSaved {len(stats)} rows to {output_path}")
    return stats


if __name__ == "__main__":
    import sys

    cli_years = [int(a) for a in sys.argv[1:]] or None
    main(years=cli_years)
