"""
Real full 18-week season schedule assembly -- claude_code_spec_full_season_matchups.md.
Feeds "Season Matchups" (one long-format row per real game across the whole season,
replacing the old hardcoded 16-game Week 1 list).

Verified live before building this: nflverse's own schedules ALREADY carry real, computed
home_rest/away_rest per game (0 nulls) and a real div_game flag (0 nulls) -- neither needs
to be re-derived from scratch here; this module reuses them directly rather than
recomputing a parallel version that could silently drift from nflverse's own real dates.
Real 2026 check: 272 REG games, 18 weeks, every one of the 32 teams plays exactly 17 real
games (one real bye apiece) -- rest values for week 2+ genuinely vary (4-14 real days), not
a flat placeholder.

The one real gap: 'roof' (dome/outdoors/closed/open) is null on ~43 of 272 2026 rows --
every one of them a real dome-capable or retractable-roof stadium (Reliant/NRG, Lucas Oil,
Mercedes-Benz, State Farm, etc.) whose specific game-day roof state genuinely isn't knowable
this far in advance. Filled with that TEAM's own real historical mode (most common real roof
status across 2023-2025 real games at that stadium) rather than a blind "outdoors" default,
which would misclassify a dome stadium.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.availability import STADIUM_COORDS, _haversine_miles
from nflverse_pull.pull import TEAM_NAMES

REQUIRED_COLS = [
    "season", "week", "game_type", "gameday", "away_team", "home_team", "roof", "stadium",
    "div_game", "away_rest", "home_rest",
]


def compute_roof_fallback(sched_multi_year: pd.DataFrame) -> dict[str, str]:
    """
    Pure function, no network. Real per-team most-common historical roof status (mode
    across every real non-null 'roof' row at that team's home stadium) -- used to fill a
    future season's null roof cells with a real, defensible fallback instead of a blind
    default.
    """
    reg = sched_multi_year[sched_multi_year["game_type"] == "REG"].dropna(subset=["roof"])
    if reg.empty:
        return {}
    return (
        reg.groupby("home_team")["roof"]
        .agg(lambda s: s.value_counts().idxmax())
        .to_dict()
    )


def compute_season_schedule(
    sched_current: pd.DataFrame, season: int, roof_fallback: dict[str, str]
) -> pd.DataFrame:
    """
    Pure function, no network. Real full REG-season schedule for `season` -- one row per
    real game, sorted by (Week, Away Team full name) for a stable, deterministic row order
    across rebuilds. Real away-team travel miles via the same STADIUM_COORDS/haversine
    calculation availability.py's own team game log already uses.

    Output: Week | Date | Away Team | Home Team | Stadium | Dome (bool) | Divisional (bool)
    | Home Rest (days) | Away Rest (days) | Away Travel (miles)
    """
    missing = [c for c in REQUIRED_COLS if c not in sched_current.columns]
    if missing:
        raise ValueError(f"Input schedule data is missing expected columns: {missing}")

    reg = sched_current[
        (sched_current["season"] == season) & (sched_current["game_type"] == "REG")
    ].copy()

    reg["roof_filled"] = reg["roof"].fillna(reg["home_team"].map(roof_fallback))
    reg["roof_filled"] = reg["roof_filled"].fillna("outdoors")
    reg["dome"] = reg["roof_filled"].isin(["dome", "closed"])

    unmapped = sorted(
        (set(reg["away_team"]) | set(reg["home_team"])) - set(TEAM_NAMES)
    )
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")

    reg["Away Team"] = reg["away_team"].map(TEAM_NAMES)
    reg["Home Team"] = reg["home_team"].map(TEAM_NAMES)
    reg["travel_miles"] = [
        _haversine_miles(STADIUM_COORDS[a], STADIUM_COORDS[h])
        if a in STADIUM_COORDS and h in STADIUM_COORDS else None
        for a, h in zip(reg["away_team"], reg["home_team"], strict=True)
    ]

    reg = reg.rename(columns={
        "week": "Week", "gameday": "Date", "stadium": "Stadium",
        "div_game": "Divisional", "home_rest": "Home Rest", "away_rest": "Away Rest",
        "travel_miles": "Away Travel",
    })
    reg["Divisional"] = reg["Divisional"].astype(bool)
    reg = reg.sort_values(["Week", "Away Team"]).reset_index(drop=True)
    return reg[[
        "Week", "Date", "Away Team", "Home Team", "Stadium", "dome", "Divisional",
        "Home Rest", "Away Rest", "Away Travel",
    ]].rename(columns={"dome": "Dome"})
