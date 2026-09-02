"""
Market Comparison & Confidence's own real "Net Home Advantage" columns -- each one a simple
Home-Away (or, for Rest, a direct passthrough) real differential of a term already ported
elsewhere in this engine. Confirmed from the real formula text directly; Phase Matchup (Y),
OL Pressure (Z), and Explosive Play (AA) are the same family and already covered by
confidence_composite.py's own real matchup_agreement_component() inputs -- not duplicated
here.

Real formulas (row 4, generalized to row r):
    Rest Net Home Adv. (V)              = O            (Season Matchups' own Rest Effect,
                                                          already a Home-Away differential)
    Injury Net Home Adv. (W)            = V - W         (both always 0 -- see
                                                          core_formula_simple_terms.py)
    QB Repl. Net Home Adv. (X)          = AS - AT
    HFA Delta Net Home Adv. (AB)        = CR - CS
    Road Fatigue Net Home Adv. (AC)     = CV - CW
    Travel Direction Net Home Adv. (AD) = -DA            (away-only term, negated for the
                                                          home-relative framing every other
                                                          column here uses)

Every one of these is literally a subtraction or negation of values already proven correct in
their own parity tests; no new decay/blend/Z-score arithmetic exists here.
"""
from __future__ import annotations


def rest_net_home_adv(rest_effect_value: float) -> float:
    return rest_effect_value


def injury_net_home_adv(home_injury_adj: float, away_injury_adj: float) -> float:
    return home_injury_adj - away_injury_adj


def qb_replacement_net_home_adv(home_qb_repl_adj: float, away_qb_repl_adj: float) -> float:
    return home_qb_repl_adj - away_qb_repl_adj


def hfa_delta_net_home_adv(home_hfa_delta: float, away_hfa_delta: float) -> float:
    return home_hfa_delta - away_hfa_delta


def road_fatigue_net_home_adv(home_road_fatigue_adj: float, away_road_fatigue_adj: float) -> float:
    return home_road_fatigue_adj - away_road_fatigue_adj


def travel_direction_net_home_adv(away_travel_direction_adj: float) -> float:
    return -away_travel_direction_adj
