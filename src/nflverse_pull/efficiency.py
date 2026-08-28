"""
Replicates the 'Advanced Efficiency Metrics' tab of the NFL Prediction Model workbook with
real data, replacing its SAMPLE PLACEHOLDER Section 1.

EPA/play, Success Rate, and NY/A (Net Yards per Attempt) are play-level stats -- not
derivable from the schedules data used by pull.py -- so this pulls nflverse's play-by-play
(pbp) release instead. Mirrors the workbook's three sections:
  Section 1: raw per-team offense/defense-allowed metrics (compute_raw_efficiency)
  Section 2: league average + population std-dev per metric (compute_league_stats)
  Section 3: per-team Z-scores (defense sign-flipped so higher Z is always better) combined
             into a single Weighted Efficiency Adjustment via the weights on the workbook's
             'Model Assumptions' tab, C24:C29 (compute_weighted_efficiency)

Split into a network-touching fetch step and pure transform steps, same pattern as pull.py.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES

# 'Model Assumptions' C24:C29 -- pts added to Net Power Rating per 1 std. dev. from league
# average. PROE (column I on the sheet) is tracked for context only and never weighted,
# per the notes in Model Assumptions A31: it measures play-calling tendency, not whether
# that tendency is working, so it has no clear "higher is better" direction to score.
EFFICIENCY_WEIGHTS = {
    "epa_off": 0.5,
    "epa_def": 0.5,
    "success_off": 0.4,
    "success_def": 0.4,
    "nya_off": 0.3,
    "nya_def": 0.3,
}

RAW_METRIC_COLS = ["epa_off", "epa_def", "success_off", "success_def", "nya_off", "nya_def"]


def fetch_pbp(years: list[int]) -> pd.DataFrame:
    """Network call -- pulls raw play-by-play data from nflverse for the given seasons."""
    import nfl_data_py as nfl  # imported lazily so tests don't require it installed

    return nfl.import_pbp_data(years, downcast=True)


def compute_raw_efficiency(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Section 1 equivalent: one row per team (regular season only,
    all seasons present in `pbp` pooled together) with EPA/play, Success Rate, and NY/A for
    offense and defense-allowed, plus PROE.
    """
    reg = pbp[pbp["season_type"] == "REG"]

    # EPA/play and Success Rate use the standard "meaningful snap" filter: pass or run plays
    # only, which excludes kneels, spikes, kickoffs, punts, FG/XP attempts, and no-plays.
    plays = reg[reg["play_type"].isin(["pass", "run"])]

    off = plays.groupby("posteam").agg(epa_off=("epa", "mean"), success_off=("success", "mean"))
    defn = plays.groupby("defteam").agg(epa_def=("epa", "mean"), success_def=("success", "mean"))

    # NY/A = (yards gained on pass attempts + yards lost on sacks) / (attempts + sacks).
    # Sacks are pass plays but nflverse doesn't count them as pass_attempts, and their
    # yardage lives in yards_gained (already negative), not passing_yards (attempts only).
    attempts = reg[reg["pass_attempt"] == 1]
    sacks = reg[reg["sack"] == 1]

    def _nya(group_col: str) -> pd.Series:
        att_yards = attempts.groupby(group_col)["passing_yards"].sum()
        att_count = attempts.groupby(group_col).size()
        sack_yards = sacks.groupby(group_col)["yards_gained"].sum()
        sack_count = sacks.groupby(group_col).size()
        denom = att_count.add(sack_count, fill_value=0)
        numer = att_yards.add(sack_yards, fill_value=0)
        return numer / denom

    nya_off = _nya("posteam").rename("nya_off")
    nya_def = _nya("defteam").rename("nya_def")

    # PROE (Pass Rate Over Expected): mean pass_oe across the same pass/run snaps, converted
    # from nflverse's percentage-point scale (-51.1) to the workbook's fraction scale (-0.511).
    proe = plays.groupby("posteam")["pass_oe"].mean() / 100

    out = (
        off.join(defn, how="outer")
        .join(nya_off, how="outer")
        .join(nya_def, how="outer")
        .join(proe.rename("proe"), how="outer")
    )
    out.index.name = "team_abbr"
    out = out.reset_index()

    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")

    out["Team"] = out["team_abbr"].map(TEAM_NAMES)
    out = out.sort_values("Team").reset_index(drop=True)
    return out[["Team", *RAW_METRIC_COLS, "proe"]]


def compute_league_stats(raw: pd.DataFrame) -> pd.DataFrame:
    """Pure function. Section 2 equivalent: league average and population std-dev per metric."""
    return pd.DataFrame(
        {"mean": raw[RAW_METRIC_COLS].mean(), "std": raw[RAW_METRIC_COLS].std(ddof=0)}
    )


def compute_weighted_efficiency(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function. Section 3 equivalent: per-team Z-scores (defense/allowed metrics
    sign-flipped so a higher Z always means better) combined into a single Weighted
    Efficiency Adjustment via EFFICIENCY_WEIGHTS.
    """
    stats = compute_league_stats(raw)

    z = pd.DataFrame({"Team": raw["Team"]})
    z["epa_off_z"] = (raw["epa_off"] - stats.loc["epa_off", "mean"]) / stats.loc["epa_off", "std"]
    z["epa_def_z"] = (stats.loc["epa_def", "mean"] - raw["epa_def"]) / stats.loc["epa_def", "std"]
    z["success_off_z"] = (
        raw["success_off"] - stats.loc["success_off", "mean"]
    ) / stats.loc["success_off", "std"]
    z["success_def_z"] = (
        stats.loc["success_def", "mean"] - raw["success_def"]
    ) / stats.loc["success_def", "std"]
    z["nya_off_z"] = (raw["nya_off"] - stats.loc["nya_off", "mean"]) / stats.loc["nya_off", "std"]
    z["nya_def_z"] = (stats.loc["nya_def", "mean"] - raw["nya_def"]) / stats.loc["nya_def", "std"]

    z["Weighted Efficiency Adjustment"] = (
        z["epa_off_z"] * EFFICIENCY_WEIGHTS["epa_off"]
        + z["epa_def_z"] * EFFICIENCY_WEIGHTS["epa_def"]
        + z["success_off_z"] * EFFICIENCY_WEIGHTS["success_off"]
        + z["success_def_z"] * EFFICIENCY_WEIGHTS["success_def"]
        + z["nya_off_z"] * EFFICIENCY_WEIGHTS["nya_off"]
        + z["nya_def_z"] * EFFICIENCY_WEIGHTS["nya_def"]
    )
    z["PROE"] = raw["proe"]
    return z


def main(years: list[int] | None = None, output_path: str = "team_efficiency.csv") -> pd.DataFrame:
    years = years or [2023, 2024, 2025]
    pbp = fetch_pbp(years)
    raw = compute_raw_efficiency(pbp)
    out = compute_weighted_efficiency(raw)
    out.to_csv(output_path, index=False)
    print(out.head(10))
    print(f"\nSaved {len(out)} rows to {output_path}")
    return out


if __name__ == "__main__":
    main()
