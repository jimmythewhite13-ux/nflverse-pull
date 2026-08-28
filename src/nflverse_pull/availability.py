"""
Injury History and Schedule Density -- the two dimensions of the originally-envisioned
5-dimension "injury index" that ARE sourceable with public data (see
claude_code_spec_qb_index.md Part E for why ACWR, GPS/load, and wellness surveys are not,
and are deliberately not attempted here). Feeds the workbook's "Availability Index" tab.

Same fetch/pure-transform split as the rest of nflverse_pull.
"""
from __future__ import annotations

import math

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES

# Games listed with either status count toward injury history -- the weekly injury report
# doesn't cleanly separate "injury" from "coach's decision" in all cases (e.g. a healthy
# scratch can also show as a report entry), so don't overstate precision here; this is a
# reasonable proxy for "missed or nearly missed," not a clinical record.
INJURED_STATUSES = ["Out", "Doubtful"]

# Home stadium coordinates (lat, lon), used only to compute real airline-distance travel
# miles between two teams' home markets -- public, unchanging facts, not fabricated data.
# One entry per current team; a team that relocates or a stadium that changes would need
# updating here (same maintenance burden as TEAM_NAMES itself).
STADIUM_COORDS: dict[str, tuple[float, float]] = {
    "ARI": (33.5276, -112.2626), "ATL": (33.7554, -84.4008), "BAL": (39.2780, -76.6227),
    "BUF": (42.7738, -78.7870), "CAR": (35.2258, -80.8528), "CHI": (41.8623, -87.6167),
    "CIN": (39.0954, -84.5160), "CLE": (41.5061, -81.6995), "DAL": (32.7473, -97.0945),
    "DEN": (39.7439, -105.0201), "DET": (42.3400, -83.0456), "GB": (44.5013, -88.0622),
    "HOU": (29.6847, -95.4107), "IND": (39.7601, -86.1639), "JAX": (30.3239, -81.6373),
    "KC": (39.0489, -94.4839), "LA": (33.9535, -118.3392), "LAC": (33.9535, -118.3392),
    "LV": (36.0909, -115.1833), "MIA": (25.9580, -80.2389), "MIN": (44.9736, -93.2575),
    "NE": (42.0909, -71.2643), "NO": (29.9511, -90.0812), "NYG": (40.8135, -74.0745),
    "NYJ": (40.8135, -74.0745), "PHI": (39.9008, -75.1675), "PIT": (40.4468, -80.0158),
    "SEA": (47.5952, -122.3316), "SF": (37.4032, -121.9698), "TB": (27.9759, -82.5033),
    "TEN": (36.1665, -86.7713), "WAS": (38.9078, -76.8645),
}


def fetch_injuries(years: list[int]) -> pd.DataFrame:
    """Network call -- pulls weekly injury reports from nflverse for the given seasons."""
    import nfl_data_py as nfl  # imported lazily so tests don't require it installed

    return nfl.import_injuries(years)


def fetch_schedules_with_dates(years: list[int]) -> pd.DataFrame:
    """
    Network call -- pulls the full schedule including gameday/home_rest/away_rest, which
    pull.fetch_schedules() doesn't select (it only needs the score columns for PPG).
    """
    import nfl_data_py as nfl

    return nfl.import_schedules(years)


def compute_player_injury_history(injuries: pd.DataFrame, player_ids: set[str]) -> pd.DataFrame:
    """
    Pure function, no network. For each of `player_ids` (restrict to the QBs we actually
    score, per the spec -- extending to the full roster is a bigger lift, noted as a future
    step, not attempted here): count of weeks listed Out or Doubtful across every season in
    `injuries`, plus the most recent (season, week) of any 'Out' designation specifically,
    for recency. A player with no matching injury rows gets a count of 0 and blank recency
    (never Out), not an omitted row.
    """
    inj = injuries[injuries["gsis_id"].isin(player_ids)]
    flagged = inj[inj["report_status"].isin(INJURED_STATUSES)]
    counts = flagged.groupby("gsis_id").size()

    out_only = inj[inj["report_status"] == "Out"].sort_values(
        ["season", "week"], ascending=[False, False]
    )
    most_recent = out_only.groupby("gsis_id").first()[["season", "week"]]

    out = pd.DataFrame({"Player ID": sorted(player_ids)})
    out["Out/Doubtful Weeks (3-Yr)"] = out["Player ID"].map(counts).fillna(0).astype(int)
    out["Most Recent Out Season"] = out["Player ID"].map(most_recent["season"])
    out["Most Recent Out Week"] = out["Player ID"].map(most_recent["week"])
    return out


def _haversine_miles(coord_a: tuple[float, float], coord_b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon) points, in miles."""
    lat1, lon1 = coord_a
    lat2, lon2 = coord_b
    radius_miles = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_miles * math.asin(math.sqrt(a))


def compute_team_game_log(sched: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. One row per team per game they played (both home and away
    games), with the game date and miles traveled for that specific game (0 for a home
    game; real airline distance from the team's home stadium to the opponent's for an away
    game). This is the raw material 'Availability Index' Section 2's rolling COUNTIFS/
    SUMIFS-over-a-date-window formulas operate on -- it deliberately does NOT pre-compute
    "games in trailing N days" itself, since that's only meaningful as of a specific date
    (a given week's matchup), which belongs in the workbook, not baked into this pull.
    """
    reg = sched[sched["game_type"] == "REG"].copy()
    reg["gameday"] = pd.to_datetime(reg["gameday"])

    home = reg[["season", "week", "gameday", "home_team", "away_team"]].rename(
        columns={"home_team": "team_abbr", "away_team": "opponent_abbr"}
    )
    home["miles_traveled"] = 0.0

    away = reg[["season", "week", "gameday", "away_team", "home_team"]].rename(
        columns={"away_team": "team_abbr", "home_team": "opponent_abbr"}
    )
    away["miles_traveled"] = [
        _haversine_miles(STADIUM_COORDS[t], STADIUM_COORDS[o])
        if t in STADIUM_COORDS and o in STADIUM_COORDS
        else None
        for t, o in zip(away["team_abbr"], away["opponent_abbr"], strict=True)
    ]

    out = pd.concat([home, away], ignore_index=True)

    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team_abbr"].map(TEAM_NAMES)

    out = out.rename(columns={
        "season": "Season", "week": "Week", "gameday": "Game Date",
        "miles_traveled": "Miles Traveled (This Game)",
    })
    out = out.sort_values(["Team", "Game Date"]).reset_index(drop=True)
    return out[["Team", "Season", "Week", "Game Date", "Miles Traveled (This Game)"]]
