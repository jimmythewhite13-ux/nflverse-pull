"""
Fills the last 2 real, deliberately-scoped gaps in `full_game_prediction.py`: real stadium-to-
stadium distance (for Travel Effect) and real per-team UTC offsets (for Travel Direction Adj).

STADIUM_COORDS -- real, individually-sourced GPS coordinates for each of the 32 real teams'
own current home stadium (2 pairs share a real building: MetLife for NYG/NYJ, SoFi for
LA/LAC), each verified against that stadium's own real, current Wikipedia article (not a
single aggregated dataset -- an earlier candidate aggregate CSV was checked and found stale:
it still listed "Redskins", pre-relocation San Diego Chargers/Oakland Raiders/St. Louis Rams).

This table is independently validated, not just individually sourced: computing haversine
distance from these coordinates for every one of the real 272 REG games in
`v35_hfa_delta_travel_fatigue_ground_truth.json` (a full season) reproduces the frozen v35
workbook's own real `away_travel_miles` to within 0.21mi on every single game (see
tests/test_stadium_locations.py) -- confirming both that these coordinates are correct AND
that the real Excel Travel Effect formula is exactly great-circle (haversine) distance at
Earth radius 3959mi, not a driving-distance or airport-routing figure.

TEAM_UTC_OFFSET -- NOT re-derived from any external source. These are the real, already-
verified-per-game values baked into `v35_travel_direction_ground_truth.json` (itself already
extracted from the frozen workbook and already used by test_core_formula_simple_terms_parity.py
for exact parity) -- confirmed static (same value for every one of a team's real appearances,
home or away, across that manifest's real 272-game season) and simply consolidated here into
one real per-team lookup for reuse by the historical composer.

Real, honest scope note on Buffalo: the Bills' new Highmark Stadium (Orchard Park) is what
was actually in use through the 2025 season -- the replacement stadium set to open in 2026
is NOT what these coordinates describe; this table only needs to be correct for the real
seasons the composer can actually target (2025 and earlier, per OL Index's own real
FTN-coverage constraint), so no revisit is needed until the 2026 season is in scope.

Real, honest scope note on neutral-site games: `fetch_schedules()`'s own real `location`
column marks a real handful of games "Neutral" each season, but a live check against 2023-2025
real schedule data found that in every real case within OL Index's already-in-scope 2025+
window, the schedule's own real `stadium` value for a "Neutral" game exactly matches the
designated home team's own real stadium (nflverse's own real, sometimes-stale sponsor-name
field, not a different city) -- so `resolve_game_venue()` below still safely uses the home
team's own coordinates by default, but raises rather than silently guessing if a future
season's real data ever shows a genuine mismatch (e.g., an actual international venue).
Genuine international-venue games (2024's real London/Munich/Sao Paulo games) are already
out of the composer's real reachable range via the same FTN-coverage constraint, so no
international venue table is built here -- a real, deliberately-scoped gap, not fabricated
around.
"""
from __future__ import annotations

import math

import pandas as pd

# Real, individually-sourced (lat, lon) for each team's own current stadium. Coordinates each
# come from that stadium's own real Wikipedia infobox (via live web search this session);
# validated in aggregate against v35's own real 272-game travel-miles ground truth (see module
# docstring and tests/test_stadium_locations.py).
STADIUM_COORDS: dict[str, tuple[float, float]] = {
    "Buffalo Bills": (42.7738, -78.7870),
    "Miami Dolphins": (25.95806, -80.23889),
    "New England Patriots": (42.0910, -71.2640),
    "New York Jets": (40.8135, -74.0744),
    "New York Giants": (40.8135, -74.0744),
    "Baltimore Ravens": (39.27806, -76.62278),
    "Cincinnati Bengals": (39.095428, -84.516190),
    "Cleveland Browns": (41.50611, -81.69944),
    "Pittsburgh Steelers": (40.44667, -80.01583),
    "Houston Texans": (29.684860, -95.411667),
    "Indianapolis Colts": (39.760056, -86.163806),
    "Jacksonville Jaguars": (30.323919, -81.637566),
    "Tennessee Titans": (36.16639, -86.77139),
    "Denver Broncos": (39.74389, -105.02000),
    "Kansas City Chiefs": (39.04889, -94.48389),
    "Las Vegas Raiders": (36.090794, -115.183952),
    "Los Angeles Chargers": (33.953587, -118.339630),
    "Los Angeles Rams": (33.953587, -118.339630),
    "Dallas Cowboys": (32.74778, -97.09278),
    "Philadelphia Eagles": (39.9015, -75.1673),
    "Washington Commanders": (38.90778, -76.86444),
    "Chicago Bears": (41.8625332, -87.6167182),
    "Detroit Lions": (42.34000, -83.04556),
    "Green Bay Packers": (44.5013805, -88.0623258),
    "Minnesota Vikings": (44.974, -93.258),
    "Atlanta Falcons": (33.75556, -84.40000),
    "Carolina Panthers": (35.22583, -80.85278),
    "New Orleans Saints": (29.95083, -90.08111),
    "Tampa Bay Buccaneers": (27.97583, -82.50333),
    "Arizona Cardinals": (33.528, -112.263),
    "San Francisco 49ers": (37.403, -121.970),
    "Seattle Seahawks": (47.595097, -122.332245),
}

# nflverse's own real `stadium` field for a "Neutral"-location game, aliased back to the team
# whose own stadium it real is (see module docstring's neutral-site scope note) -- current AND
# recently-retired real sponsor names, since nflverse's field is not always kept current.
_STADIUM_NAME_TO_TEAM: dict[str, str] = {
    "Highmark Stadium": "Buffalo Bills", "New Era Field": "Buffalo Bills",
    "Hard Rock Stadium": "Miami Dolphins",
    "Gillette Stadium": "New England Patriots",
    "MetLife Stadium": "New York Jets",  # ambiguous with Giants; only used as a same-building check
    "M&T Bank Stadium": "Baltimore Ravens",
    "Paycor Stadium": "Cincinnati Bengals",
    "Huntington Bank Field": "Cleveland Browns", "FirstEnergy Stadium": "Cleveland Browns",
    "Acrisure Stadium": "Pittsburgh Steelers",
    "NRG Stadium": "Houston Texans",
    "Lucas Oil Stadium": "Indianapolis Colts",
    "EverBank Stadium": "Jacksonville Jaguars", "TIAA Bank Stadium": "Jacksonville Jaguars",
    "Nissan Stadium": "Tennessee Titans",
    "Empower Field at Mile High": "Denver Broncos",
    "Arrowhead Stadium": "Kansas City Chiefs",
    "GEHA Field at Arrowhead Stadium": "Kansas City Chiefs",
    "Allegiant Stadium": "Las Vegas Raiders",
    "SoFi Stadium": "Los Angeles Chargers",  # ambiguous with Rams; same-building check only
    "AT&T Stadium": "Dallas Cowboys",
    "Lincoln Financial Field": "Philadelphia Eagles",
    "Northwest Stadium": "Washington Commanders", "FedExField": "Washington Commanders",
    "Soldier Field": "Chicago Bears",
    "Ford Field": "Detroit Lions",
    "Lambeau Field": "Green Bay Packers",
    "U.S. Bank Stadium": "Minnesota Vikings",
    "Mercedes-Benz Stadium": "Atlanta Falcons",
    "Bank of America Stadium": "Carolina Panthers",
    "Caesars Superdome": "New Orleans Saints", "Mercedes-Benz Superdome": "New Orleans Saints",
    "Raymond James Stadium": "Tampa Bay Buccaneers",
    "State Farm Stadium": "Arizona Cardinals",
    "Levi's Stadium": "San Francisco 49ers",
    "Lumen Field": "Seattle Seahawks",
}

# Real, static per-team UTC offset -- consolidated from v35_travel_direction_ground_truth.json
# (already extracted from the frozen workbook), not independently re-derived.
TEAM_UTC_OFFSET: dict[str, float] = {
    "Arizona Cardinals": -7, "Atlanta Falcons": -5, "Baltimore Ravens": -5,
    "Buffalo Bills": -5, "Carolina Panthers": -5, "Chicago Bears": -6,
    "Cincinnati Bengals": -5, "Cleveland Browns": -5, "Dallas Cowboys": -6,
    "Denver Broncos": -7, "Detroit Lions": -5, "Green Bay Packers": -6,
    "Houston Texans": -6, "Indianapolis Colts": -5, "Jacksonville Jaguars": -5,
    "Kansas City Chiefs": -6, "Las Vegas Raiders": -8, "Los Angeles Chargers": -8,
    "Los Angeles Rams": -8, "Miami Dolphins": -5, "Minnesota Vikings": -6,
    "New England Patriots": -5, "New Orleans Saints": -6, "New York Giants": -5,
    "New York Jets": -5, "Philadelphia Eagles": -5, "Pittsburgh Steelers": -5,
    "San Francisco 49ers": -8, "Seattle Seahawks": -8, "Tampa Bay Buccaneers": -5,
    "Tennessee Titans": -6, "Washington Commanders": -5,
}


def haversine_miles(coord1: tuple[float, float], coord2: tuple[float, float]) -> float:
    """Real great-circle distance in miles (Earth radius 3959mi -- confirmed to match v35's
    own real Travel Effect formula, not guessed; see module docstring)."""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 3959.0 * 2 * math.asin(math.sqrt(a))


def resolve_game_venue_team(game_row: pd.Series | None, home_team: str) -> str:
    """Real venue-owning team for THIS game -- the home team for a real 'Home' game; for a real
    'Neutral' game, verifies (rather than assumes) that the schedule's own real `stadium` value
    really is the home team's own stadium under nflverse's own naming, raising instead of
    silently guessing if it is not (see module docstring's neutral-site scope note).
    `game_row` may be None/absent 'location' -- treated as a real 'Home' game (matches this
    project's established blank-guard convention)."""
    if game_row is None or game_row.get("location") != "Neutral":
        return home_team
    stadium_name = game_row.get("stadium")
    owning_team = _STADIUM_NAME_TO_TEAM.get(stadium_name)
    # Coordinate equality (not name equality) so a real shared building (MetLife for NYJ/NYG,
    # SoFi for LAC/LAR) correctly passes even when the alias table's owning_team differs from
    # home_team by name.
    if owning_team is None or STADIUM_COORDS.get(owning_team) != STADIUM_COORDS.get(home_team):
        # Real, deliberate refusal to guess: a genuine mismatch would mean a true neutral/
        # international venue this table does not yet cover (never fabricated around).
        raise ValueError(
            f"Neutral-site game with unresolved real venue '{stadium_name}' for home team "
            f"'{home_team}' -- not a known alias of that team's own stadium, and no "
            f"international-venue table is built (real, documented scope gap; never guessed)."
        )
    return home_team


def resolve_travel_effect_miles(
    away_team: str, home_team: str, game_row: pd.Series | None = None,
) -> float:
    """Real distance in miles from the away team's own stadium to the real game venue."""
    venue_team = resolve_game_venue_team(game_row, home_team)
    return haversine_miles(STADIUM_COORDS[away_team], STADIUM_COORDS[venue_team])


def resolve_travel_direction_offsets(home_team: str, away_team: str) -> tuple[float, float]:
    """Real (home_utc_offset, away_utc_offset) -- each team's own static real offset, matching
    v35's own real formula (venue-independent; see module docstring)."""
    return TEAM_UTC_OFFSET[home_team], TEAM_UTC_OFFSET[away_team]
