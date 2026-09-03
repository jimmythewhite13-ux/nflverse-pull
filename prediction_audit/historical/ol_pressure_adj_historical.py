"""
Step 6 composition: resolves a real historical OL Pressure Adj differential (Home/Away OL
Index Pass Protection Z minus Away/Home Pass Rush Generation Index Score) for a real matchup,
using only real data available before a target game's own kickoff. Composes the already-built
OL Index and Pass Rush Generation Index walk-forward resolvers directly -- no new data source.
"""
from __future__ import annotations

import pandas as pd

from prediction_audit.engine.offensive_line_index import OLIndexConstants, compute_ol_index
from prediction_audit.engine.pass_rush_generation_index import (
    PassRushGenerationConstants,
    compute_pass_rush_generation_index,
)
from prediction_audit.historical.offensive_line_index_historical import (
    resolve_ol_index_history,
)
from prediction_audit.historical.pass_rush_generation_index_historical import (
    resolve_pass_rush_generation_history,
)


def resolve_ol_pressure_diff(
    pbp_3yr_prior: pd.DataFrame, pfr_pass_3yr: pd.DataFrame, pfr_rush_3yr: pd.DataFrame,
    ftn_3yr: pd.DataFrame, target_season: int, ol_team: str, pass_rush_opponent: str,
    ol_constants: OLIndexConstants, pass_rush_constants: PassRushGenerationConstants,
) -> float | None:
    """`ol_team`'s real OL Index Pass Protection Z minus `pass_rush_opponent`'s real Pass Rush
    Generation Score. Returns None (never fabricates) if either side can't be resolved --
    most commonly OL Index's own real FTN-coverage constraint for target seasons before 2025.
    """
    try:
        ol_history = resolve_ol_index_history(
            pfr_pass_3yr, pfr_rush_3yr, pbp_3yr_prior, ftn_3yr, target_season, ol_team,
        )
    except ValueError:
        return None
    ol_result = compute_ol_index(ol_history, ol_constants)

    try:
        pass_rush_history = resolve_pass_rush_generation_history(
            pbp_3yr_prior, target_season, pass_rush_opponent,
        )
    except ValueError:
        return None
    pass_rush_result = compute_pass_rush_generation_index(pass_rush_history, pass_rush_constants)

    return ol_result.z_scores["pass_protection"] - pass_rush_result.score
