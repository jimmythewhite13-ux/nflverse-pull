"""
Step 6 composition: resolves real historical Explosive Play Adj (Home/Away, Season Matchups
CO/CP) for a real game matchup, using only real data available before that game's own kickoff.
Composes each side's own already-built `resolve_explosive_play_matchup_history()` result
(both teams) with the already-Excel-proven `explosive_play_matchup_adj()` -- no new data
source, pure integration.
"""
from __future__ import annotations

import pandas as pd

from prediction_audit.engine.explosive_play_matchup import (
    ExplosivePlayMatchupConstants,
    compute_explosive_play_matchup,
    explosive_play_matchup_adj,
)
from prediction_audit.engine.pass_defense_matchup import PassDefenseMatchupConstants
from prediction_audit.engine.run_defense_matchup import RunDefenseMatchupConstants
from prediction_audit.historical.explosive_play_matchup_historical import (
    resolve_explosive_play_matchup_history,
)


def resolve_explosive_play_adj(
    pbp_3yr_prior: pd.DataFrame, target_season: int, home_team: str, away_team: str,
    pass_defense_constants: PassDefenseMatchupConstants,
    run_defense_constants: RunDefenseMatchupConstants,
    explosive_constants: ExplosivePlayMatchupConstants,
    pass_conversion: float, run_conversion: float,
) -> tuple[float, float]:
    """Returns (home_adj, away_adj). Returns (0.0, 0.0) (never fabricates) if either team's
    own real Explosive Play Matchup can't be resolved (most commonly a real Pass/Run Defense
    Matchup coverage gap for one side)."""
    try:
        home_history = resolve_explosive_play_matchup_history(
            pbp_3yr_prior, target_season, home_team, pass_defense_constants,
            run_defense_constants,
        )
        away_history = resolve_explosive_play_matchup_history(
            pbp_3yr_prior, target_season, away_team, pass_defense_constants,
            run_defense_constants,
        )
    except ValueError:
        return 0.0, 0.0

    home_result = compute_explosive_play_matchup(home_history, explosive_constants)
    away_result = compute_explosive_play_matchup(away_history, explosive_constants)

    return explosive_play_matchup_adj(
        home_pass_off_z=home_result.pass_off_z,
        away_pass_prevention_z=away_result.pass_prevention_composite_z,
        away_pass_off_z=away_result.pass_off_z,
        home_pass_prevention_z=home_result.pass_prevention_composite_z,
        home_run_off_z=home_result.run_off_z,
        away_run_prevention_z=away_result.run_prevention_z,
        away_run_off_z=away_result.run_off_z,
        home_run_prevention_z=home_result.run_prevention_z,
        pass_conversion=pass_conversion, run_conversion=run_conversion,
    )
