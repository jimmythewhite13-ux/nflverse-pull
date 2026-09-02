"""
Season Matchups' own "simple direct-arithmetic" Z/AA components -- confirmed by reading the
real formula text in the frozen v35 file's own Season Matchups sheet directly (never assumed).
Unlike every tab ported so far (decay-weighted-average -> team-history -> projected-baseline
-> [blend] -> Z-score -> weighted-composite chains), these six terms are simple threshold/
lookup/multiply arithmetic over already-resolved real inputs -- no decay, no Z-scoring.

Real formulas confirmed live in the recalculated v35 copy (row 3, generalized to row r):

    Rest Effect (O):
        =IF(M3<=C150,C152,IF(M3>=C151,C154,C153))
         -IF(N3<=C150,C152,IF(N3>=C151,C154,C153))
    Weather Adj (U):
        =IF(F3="Dome",0,
            IF(DB3="Y",C158,IF(T3="Y",C10,0))
            +IF(S3>C6,C7,0)+IF(R3<C8,C9,0)+IF(DC3>=C159,C160,0))
    Division Adj (Y):
        =IF(X3="Y",C11,0)
    QB Replacement Value (Season Matchups AS/AT, sourced from QB Index Section 6's own real
    "Replacement Value (Game Points)" column G):
        =IF(AQ3="Backup In",IFERROR(-INDEX('QB Index'!$G$312:$G$343,
            MATCH(D3,'QB Index'!$A$312:$A$343,0)),0),0)
    Phase Matchup Adj (BG/BH), where AW/BC (home) and AZ/BF (away) are pre-computed real
    differentials (Home/Away Starter [QB|RB] Index Score minus Away/Home [Pass|Run] Defense
    Matchup Score -- both already-ported engine outputs, taken here as given real inputs per
    this project's established "arithmetic only, not data sourcing" scoping):
        =IF(AW3="",0,AW3*C101)+IF(BC3="",0,BC3*C102)
    OL Pressure Adj (BO/BP), where BK/BN are a pre-computed real differential (Home/Away OL
    Index's own Pass Protection Z minus Away/Home Pass Rush Generation Index Score -- also
    already-ported outputs, taken as given):
        =IF(BK3="",0,BK3*C123)

Ground truth was extracted across all 272 real Season Matchups rows. In that real snapshot,
every game's real Snow/Precipitation flags are "N", every real Backup-In flag is "Starter In",
and no game has a non-Dome nonzero Weather Adj or nonzero QB Replacement Value -- this reflects
the workbook's real current/future-week live-entry state (weather/injury events for future
weeks genuinely haven't happened yet), not a gap in this extraction. Per this project's
anti-fabrication principle, no synthetic non-zero case is manufactured to pad coverage; the
branch logic for those paths is implemented directly from the real formula text above and will
be exercised for real the moment a real future week's data includes them.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RestEffectConstants:
    low_threshold: float   # C150 -- days, <=
    high_threshold: float  # C151 -- days, >=
    low_val: float          # C152
    mid_val: float           # C153
    high_val: float          # C154


def _rest_tier(rest_days: float, c: RestEffectConstants) -> float:
    if rest_days <= c.low_threshold:
        return c.low_val
    if rest_days >= c.high_threshold:
        return c.high_val
    return c.mid_val


def rest_effect(home_rest: float, away_rest: float, c: RestEffectConstants) -> float:
    return _rest_tier(home_rest, c) - _rest_tier(away_rest, c)


@dataclass
class WeatherAdjConstants:
    wind_threshold: float   # C6, mph, strictly >
    wind_adj: float          # C7
    cold_threshold: float   # C8, deg F, strictly <
    cold_adj: float           # C9
    precip_adj: float        # C10
    snow_adj: float           # C158
    humidity_threshold: float  # C159, %, >=
    humidity_adj: float        # C160


def weather_adj(
    is_dome: str, snow_flag: str, precip_flag: str,
    wind: float, temp: float, humidity: float, c: WeatherAdjConstants,
) -> float:
    if is_dome == "Dome":
        return 0.0
    total = c.snow_adj if snow_flag == "Y" else (c.precip_adj if precip_flag == "Y" else 0.0)
    if wind > c.wind_threshold:
        total += c.wind_adj
    if temp < c.cold_threshold:
        total += c.cold_adj
    if humidity >= c.humidity_threshold:
        total += c.humidity_adj
    return total


def division_adj(is_divisional: str, division_adj_const: float) -> float:
    return division_adj_const if is_divisional == "Y" else 0.0


def qb_replacement_adj(backup_in_flag: str, replacement_value: float) -> float:
    """replacement_value is QB Index Section 6's own real "Replacement Value (Game Points)"
    (Starter Score - Backup Score) for the team in question -- an already-resolved real input,
    per this project's "arithmetic only, not data sourcing" scoping. IFERROR's fallback (0) is
    not separately modeled here: absence of a real lookup match is a data-resolution concern,
    not an arithmetic one; callers pass 0.0 for replacement_value in that case."""
    return -replacement_value if backup_in_flag == "Backup In" else 0.0


def phase_matchup_adj(
    home_diff: float | None, away_diff: float | None,
    pass_or_run_conversion: float,
) -> tuple[float, float]:
    """Returns (home_adj, away_adj). home_diff/away_diff are already-resolved real
    differentials (e.g. Home Starter QB Index Score - Away Pass Defense Matchup Score);
    None/"" mirrors Excel's own =IF(cell="",0,...) blank guard."""
    home_adj = 0.0 if home_diff in (None, "") else home_diff * pass_or_run_conversion
    away_adj = 0.0 if away_diff in (None, "") else away_diff * pass_or_run_conversion
    return home_adj, away_adj


def ol_pressure_adj(diff: float | None, conversion: float) -> float:
    """diff is an already-resolved real differential (Home/Away OL Index Pass Protection Z
    minus Away/Home Pass Rush Generation Index Score); None/"" mirrors Excel's own blank guard."""
    return 0.0 if diff in (None, "") else diff * conversion
