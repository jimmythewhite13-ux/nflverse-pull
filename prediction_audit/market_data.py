"""
Step 5 of the NFL Model v35 Validation/Audit master spec: real historical/current market
(betting-line) data.

For most of this project's life, Step 5 was documented as **blocked**: the workbook has only
ever used manual, current-week sportsbook entry, with no archive of real historical opening/
closing lines with real timestamps. Per the spec's own "do not fabricate historical betting
lines" principle, that gap was never invented around.

**Real unblock found and verified this session**: `nfl_data_py.import_schedules()` (already a
project dependency -- see `src/nflverse_pull/pull.py`'s own `fetch_schedules()`, which wraps
the exact same call) pulls `http://www.habitatring.com/games.csv` -- the standard, free,
publicly-documented historical NFL schedule/results/odds dataset maintained by the nflverse
community (originally Lee Sharpe's `nfldata` repo), used throughout the public NFL-analytics
ecosystem. Verified live in this session:

- `spread_line` / `total_line`: 0% null for every regular-season game, every season 1999-2025.
- `away_moneyline` / `home_moneyline`: 0% null from 2010 onward (spotty before, as expected --
  moneyline data collection was less consistent industry-wide in the 2000s).
- The 2026 season (in progress) already has real lines populated for its near-term weeks, with
  future weeks correctly null (lines genuinely don't exist yet -- not a data gap).

**What this DOES unblock**: a single real, verified, sourced line per game (spread/total/
moneyline), usable as a real market baseline for backtesting model output against (Steps 6-9),
and as a real `market_data_status='VERIFIED'` `line_stage='prediction_time'` (or `'closing'`,
once re-fetched close to kickoff) row in the `market_lines` table -- replacing the prior
MISSING default with real data for the first time.

**What this does NOT unblock**: true timestamped open-to-close CLV movement. This dataset
carries one line per game (understood, per its real public documentation and community usage,
to represent the closing number), not a full timestamped bet-placement-to-close history. Real
CLV tracking (the `v_clv` view) still needs either a paid odds API with timestamped snapshots,
or -- the path this module enables for the first time -- **forward-only collection starting
now**: capture a real `'prediction_time'` line when a prediction is made, and a real
`'closing'` line via a later re-fetch close to kickoff, for every future game from here on.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES, fetch_schedules

REAL_SOURCE_NAME = "habitatring.com/games.csv (via nfl_data_py import_schedules)"


@dataclass
class RealMarketLine:
    week: int
    away_team: str  # full name, matching this project's `games` table convention
    home_team: str
    spread_line: float | None    # home-team spread, real
    total_line: float | None      # real
    away_moneyline: float | None  # real
    home_moneyline: float | None  # real


def fetch_real_market_lines(season: int) -> list[RealMarketLine]:
    """Network call -- pulls the real schedule+odds data, then applies the pure transform
    below. Split this way so the transform logic can be unit tested without internet access
    (same convention as `season_schedule.py` / `pull.py`'s own fetch/transform split)."""
    sched = fetch_schedules([season])
    return transform_schedule_to_market_lines(sched)


def transform_schedule_to_market_lines(sched: pd.DataFrame) -> list[RealMarketLine]:
    """
    Pure function, no network. Takes a raw nflverse schedules DataFrame (as returned by
    `fetch_schedules`) and returns one RealMarketLine per real regular-season game, with team
    abbreviations mapped to this project's own full-name convention (reusing TEAM_NAMES, the
    same real mapping `season_schedule.py` already uses to build the Excel schedule -- not a
    separately hand-typed mapping). Lines that are genuinely not yet posted (future weeks)
    come through as None fields -- never fabricated.
    """
    reg = sched[sched["game_type"] == "REG"].copy()

    unmapped = (set(reg["away_team"]) | set(reg["home_team"])) - set(TEAM_NAMES)
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")

    lines = []
    for _, row in reg.iterrows():
        lines.append(RealMarketLine(
            week=int(row["week"]),
            away_team=TEAM_NAMES[row["away_team"]],
            home_team=TEAM_NAMES[row["home_team"]],
            spread_line=_none_if_nan(row.get("spread_line")),
            total_line=_none_if_nan(row.get("total_line")),
            away_moneyline=_none_if_nan(row.get("away_moneyline")),
            home_moneyline=_none_if_nan(row.get("home_moneyline")),
        ))
    return lines


def _none_if_nan(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
