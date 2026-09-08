"""
Step 6: resolves real per-game Z/AA context terms (Rest Effect, Division Adj, and a
real-but-partial Weather Adj) for an arbitrary real historical game, directly from nflverse's
own real schedule row -- no re-derivation needed, since nflverse already carries these as real
per-game fields (home_rest/away_rest, div_game, roof/temp/wind).

Wires real values into core_formula_simple_terms.py's already-Excel-proven rest_effect() /
division_adj() / weather_adj() -- no new scoring arithmetic here, only real historical data
resolution, per this project's "arithmetic only, not data sourcing" module boundary.

Weather Adj is honestly PARTIAL for historical targets: nflverse's real schedule data carries
real temp/wind/roof for every season, but has no snow_flag, precip_flag, or humidity field at
all -- those are the live pipeline's own manually-entered current-week inputs, not archived
anywhere real and free. `resolve_weather_adj_for_game` computes the wind/cold-threshold
portion only from real data and explicitly documents the excluded terms rather than defaulting
them to "no precipitation" (which would misrepresent real historical conditions in an outdoor
game where it may genuinely have rained or snowed). It also returns None (not a fabricated
0.0) for a real outdoor/open-roof game where nflverse's own temp/wind happen to be null -- a
real, if smaller, data gap (about 21-25% of outdoor games in 2021-2023) that must not be
papered over.
"""
from __future__ import annotations

import pandas as pd

from prediction_audit.engine.core_formula_simple_terms import (
    RestEffectConstants,
    WeatherAdjConstants,
    division_adj,
    rest_effect,
    road_fatigue_adj,
)

# Real nflverse `roof` values meaning no outdoor weather exposure (matches the live pipeline's
# own "Dome" flag semantics for Weather Adj's own first blank-guard branch).
_NO_WEATHER_EXPOSURE_ROOFS = frozenset({"dome", "closed"})


def resolve_rest_effect_for_game(game_row: pd.Series, constants: RestEffectConstants) -> float:
    """game_row: one real row from nflverse's own schedule data (real home_rest/away_rest,
    already computed by nflverse itself -- real days since each team's last game)."""
    return rest_effect(float(game_row["home_rest"]), float(game_row["away_rest"]), constants)


def resolve_division_adj_for_game(game_row: pd.Series, division_adj_const: float) -> float:
    """game_row: real nflverse div_game (int 0/1) mapped to the engine's own "Y"/"N" convention."""
    is_divisional = "Y" if bool(game_row["div_game"]) else "N"
    return division_adj(is_divisional, division_adj_const)


def resolve_consecutive_road_games(
    sched: pd.DataFrame, target_season: int, target_week: int, team: str,
) -> int:
    """Real count of consecutive real AWAY games this team played immediately before
    target_week (a bye week or a real HOME game resets the count to 0) -- computed directly
    from nflverse's own real schedule, not sourced from the not-yet-ported Availability Index
    tab this term was originally scoped as a given input from. `team` is nflverse's own real
    abbreviation (not the project's full-name convention -- schedules' own home_team/away_team
    columns are abbreviations)."""
    reg = sched[
        (sched["season"] == target_season) & (sched["game_type"] == "REG")
        & (sched["week"] < target_week)
        & ((sched["home_team"] == team) | (sched["away_team"] == team))
    ].sort_values("week")

    count = 0
    for _, row in reg.iloc[::-1].iterrows():
        if row["away_team"] == team:
            count += 1
        else:
            break
    return count


def resolve_road_fatigue_adj_for_game(
    sched: pd.DataFrame, target_season: int, target_week: int, team: str,
    threshold: float, penalty: float,
) -> float:
    """Real Road Fatigue Adj -- wires resolve_consecutive_road_games()'s own real count into
    the already-Excel-proven road_fatigue_adj()."""
    consecutive = resolve_consecutive_road_games(sched, target_season, target_week, team)
    return road_fatigue_adj(consecutive, threshold, penalty)


def resolve_weather_adj_for_game(
    game_row: pd.Series, constants: WeatherAdjConstants,
) -> float | None:
    """
    Real but partial: only the dome/wind/cold-threshold terms are computed from real
    historical data (nflverse's own roof/temp/wind). snow_flag/precip_flag/humidity are NOT
    available historically from this source and are excluded, not defaulted to "none" --
    total real weather impact for a genuinely rainy/snowy/humid game will be UNDERSTATED, and
    callers must not treat this as the full real Weather Adj term. Returns None (never a
    fabricated 0.0) when the target game is real outdoor/open-roof but nflverse's own real
    temp/wind happen to be null for it.
    """
    roof = game_row.get("roof")
    if roof in _NO_WEATHER_EXPOSURE_ROOFS:
        return 0.0

    temp, wind = game_row.get("temp"), game_row.get("wind")
    if pd.isna(temp) or pd.isna(wind):
        return None

    total = 0.0
    if wind > constants.wind_threshold:
        total += constants.wind_adj
    if temp < constants.cold_threshold:
        total += constants.cold_adj
    return total
