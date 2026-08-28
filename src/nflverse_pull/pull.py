"""
Pulls NFL schedule/results data from nflverse and reshapes it into the exact
format the 'YoY Baseline Engine' tab (Section 1) of the NFL Prediction Model
workbook expects: Team | Season | Off PPG | Def PPG.

Split into a network-touching fetch step and a pure transform step so the
transform logic can be unit tested without internet access (see tests/).
"""
from __future__ import annotations

import pandas as pd

# nflverse uses 2/3-letter team abbreviations -- map to the full names used in the workbook
TEAM_NAMES: dict[str, str] = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers",
    "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}

REQUIRED_SCHED_COLS = ["season", "game_type", "home_team", "away_team", "home_score", "away_score"]


def fetch_schedules(years: list[int]) -> pd.DataFrame:
    """Network call -- pulls raw schedule/results data from nflverse for the given seasons."""
    import nfl_data_py as nfl  # imported lazily so tests don't require it installed

    return nfl.import_schedules(years)


def transform_to_team_season(sched: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Takes a raw nflverse schedules DataFrame and returns
    one row per team per season with Off PPG / Def PPG, in the workbook's expected shape.
    """
    missing = [c for c in REQUIRED_SCHED_COLS if c not in sched.columns]
    if missing:
        raise ValueError(f"Input schedule data is missing expected columns: {missing}")

    reg = sched[sched["game_type"] == "REG"].dropna(subset=["home_score", "away_score"])

    home = reg[["season", "home_team", "home_score", "away_score"]].rename(
        columns={"home_team": "team_abbr", "home_score": "pts_scored", "away_score": "pts_allowed"}
    )
    away = reg[["season", "away_team", "away_score", "home_score"]].rename(
        columns={"away_team": "team_abbr", "away_score": "pts_scored", "home_score": "pts_allowed"}
    )
    long_df = pd.concat([home, away], ignore_index=True)

    team_season = (
        long_df.groupby(["team_abbr", "season"])
        .agg(off_ppg=("pts_scored", "mean"), def_ppg=("pts_allowed", "mean"))
        .reset_index()
    )

    unmapped = sorted(set(team_season["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")

    team_season["Team"] = team_season["team_abbr"].map(TEAM_NAMES)
    team_season["Off PPG"] = team_season["off_ppg"].round(1)
    team_season["Def PPG"] = team_season["def_ppg"].round(1)
    team_season = team_season.rename(columns={"season": "Season"})

    out = team_season[["Team", "Season", "Off PPG", "Def PPG"]].sort_values(["Team", "Season"])
    return out.reset_index(drop=True)


def main(years: list[int] | None = None, output_path: str = "team_season_ppg.csv") -> pd.DataFrame:
    years = years or [2023, 2024, 2025]
    raw = fetch_schedules(years)
    out = transform_to_team_season(raw)
    out.to_csv(output_path, index=False)
    print(out.head(10))
    print(f"\nSaved {len(out)} rows to {output_path}")
    return out


if __name__ == "__main__":
    main()
