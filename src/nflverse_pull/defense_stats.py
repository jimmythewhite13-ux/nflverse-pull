"""
Pulls REAL front-seven defensive counting stats from nflverse play-by-play data -- team-
level rates (Sack Rate, TFL Rate, QB Hit Rate) and individual per-player season totals.
Feeds the workbook's "Front Seven & D-Line Index" tab. Scoped to EDGE/interior-line/
linebacker per explicit user instruction -- secondary (CB/S, INT/PBU) is a separate future
phase, not built here.

This follows claude_code_spec_rb_index.md's own guidance for defense almost exactly:
"counting-stats index only (sacks/TFL/INT/PBU), explicitly NOT an EPA-equivalent value
model" -- real, individually-attributed plays, not an invented per-position grade (see
oline_stats.py's docstring for why that pattern was rejected for offensive line, and why
the same reasoning applies to any 0-100 "Pass_Rush_Grade"/"Coverage_Grade"-style input).

Schema, verified live before writing this: `sack`, `qb_hit`, and `tackled_for_loss` are
real 0/1 flags on every pbp row; `defteam` (the team ON DEFENSE for that play) is the
correct team-attribution column -- NOT `posteam` (the team with the ball), which would
attribute a sack/hit/TFL to the team that GOT sacked instead of the team that caused it.
Individual attribution: `sack_player_id` (full sacks) plus `half_sack_1_player_id`/
`half_sack_2_player_id` (split sacks on a co-credited play -- each half-sack player gets
0.5, matching the NFL's own official sack-crediting convention); `qb_hit_1_player_id`/
`qb_hit_2_player_id` (up to 2 players credited per QB-hit play); `tackle_for_loss_1_player_
id`/`tackle_for_loss_2_player_id` (up to 2 players credited per TFL play).

Rate denominators: Sack Rate and QB Hit Rate use the defense's real pass plays faced
(`pass_attempt == 1` while on defense -- verified this already includes sack plays, same
"pass_attempt is TRUE on a sack too" quirk documented in receiving_stats.py, so sacks are
correctly counted in their own denominator). TFL Rate uses ALL real defensive plays faced
(TFL can happen on a run OR a pass play, unlike sacks/QB hits which are pass-play-only).
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES

# Individual sack/QB-hit/TFL credit columns, in the order NFL/PFR convention charts them
# (a play can have 0, 1, or 2 credited players -- e.g. a split sack, or two defenders
# sharing hit/TFL credit on the same play).
_SACK_COLS = ["sack_player_id"]
_HALF_SACK_COLS = ["half_sack_1_player_id", "half_sack_2_player_id"]
_QB_HIT_COLS = ["qb_hit_1_player_id", "qb_hit_2_player_id"]
_TFL_COLS = ["tackle_for_loss_1_player_id", "tackle_for_loss_2_player_id"]


def compute_team_season_front7_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. One row per TEAM per season -- team-level, like
    oline_stats.py (there is no honest reason to gate a TEAM rate stat behind a per-player
    qualifying threshold; it's already a full-season aggregate).

    Columns: Team | Season | Sack Rate | TFL Rate | QB Hit Rate
    """
    reg = pbp[pbp["season_type"] == "REG"]
    reg = reg[reg["defteam"].notna()]

    pass_faced = reg[reg["pass_attempt"] == 1]
    pass_denom = pass_faced.groupby(["defteam", "season"]).size().rename("pass_plays_faced")
    all_denom = reg.groupby(["defteam", "season"]).size().rename("all_plays_faced")

    sacks = reg.groupby(["defteam", "season"])["sack"].sum().rename("sacks")
    qb_hits = reg.groupby(["defteam", "season"])["qb_hit"].sum().rename("qb_hits")
    tfls = reg.groupby(["defteam", "season"])["tackled_for_loss"].sum().rename("tfls")

    out = (
        pass_denom.to_frame()
        .join(all_denom)
        .join(sacks)
        .join(qb_hits)
        .join(tfls)
        .reset_index()
    )
    out = out.rename(columns={"defteam": "team", "season": "Season"})

    out["Sack Rate"] = out["sacks"] / out["pass_plays_faced"]
    out["QB Hit Rate"] = out["qb_hits"] / out["pass_plays_faced"]
    out["TFL Rate"] = out["tfls"] / out["all_plays_faced"]

    unmapped = sorted(set(out["team"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team"].map(TEAM_NAMES)

    out = out.sort_values(["Team", "Season"]).reset_index(drop=True)
    return out[["Team", "Season", "Sack Rate", "TFL Rate", "QB Hit Rate"]]


def compute_player_season_front7_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real per-player season totals -- Section 6's individual
    layer (a current starter's OWN real production, not a proxy or invented grade). A full
    sack counts 1.0; each of the (up to 2) players on a split sack counts 0.5, matching the
    NFL's own official crediting convention.

    Columns: Player ID | Season | Team | Sacks | TFL | QB Hits
    """
    reg = pbp[pbp["season_type"] == "REG"]
    reg = reg[reg["defteam"].notna()]

    def _credit_counts(df: pd.DataFrame, cols: list[str], weight: float = 1.0) -> pd.Series:
        parts = []
        for col in cols:
            if col not in df.columns:
                continue
            sub = df[df[col].notna()]
            if len(sub):
                parts.append(
                    sub.groupby(["defteam", "season", col]).size().mul(weight)
                    .rename_axis(index={col: "player_id"})
                )
        if not parts:
            return pd.Series(dtype=float, name="count")
        combined = pd.concat(parts)
        return combined.groupby(level=[0, 1, 2]).sum()

    sacks = _credit_counts(reg, _SACK_COLS, weight=1.0)
    half_sacks = _credit_counts(reg, _HALF_SACK_COLS, weight=0.5)
    qb_hits = _credit_counts(reg, _QB_HIT_COLS, weight=1.0)
    tfls = _credit_counts(reg, _TFL_COLS, weight=1.0)

    # Long-format (one row per team/season/player/stat/value) then pivoted with an explicit
    # sum aggregation -- two sources sharing the same stat name (full + half sacks both
    # produce "Sacks") must ADD, not collide into suffixed columns the way a naive
    # merge-per-source would (a real bug caught by this module's own test suite: an earlier
    # draft used sequential merges here and silently dropped the half-sack contribution).
    long_frames = []
    for series, label in [(sacks, "Sacks"), (half_sacks, "Sacks"),
                           (qb_hits, "QB Hits"), (tfls, "TFL")]:
        if len(series) == 0:
            continue
        f = series.rename("value").reset_index()
        f = f.rename(columns={"defteam": "team", "season": "Season"})
        f["stat"] = label
        long_frames.append(f)

    if not long_frames:
        return pd.DataFrame(columns=["Player ID", "Season", "Team", "Sacks", "TFL", "QB Hits"])

    long_df = pd.concat(long_frames, ignore_index=True)
    combined = long_df.pivot_table(
        index=["team", "Season", "player_id"], columns="stat", values="value",
        aggfunc="sum", fill_value=0.0,
    ).reset_index()
    combined.columns.name = None

    for col in ("Sacks", "TFL", "QB Hits"):
        if col not in combined.columns:
            combined[col] = 0.0

    unmapped = sorted(set(combined["team"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    combined["Team"] = combined["team"].map(TEAM_NAMES)
    combined = combined.rename(columns={"player_id": "Player ID"})

    return combined[["Player ID", "Season", "Team", "Sacks", "TFL", "QB Hits"]]


def main(
    years: list[int] | None = None, output_path: str = "team_season_front7_stats.csv"
) -> pd.DataFrame:
    from nflverse_pull.efficiency import fetch_pbp

    years = years or [2023, 2024, 2025]
    pbp = fetch_pbp(years)

    stats = compute_team_season_front7_stats(pbp)
    stats.to_csv(output_path, index=False)
    print(stats.head(10))
    print(f"\nSaved {len(stats)} rows to {output_path}")
    return stats


if __name__ == "__main__":
    import sys

    cli_years = [int(a) for a in sys.argv[1:]] or None
    main(years=cli_years)
