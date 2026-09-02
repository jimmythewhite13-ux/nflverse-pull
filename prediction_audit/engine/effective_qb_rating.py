"""
Season Matchups' own real "Effective QB Rating" (CA/CB) -- the real composite that Phase
Matchup Adj's pass-side differential (AW/AZ) actually reads as "Home/Away Starter QB Index
Score", found while correcting this project's own earlier mis-scoping of QB Environment Model
(see that module's own docstring). NOT simply QB Index's own Score for the starter -- a real
opponent-independent QB Environment-Adjusted Baseline (qb_environment_model.py's own output)
plus two real game-specific modifiers.

Real formula chain, confirmed from the text directly (row 3, generalized to row r):

    OL Modifier (BU/BV): scales the already-computed OL Pressure Matchup Diff (BK/BN, the
    same real differential OL Pressure Adj itself uses -- read twice for two different
    purposes, not circular) by the QB's own real Sack Rate Z (from QB Environment Model,
    reference-only there) -- a QB who takes sacks at a below-average rate (positive Sack Rate
    Z) has their OL matchup differential amplified; MAX(0, ...) means a bad Sack Rate Z never
    REDUCES the OL modifier below the raw differential, only a good one can amplify it:
        BU =IF(BK="","",BK*(1+MAX(0,IF(BS="",0,BS))*C133))

    Weather-on-Passing Modifier (BW/BX): scales the already-ported Weather Adj (U) by a real
    team pass-rate share (a real aggregate ratio from real SUMIFS over QB Environment Model +
    RB Value Index raw play data, taken here as an already-resolved given input per this
    project's "arithmetic only, not data sourcing" scoping):
        BW =IF(BQ="",0,U*BQ*C134)

    Effective QB Rating (CA/CB): the QB Environment-Adjusted Baseline (BY/BZ) plus both
    modifiers, with a blank guard on the baseline itself (not on the modifiers, which already
    guard themselves) -- and the OL Modifier substitutes 0 if blank rather than propagating a
    blank, unlike the baseline's own guard:
        CA =IF(BY="","",BY+IF(BU="",0,BU)+BW)
"""
from __future__ import annotations


def ol_modifier(
    ol_pressure_diff: float | None, sack_rate_z: float | None, scaling: float,
) -> float | None:
    if ol_pressure_diff in (None, ""):
        return None
    sack_z_or_zero = 0.0 if sack_rate_z in (None, "") else sack_rate_z
    return ol_pressure_diff * (1 + max(0.0, sack_z_or_zero) * scaling)


def weather_on_passing_modifier(
    weather_adj_value: float, team_pass_rate: float | None, scaling: float,
) -> float:
    if team_pass_rate in (None, ""):
        return 0.0
    return weather_adj_value * team_pass_rate * scaling


def effective_qb_rating(
    adjusted_baseline: float | None, ol_modifier_value: float | None,
    weather_modifier_value: float,
) -> float | None:
    if adjusted_baseline in (None, ""):
        return None
    ol_mod_or_zero = 0.0 if ol_modifier_value in (None, "") else ol_modifier_value
    return adjusted_baseline + ol_mod_or_zero + weather_modifier_value
