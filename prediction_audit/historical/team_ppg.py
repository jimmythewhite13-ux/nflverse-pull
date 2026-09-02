"""
Step 6's own historical data-resolution layer: real per-team PPG (Off/Def), for any real past
season, with an optional real "as-of" week cutoff for partial-season (current-season-so-far)
aggregation. Extends `nflverse_pull.pull.transform_to_team_season()` -- already used to build
YoY Baseline Engine's own real Section 1 data for the live 2026 pipeline -- with week-awareness,
so the exact same real logic can resolve a historical walk-forward target's real Y1/Y2/Y3 (full
prior seasons) and real current-season-so-far inputs, not just "the current live season."

Real no-future-information guard: `through_week`, when given, restricts the real games used to
those with `week < through_week` within `season` -- never `<=`, so a walk-forward prediction
for week W never sees week W's own (or a later week's) real result. This is the concrete
mechanism enforcing the master spec's own "do not use future information" principle for this
piece of the engine.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import REQUIRED_SCHED_COLS, TEAM_NAMES


def team_season_ppg(
    sched: pd.DataFrame, season: int, through_week: int | None = None,
) -> pd.DataFrame:
    """
    Pure function, no network. Real per-team Off/Def PPG for one real season, optionally
    restricted to weeks strictly before `through_week`. Returns one row per team with columns
    Team / Off PPG / Def PPG / Games Played -- a team with zero real qualifying games in this
    slice is simply absent (no fabricated 0-PPG row).
    """
    missing = [c for c in REQUIRED_SCHED_COLS if c not in sched.columns]
    if missing:
        raise ValueError(f"Input schedule data is missing expected columns: {missing}")

    reg = sched[
        (sched["game_type"] == "REG") & (sched["season"] == season)
    ].dropna(subset=["home_score", "away_score"])
    if through_week is not None:
        reg = reg[reg["week"] < through_week]

    home = reg[["home_team", "home_score", "away_score"]].rename(columns={
        "home_team": "team_abbr", "home_score": "pts_scored", "away_score": "pts_allowed",
    })
    away = reg[["away_team", "away_score", "home_score"]].rename(columns={
        "away_team": "team_abbr", "away_score": "pts_scored", "home_score": "pts_allowed",
    })
    long_df = pd.concat([home, away], ignore_index=True)

    if long_df.empty:
        return pd.DataFrame(columns=["Team", "Off PPG", "Def PPG", "Games Played"])

    team_stats = (
        long_df.groupby("team_abbr")
        .agg(
            off_ppg=("pts_scored", "mean"), def_ppg=("pts_allowed", "mean"),
            games_played=("pts_scored", "size"),
        )
        .reset_index()
    )

    unmapped = sorted(set(team_stats["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")

    team_stats["Team"] = team_stats["team_abbr"].map(TEAM_NAMES)
    team_stats["Off PPG"] = team_stats["off_ppg"].round(1)
    team_stats["Def PPG"] = team_stats["def_ppg"].round(1)
    out = team_stats[["Team", "Off PPG", "Def PPG", "games_played"]].rename(
        columns={"games_played": "Games Played"},
    ).sort_values("Team")
    return out.reset_index(drop=True)


def league_average_ppg(team_season: pd.DataFrame) -> dict[str, float]:
    """Real league-wide average Off/Def PPG across every team in a team_season_ppg() result --
    the same real AVERAGEIF-across-32-teams logic YoY Baseline Engine's own Section 2 uses."""
    if team_season.empty:
        raise ValueError("Cannot compute a league average from an empty team_season_ppg result")
    return {
        "off": float(team_season["Off PPG"].mean()),
        "def": float(team_season["Def PPG"].mean()),
    }
