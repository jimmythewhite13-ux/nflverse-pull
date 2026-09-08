"""
Pulls per-kicker-season kicking efficiency (FG% Over Expected, distance-adjusted; raw FG%;
XP%) from nflverse play-by-play data. Feeds the workbook's "Kicking Index" tab (Phase 3 of
the multi-phase roadmap in claude_code_spec_rb_index.md -- no separate written spec exists
for this phase; designed directly, mirroring rb_stats.py's / receiving_stats.py's pattern).

Reuses efficiency.py's fetch_pbp() -- pbp is a heavy pull, don't re-fetch it separately.

Schema note (verified against the installed nfl_data_py package before writing this, per
project convention): the kicker's position abbreviation in depth-chart data is "PK" (Place
Kicker), not "K" -- see current_roster.py. Kicking-play columns used here: `play_type`
("field_goal" / "extra_point"), `kicker_player_id`/`kicker_player_name` (never null on a
real field_goal or extra_point play, verified against real 2025 data -- no scramble-style
null-pattern quirk here, unlike passer/rusher/receiver), `field_goal_result` ("made" /
"missed" / "blocked"), `kick_distance`, `extra_point_result` ("good" / "failed" / "blocked").

FG% Over Expected (distance-adjusted) is this module's CPOE-equivalent for kickers: for each
individual field-goal attempt, "expected" is the LEAGUE-WIDE make rate for that attempt's
5-yard distance bucket, computed across ALL pulled years COMBINED (not per-season, unlike
every other Section 2 league average in this project) -- a single season's per-bucket sample
(e.g. the 50-54-yard bucket) is often too thin league-wide for a stable rate; combining years
gives a materially more stable baseline while remaining real pulled data, not a fabricated
model. A kicker-season's FG% Over Expected is the average of (make [1/0] - expected) across
his attempts that season.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES

# Kickers attempt far fewer field goals per season than a QB has dropbacks or a WR has
# targets -- a much lower minimum sample threshold is appropriate. Below this, a
# kicker-season is OMITTED entirely from that player's history (not zero-filled), same
# pattern as every other stats module in this project.
MIN_QUALIFYING_FG_ATTEMPTS = 15

# 5-yard buckets for the league-wide "expected" make-rate lookup (e.g. a 42-yard attempt
# falls in the 40-44 bucket). A named, tunable constant, not a hardcoded magic number.
DISTANCE_BUCKET_SIZE = 5

SEASON_STATS_COLUMNS = [
    "Team", "Season", "Player Name", "Player ID", "FG Attempts", "FG% Over Expected",
    "FG%", "XP%", "Is Rookie Season",
]


def compute_team_season_kicking_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. One row per kicker per season per team -- same shape and
    conventions as the other stats modules in this project.

    Columns: Team | Season | Player Name | Player ID | FG Attempts | FG% Over Expected |
    FG% | XP% | Is Rookie Season
    """
    reg = pbp[pbp["season_type"] == "REG"]

    fg = reg[reg["play_type"] == "field_goal"]
    fg = fg[fg["kicker_player_id"].notna()].copy()
    fg["made"] = (fg["field_goal_result"] == "made").astype(int)
    fg["distance_bucket"] = (fg["kick_distance"] // DISTANCE_BUCKET_SIZE) * DISTANCE_BUCKET_SIZE

    # League-wide expected make rate per distance bucket, across every pulled year combined
    # -- see the module docstring for why this one lookup deliberately isn't per-season.
    bucket_rate = fg.groupby("distance_bucket")["made"].mean()
    fg["expected_make"] = fg["distance_bucket"].map(bucket_rate)
    fg["make_over_expected"] = fg["made"] - fg["expected_make"]

    group_cols = ["kicker_player_id", "season", "posteam"]
    fg_attempts = fg.groupby(group_cols).size().rename("FG Attempts")
    fg_pct = fg.groupby(group_cols)["made"].mean().rename("FG%")
    fg_oe = fg.groupby(group_cols)["make_over_expected"].mean().rename("FG% Over Expected")
    player_name = (
        fg.groupby(group_cols)["kicker_player_name"]
        .agg(lambda s: s.mode().iat[0])
        .rename("Player Name")
    )

    out = (
        fg_attempts.to_frame()
        .join(fg_pct)
        .join(fg_oe)
        .join(player_name)
        .reset_index()
    )
    out = out.rename(columns={
        "kicker_player_id": "Player ID", "season": "Season", "posteam": "team_abbr",
    })

    # Guard against a pbp slice with zero extra_point rows (a real full pull always has
    # both play types, but an FG-only test fixture -- or a bizarre real slice -- would leave
    # "extra_point_result" missing from the DataFrame's columns entirely, not just empty).
    if "extra_point_result" in reg.columns:
        xp = reg[reg["play_type"] == "extra_point"]
        xp = xp[xp["kicker_player_id"].notna()].copy()
        xp["good"] = (xp["extra_point_result"] == "good").astype(int)
        xp_pct = (
            xp.groupby(group_cols)["good"].mean().rename("XP%")
            .reset_index()
            .rename(columns={
                "kicker_player_id": "Player ID", "season": "Season", "posteam": "team_abbr",
            })
        )
    else:
        xp_pct = pd.DataFrame(columns=["Player ID", "Season", "team_abbr", "XP%"])
    out = out.merge(xp_pct, on=["Player ID", "Season", "team_abbr"], how="left")

    out = out[out["FG Attempts"] >= MIN_QUALIFYING_FG_ATTEMPTS].copy()

    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team_abbr"].map(TEAM_NAMES)

    # Rookie-season proxy: identical convention to every other stats module in this project.
    first_qualifying_season = out.groupby("Player ID")["Season"].transform("min")
    out["Is Rookie Season"] = out["Season"] == first_qualifying_season

    out = out.sort_values(
        ["Team", "Season", "FG Attempts"], ascending=[True, True, False]
    ).reset_index(drop=True)
    return out[SEASON_STATS_COLUMNS]


def main(
    years: list[int] | None = None, output_path: str = "team_season_kicking_stats.csv"
) -> pd.DataFrame:
    from nflverse_pull.efficiency import fetch_pbp

    years = years or [2023, 2024, 2025]
    pbp = fetch_pbp(years)

    stats = compute_team_season_kicking_stats(pbp)
    stats.to_csv(output_path, index=False)
    print(stats.head(10))
    print(f"\nSaved {len(stats)} rows to {output_path}")
    return stats


if __name__ == "__main__":
    import sys

    cli_years = [int(a) for a in sys.argv[1:]] or None
    main(years=cli_years)
