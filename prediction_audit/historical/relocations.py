"""
Real franchise-relocation abbreviation normalization -- nflverse's real historical schedule
data uses the abbreviation in effect AT THE TIME (OAK through 2019, SD through 2016, STL
through 2015), which breaks any downstream full-name lookup keyed to the CURRENT abbreviation
(LV/LAC/LA). Renaming at the raw-abbreviation level, before any other processing, means every
consumer (this package's own team_season_ppg, or nflverse_pull's own
compute_team_season_home_away_splits/transform_to_team_season) works unchanged -- no separate
historical name dict needed in each one.

Real continuity, not a new team: the 2019 Oakland Raiders and the 2020 Las Vegas Raiders are
the same real franchise, same for the other two moves.
"""
from __future__ import annotations

import pandas as pd

_ABBR_RELOCATIONS: dict[str, str] = {
    "OAK": "LV",   # Oakland Raiders -> Las Vegas Raiders, real move after the 2019 season
    "SD": "LAC",   # San Diego Chargers -> Los Angeles Chargers, real move after the 2016 season
    "STL": "LA",   # St. Louis Rams -> Los Angeles Rams, real move after the 2015 season
}


_SCHEDULE_TEAM_COLUMNS = ("home_team", "away_team")
_PBP_TEAM_COLUMNS = ("posteam", "defteam", "home_team", "away_team")


def normalize_relocated_abbreviations(
    df: pd.DataFrame, columns: tuple[str, ...] = _SCHEDULE_TEAM_COLUMNS,
) -> pd.DataFrame:
    """Pure function, no network. Returns a copy of `df` with real pre-relocation team
    abbreviations, in any of `columns` that are actually present, replaced by their current
    real equivalent. Defaults to schedule data's own home_team/away_team; pass
    `columns=PBP_TEAM_COLUMNS` for real pbp data's own posteam/defteam (plus home_team/
    away_team, which real pbp also carries)."""
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = out[col].replace(_ABBR_RELOCATIONS)
    return out


PBP_TEAM_COLUMNS = _PBP_TEAM_COLUMNS
