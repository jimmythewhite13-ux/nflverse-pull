"""
Pulls REAL defensive counting stats from nflverse play-by-play data -- team-level rates and
individual per-player season totals, for both the front seven (Sack Rate, TFL Rate, QB Hit
Rate -- feeds "Front Seven & D-Line Index") and the secondary (INT Rate, PBU Rate -- feeds
"Secondary Index").

This follows claude_code_spec_rb_index.md's own guidance for defense almost exactly:
"counting-stats index only (sacks/TFL/INT/PBU), explicitly NOT an EPA-equivalent value
model" -- real, individually-attributed plays, not an invented per-position grade (see
oline_stats.py's docstring for why that pattern was rejected for offensive line, and why
the same reasoning applies to any 0-100 "Pass_Rush_Grade"/"Coverage_Grade"-style input).

Schema, verified live before writing this: `sack`, `qb_hit`, `tackled_for_loss`, and
`interception` are real 0/1 flags on every pbp row; `defteam` (the team ON DEFENSE for that
play) is the correct team-attribution column -- NOT `posteam` (the team with the ball),
which would attribute a sack/hit/TFL/INT to the team that GOT sacked/picked off instead of
the team that caused it. Individual attribution: `sack_player_id` (full sacks) plus
`half_sack_1_player_id`/`half_sack_2_player_id` (split sacks on a co-credited play -- each
half-sack player gets 0.5, matching the NFL's own official sack-crediting convention);
`qb_hit_1_player_id`/`qb_hit_2_player_id` and `tackle_for_loss_1_player_id`/`tackle_for_
loss_2_player_id` (up to 2 players credited per play); `interception_player_id` (never null
on a real interception play, verified live); `pass_defense_1_player_id`/`pass_defense_2_
player_id` (up to 2 players credited per pass-breakup play).

Rate denominators: Sack Rate, QB Hit Rate, INT Rate, and PBU Rate all use the defense's real
pass plays faced (`pass_attempt == 1` while on defense -- verified this already includes
sack plays, same "pass_attempt is TRUE on a sack too" quirk documented in
receiving_stats.py). TFL Rate uses ALL real defensive plays faced (TFL can happen on a run
OR a pass play, unlike the other four which are pass-play-only).

Scheme context (Blitz Rate, Avg Box Count): CORRECTED per claude_code_spec_ftn_fix.md --
originally sourced from FTN Fantasy's real per-play charting (nfl_data_py.import_ftn_data),
which turned out to be a real, free, CC-BY-SA-licensed public dataset (verified: FTN Data
donated a charting subset for open publication via nflverse's GitHub Releases, no API key
or subscription required -- this was NOT fabricated data and NOT the paid FTN Fantasy
product, but the user asked for a second, independent free source as well). Now sourced
from nflverse's own official PARTICIPATION data instead: `number_of_pass_rushers` and
`defenders_in_box`, both already merged into every pbp pull this project makes by
nfl_data_py.import_pbp_data's own default `include_participation=True` (verified live:
these columns pull from the SAME nflverse-data GitHub Releases family the pbp/schedules
data already used everywhere in this project comes from -- no separate fetch call needed,
0 nulls on real 2025 pass/run plays). Blitz Rate = share of real pass plays faced with 5+
pass rushers (the standard definition of a blitz -- a named, documented threshold, not a
magic number); Avg Box Count = mean defenders_in_box across real SCRIMMAGE plays only (pass
or run) -- caught live while verifying this: defenders_in_box is 0, not null, on kickoffs/
punts/extra points/kneels/spikes (no real front-seven alignment to chart there), so
averaging over every "defensive" row including special teams plays would silently deflate
every team's real number (Arizona 2023: 4.96 unrestricted vs. the real 6.11 restricted to
actual snaps). Deliberately informational/contextual, NOT part of the weighted Z-score
composite on Front
Seven & D-Line Index -- a higher or lower blitz rate isn't inherently "better," it's a
scheme choice, unlike Sack/TFL/QB-Hit Rate which are unambiguously "higher is better."
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES

# Individual credit columns, in the order NFL/PFR convention charts them (a play can have
# 0, 1, or 2 credited players -- e.g. a split sack, or two defenders sharing hit/TFL/PBU
# credit on the same play).
_SACK_COLS = ["sack_player_id"]
_HALF_SACK_COLS = ["half_sack_1_player_id", "half_sack_2_player_id"]
_QB_HIT_COLS = ["qb_hit_1_player_id", "qb_hit_2_player_id"]
_TFL_COLS = ["tackle_for_loss_1_player_id", "tackle_for_loss_2_player_id"]
_INT_COLS = ["interception_player_id"]
_PBU_COLS = ["pass_defense_1_player_id", "pass_defense_2_player_id"]


def _credit_counts(df: pd.DataFrame, cols: list[str], weight: float = 1.0) -> pd.Series:
    """
    Pure helper, no network. Sums per-(team, season, player) credit across one or more
    charting columns, each contributing `weight` per real play it's populated on. Shared by
    every compute_player_season_*_stats function below.
    """
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


def _pivot_player_credits(
    long_frames: list[pd.DataFrame], value_cols: list[str]
) -> pd.DataFrame:
    """
    Pure helper, no network. Pivots a list of (team, season, player, stat, value) long
    frames into one wide per-player frame, explicitly SUMMING contributions that share a
    stat name (e.g. full + half sacks both label "Sacks") -- a naive sequential merge would
    silently collide same-named columns into _x/_y suffixes instead of adding them (a real
    bug this project's own test suite caught before it ever touched real data).
    """
    if not long_frames:
        return pd.DataFrame(columns=["team", "Season", "player_id", *value_cols])

    long_df = pd.concat(long_frames, ignore_index=True)
    combined = long_df.pivot_table(
        index=["team", "Season", "player_id"], columns="stat", values="value",
        aggfunc="sum", fill_value=0.0,
    ).reset_index()
    combined.columns.name = None
    for col in value_cols:
        if col not in combined.columns:
            combined[col] = 0.0
    return combined


def _finalize_player_frame(combined: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
    """Pure helper: team-name mapping + column selection, shared by every player function."""
    unmapped = sorted(set(combined["team"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    combined = combined.copy()
    combined["Team"] = combined["team"].map(TEAM_NAMES)
    combined = combined.rename(columns={"player_id": "Player ID"})
    return combined[["Player ID", "Season", "Team", *value_cols]]


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

    sacks = _credit_counts(reg, _SACK_COLS, weight=1.0)
    half_sacks = _credit_counts(reg, _HALF_SACK_COLS, weight=0.5)
    qb_hits = _credit_counts(reg, _QB_HIT_COLS, weight=1.0)
    tfls = _credit_counts(reg, _TFL_COLS, weight=1.0)

    long_frames = []
    for series, label in [(sacks, "Sacks"), (half_sacks, "Sacks"),
                           (qb_hits, "QB Hits"), (tfls, "TFL")]:
        if len(series) == 0:
            continue
        f = series.rename("value").reset_index()
        f = f.rename(columns={"defteam": "team", "season": "Season"})
        f["stat"] = label
        long_frames.append(f)

    value_cols = ["Sacks", "TFL", "QB Hits"]
    combined = _pivot_player_credits(long_frames, value_cols)
    if len(combined) == 0:
        return pd.DataFrame(columns=["Player ID", "Season", "Team", *value_cols])
    return _finalize_player_frame(combined, value_cols)


def compute_team_season_secondary_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. One row per TEAM per season -- team-level, same pattern as
    compute_team_season_front7_stats.

    Columns: Team | Season | INT Rate | PBU Rate
    """
    reg = pbp[pbp["season_type"] == "REG"]
    reg = reg[reg["defteam"].notna()]

    pass_faced = reg[reg["pass_attempt"] == 1]
    pass_denom = pass_faced.groupby(["defteam", "season"]).size().rename("pass_plays_faced")

    ints = reg.groupby(["defteam", "season"])["interception"].sum().rename("ints")
    # PBU isn't a single 0/1 flag column like sack/qb_hit/interception -- a play counts as a
    # pass breakup if EITHER pass_defense credit column is populated (a play only ever has
    # PBU credit, never both an interception AND a PBU on the same play in this schema, but
    # this counts the PLAY once regardless -- individual player counting below is separate).
    is_pbu = reg["pass_defense_1_player_id"].notna() | reg["pass_defense_2_player_id"].notna()
    pbus = reg[is_pbu].groupby(["defteam", "season"]).size().rename("pbus")

    out = pass_denom.to_frame().join(ints).join(pbus).reset_index()
    out = out.rename(columns={"defteam": "team", "season": "Season"})
    out["ints"] = out["ints"].fillna(0)
    out["pbus"] = out["pbus"].fillna(0)

    out["INT Rate"] = out["ints"] / out["pass_plays_faced"]
    out["PBU Rate"] = out["pbus"] / out["pass_plays_faced"]

    unmapped = sorted(set(out["team"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team"].map(TEAM_NAMES)

    out = out.sort_values(["Team", "Season"]).reset_index(drop=True)
    return out[["Team", "Season", "INT Rate", "PBU Rate"]]


def compute_player_season_secondary_stats(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real per-player season totals -- Secondary Index's
    individual layer, same pattern as compute_player_season_front7_stats. Each of the (up
    to 2) players on a shared pass-breakup play gets full PBU credit (matching how QB
    hits/TFL are already credited above), not split like a half-sack.

    Columns: Player ID | Season | Team | INT | PBU
    """
    reg = pbp[pbp["season_type"] == "REG"]
    reg = reg[reg["defteam"].notna()]

    ints = _credit_counts(reg, _INT_COLS, weight=1.0)
    pbus = _credit_counts(reg, _PBU_COLS, weight=1.0)

    long_frames = []
    for series, label in [(ints, "INT"), (pbus, "PBU")]:
        if len(series) == 0:
            continue
        f = series.rename("value").reset_index()
        f = f.rename(columns={"defteam": "team", "season": "Season"})
        f["stat"] = label
        long_frames.append(f)

    value_cols = ["INT", "PBU"]
    combined = _pivot_player_credits(long_frames, value_cols)
    if len(combined) == 0:
        return pd.DataFrame(columns=["Player ID", "Season", "Team", *value_cols])
    return _finalize_player_frame(combined, value_cols)


# Standard definition of a blitz: 5 or more pass rushers. A named, documented, tunable
# threshold (like every other judgment-call constant in this project -- QB's 100-dropback
# minimum, RB's 50-carry minimum), not a magic number buried in a formula.
BLITZ_MIN_PASS_RUSHERS = 5


def compute_team_season_participation_context(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real, per-play scheme-tendency context for Front Seven & D-
    Line Index -- Blitz Rate and Avg Box Count, from nflverse's own official participation
    data (`number_of_pass_rushers` / `defenders_in_box`), already present in `pbp` -- no
    separate fetch or join needed, unlike the FTN-sourced version this replaced (see module
    docstring for the correction history). Deliberately informational (see module
    docstring): neither is a "higher is better" quality signal, so neither feeds the tab's
    weighted Z-score composite.

    Blitz Rate = share of real pass plays faced with BLITZ_MIN_PASS_RUSHERS (5) or more pass
    rushers. Avg Box Count = mean defenders_in_box across all real SCRIMMAGE plays (pass or
    run) -- found live while verifying this against a direct pull: `defenders_in_box` is 0
    (not null) on kickoffs/punts/extra points/field goals/kneels/spikes, since there's no
    real front-seven alignment to chart on those -- Arizona's real 2023 average was 4.96
    including those non-scrimmage 0's dragging it down, vs. 6.11 restricted to real
    pass/run plays (matches real NFL box-count ranges); the unrestricted version would have
    shipped a real accuracy bug, not just a labeling one.

    Columns: Team | Season | Blitz Rate | Avg Box Count
    """
    reg = pbp[pbp["season_type"] == "REG"].copy()
    reg = reg[reg["defteam"].notna()]
    scrimmage = reg[reg["play_type"].isin(["pass", "run"])]

    box_avg = (
        scrimmage.groupby(["defteam", "season"])["defenders_in_box"]
        .mean().rename("Avg Box Count")
    )

    pass_faced = reg[reg["pass_attempt"] == 1].copy()
    pass_faced["blitzed"] = pass_faced["number_of_pass_rushers"] >= BLITZ_MIN_PASS_RUSHERS
    blitz_rate = pass_faced.groupby(["defteam", "season"])["blitzed"].mean().rename("Blitz Rate")

    out = blitz_rate.to_frame().join(box_avg).reset_index()
    out = out.rename(columns={"defteam": "team", "season": "Season"})

    unmapped = sorted(set(out["team"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team"].map(TEAM_NAMES)

    out = out.sort_values(["Team", "Season"]).reset_index(drop=True)
    return out[["Team", "Season", "Blitz Rate", "Avg Box Count"]]


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
