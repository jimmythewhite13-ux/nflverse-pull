"""
Season Matchups' own real Z/AA formula -- the top-level composition of every term ported in
core_formula_simple_terms.py, team_quality.py, and explosive_play_matchup.py. This is the
culminating piece: with every real named term in v35_core_formula_components.csv individually
proven correct against its own ground truth, this module sums them exactly as the real Z/AA
formula does and is checked against the real Model Home/Away Score for all 272 real games.

Real formula (confirmed from the text, Season Matchups row 3, generalized to row r):

    Z  (Model Home Score) =(I+L)/2 + C3/2 + O/2 + U/2 + V + Y/2 + AS + BG + BO + CO + CR + CV
    AA (Model Away Score) =(K+J)/2 - C3/2 - O/2 + Q + U/2 + W + Y/2 + AT + BH + BP + CP + CS
                            + CW + DA

Every term on the right-hand side is produced by a function already ported elsewhere in this
package (see each function's own docstring for its real formula and ground truth); this module
does no new arithmetic of its own beyond the final sum. Per this project's "arithmetic only,
not data sourcing" scoping used throughout every tab in this engine, upstream real inputs this
module's own callers must supply (Phase Matchup / OL Pressure differentials, QB Replacement
Values, per-team UTC offsets, Consecutive Road Games counts, etc.) are taken as given -- see
core_formula_simple_terms.py's own module docstring for exactly which pieces that covers.
Wiring those differentials up from the QB/RB/OL/Pass-Defense/Run-Defense/Pass-Rush-Generation
engines' own real Section 5 outputs (rather than reading them from Excel) is a separate,
larger follow-on increment -- this module proves the SUMMATION is correct, not (yet) a
zero-Excel-dependency walk-forward reconstruction.
"""
from __future__ import annotations


def compute_model_home_away_score(
    base_team_quality_home: float,
    base_team_quality_away: float,
    flat_hfa: float,
    rest_effect_value: float,
    weather_adj_value: float,
    injury_adj_home: float,
    injury_adj_away: float,
    division_adj_value: float,
    qb_replacement_home: float,
    qb_replacement_away: float,
    phase_matchup_home: float,
    phase_matchup_away: float,
    ol_pressure_home: float,
    ol_pressure_away: float,
    explosive_play_home: float,
    explosive_play_away: float,
    hfa_delta_home: float,
    hfa_delta_away: float,
    road_fatigue_home: float,
    road_fatigue_away: float,
    travel_effect_away: float,
    travel_direction_away: float,
) -> tuple[float, float]:
    """Returns (model_home_score, model_away_score) -- the real Z/AA values."""
    home = (
        base_team_quality_home
        + flat_hfa / 2
        + rest_effect_value / 2
        + weather_adj_value / 2
        + injury_adj_home
        + division_adj_value / 2
        + qb_replacement_home
        + phase_matchup_home
        + ol_pressure_home
        + explosive_play_home
        + hfa_delta_home
        + road_fatigue_home
    )
    away = (
        base_team_quality_away
        - flat_hfa / 2
        - rest_effect_value / 2
        + travel_effect_away
        + weather_adj_value / 2
        + injury_adj_away
        + division_adj_value / 2
        + qb_replacement_away
        + phase_matchup_away
        + ol_pressure_away
        + explosive_play_away
        + hfa_delta_away
        + road_fatigue_away
        + travel_direction_away
    )
    return home, away
