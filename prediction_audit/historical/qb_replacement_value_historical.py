"""
Step 6 composition: resolves a real historical QB Replacement Value (QB Index Section 6's own
real "Replacement Value (Game Points)" = Starter Score - Backup Score, scaled) for one real
team, using only real data available before a target game's own kickoff. Reuses the
already-built QB Index walk-forward resolver directly -- calls it once for role="Starter" and
once for role="Backup" for the same team, then diffs their real scores.

Real, deliberately scoped boundary (not a shortcut): whether the backup is ACTUALLY starting a
specific real game (`qb_replacement_adj()`'s own `backup_in_flag` argument) is a real, live
roster/injury-report fact for that one game -- not something decay-weighted season-to-date
stats can determine on their own. This module resolves the real replacement_value (the hard,
real, data-driven part); the caller supplies the real backup_in_flag for the target game,
matching this project's established "arithmetic only, not data sourcing" scoping exactly.
"""
from __future__ import annotations

import pandas as pd

from prediction_audit.engine.qb_index import QBIndexConstants, compute_qb_index
from prediction_audit.historical.qb_index_historical import resolve_qb_index_history


def resolve_qb_replacement_value(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame, sched: pd.DataFrame,
    target_season: int, target_week: int, team: str, qb_index_constants: QBIndexConstants,
) -> float | None:
    """Real QB Index Section 6 Replacement Value (Game Points) = (Starter Score - Backup
    Score) * conversion, using QBIndexConstants' own real points_per_sd/score_baseline
    already-applied Score (the conversion is baked into .score, not re-applied here -- matches
    the real Excel formula, which reads QB Index's own Score column directly, already in game-
    point terms via C37/C38, then applies ONLY the separate C39 points-to-game-points
    conversion on top). Returns None (never fabricates) if either the real Starter or real
    Backup can't be resolved for this team as of target_week -- most commonly because the team
    has no real qualifying backup this season yet.
    """
    try:
        starter_history = resolve_qb_index_history(
            pbp_3yr_prior, pbp_current_season, sched, target_season, target_week, team,
            "Starter",
        )
        backup_history = resolve_qb_index_history(
            pbp_3yr_prior, pbp_current_season, sched, target_season, target_week, team,
            "Backup",
        )
    except ValueError:
        return None

    starter_result = compute_qb_index(starter_history, qb_index_constants)
    backup_result = compute_qb_index(backup_history, qb_index_constants)
    return starter_result.score - backup_result.score
