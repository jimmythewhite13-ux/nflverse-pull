"""
Step 6 composition: resolves real historical Phase Matchup Adj (Home/Away) for a real game
matchup, using only real data available before that game's own kickoff. Composes Effective QB
Rating (pass side) and RB Index (run side) against the OPPONENT's real Pass/Run Defense
Matchup Score -- the real "home vs away, not same-team" matchup diff this term is named for.

Real formula (confirmed via core_formula_simple_terms.py's own docstring, Season Matchups
BG/BH): Home Adj = (Home Pass diff * C101) + (Home Run diff * C102); Away Adj mirrors with
sides swapped. Both halves independently return 0.0 (never fabricate) when their own real
differential can't be resolved, matching Excel's own real blank-guard behavior.
"""
from __future__ import annotations

import pandas as pd

from prediction_audit.engine.core_formula_simple_terms import phase_matchup_adj
from prediction_audit.engine.offensive_line_index import OLIndexConstants
from prediction_audit.engine.pass_defense_matchup import (
    PassDefenseMatchupConstants,
    compute_pass_defense_matchup,
)
from prediction_audit.engine.pass_rush_generation_index import PassRushGenerationConstants
from prediction_audit.engine.qb_environment_model import QBEnvironmentModelConstants
from prediction_audit.engine.rb_index import RBIndexConstants, compute_rb_index
from prediction_audit.engine.run_defense_matchup import (
    RunDefenseMatchupConstants,
    compute_run_defense_matchup,
)
from prediction_audit.historical.effective_qb_rating_historical import (
    resolve_effective_qb_rating,
)
from prediction_audit.historical.pass_defense_matchup_historical import (
    resolve_pass_defense_matchup_history,
)
from prediction_audit.historical.rb_index_historical import resolve_rb_index_history
from prediction_audit.historical.run_defense_matchup_historical import (
    resolve_run_defense_matchup_history,
)


def _resolve_pass_defense_score(
    pbp_3yr_prior: pd.DataFrame, target_season: int, team: str,
    constants: PassDefenseMatchupConstants,
) -> float | None:
    try:
        history = resolve_pass_defense_matchup_history(pbp_3yr_prior, target_season, team)
    except ValueError:
        return None
    return compute_pass_defense_matchup(history, constants).score


def _resolve_run_defense_score(
    pbp_3yr_prior: pd.DataFrame, target_season: int, team: str,
    constants: RunDefenseMatchupConstants,
) -> float | None:
    try:
        history = resolve_run_defense_matchup_history(pbp_3yr_prior, target_season, team)
    except ValueError:
        return None
    return compute_run_defense_matchup(history, constants).score


def _resolve_rb_starter_score(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame,
    ngs_rushing_3yr_prior: pd.DataFrame, ngs_rushing_current: pd.DataFrame,
    sched: pd.DataFrame, target_season: int, target_week: int, team: str,
    constants: RBIndexConstants,
) -> float | None:
    try:
        history = resolve_rb_index_history(
            pbp_3yr_prior, pbp_current_season, ngs_rushing_3yr_prior, ngs_rushing_current,
            sched, target_season, target_week, team, "Starter",
        )
    except ValueError:
        return None
    return compute_rb_index(history, constants).score


def resolve_phase_matchup_adj(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame, sched: pd.DataFrame,
    pfr_pass_3yr: pd.DataFrame, pfr_rush_3yr: pd.DataFrame, ftn_3yr: pd.DataFrame,
    ngs_rushing_3yr_prior: pd.DataFrame, ngs_rushing_current: pd.DataFrame,
    target_season: int, target_week: int,
    home_team: str, home_abbr: str, away_team: str, away_abbr: str,
    home_weather_adj: float, away_weather_adj: float,
    qb_env_constants: QBEnvironmentModelConstants, ol_constants: OLIndexConstants,
    pass_rush_constants: PassRushGenerationConstants,
    pass_defense_constants: PassDefenseMatchupConstants,
    run_defense_constants: RunDefenseMatchupConstants, rb_constants: RBIndexConstants,
    ol_modifier_scaling: float, weather_modifier_scaling: float,
    pass_conversion: float, run_conversion: float,
) -> tuple[float, float]:
    """Returns (home_adj, away_adj) -- the real Season Matchups BG/BH. home_weather_adj/
    away_weather_adj are the SAME real Weather Adj value for this game, per side (U/2's own
    real sign convention is applied by the caller composing the final Z/AA sum, not here --
    this module passes the raw real Weather Adj value into each side's own Effective QB Rating
    unchanged, matching Excel's own real BW/BX formula, which reads U directly)."""
    home_eqr = resolve_effective_qb_rating(
        pbp_3yr_prior, pbp_current_season, sched, pfr_pass_3yr, pfr_rush_3yr, ftn_3yr,
        target_season, target_week, home_team, home_abbr, away_team, home_weather_adj,
        qb_env_constants, ol_constants, pass_rush_constants, ol_modifier_scaling,
        weather_modifier_scaling,
    )
    away_eqr = resolve_effective_qb_rating(
        pbp_3yr_prior, pbp_current_season, sched, pfr_pass_3yr, pfr_rush_3yr, ftn_3yr,
        target_season, target_week, away_team, away_abbr, home_team, away_weather_adj,
        qb_env_constants, ol_constants, pass_rush_constants, ol_modifier_scaling,
        weather_modifier_scaling,
    )
    away_pass_defense = _resolve_pass_defense_score(
        pbp_3yr_prior, target_season, away_team, pass_defense_constants,
    )
    home_pass_defense = _resolve_pass_defense_score(
        pbp_3yr_prior, target_season, home_team, pass_defense_constants,
    )
    home_pass_diff = (
        None if home_eqr is None or away_pass_defense is None
        else home_eqr - away_pass_defense
    )
    away_pass_diff = (
        None if away_eqr is None or home_pass_defense is None
        else away_eqr - home_pass_defense
    )

    home_rb = _resolve_rb_starter_score(
        pbp_3yr_prior, pbp_current_season, ngs_rushing_3yr_prior, ngs_rushing_current, sched,
        target_season, target_week, home_team, rb_constants,
    )
    away_rb = _resolve_rb_starter_score(
        pbp_3yr_prior, pbp_current_season, ngs_rushing_3yr_prior, ngs_rushing_current, sched,
        target_season, target_week, away_team, rb_constants,
    )
    away_run_defense = _resolve_run_defense_score(
        pbp_3yr_prior, target_season, away_team, run_defense_constants,
    )
    home_run_defense = _resolve_run_defense_score(
        pbp_3yr_prior, target_season, home_team, run_defense_constants,
    )
    home_run_diff = (
        None if home_rb is None or away_run_defense is None else home_rb - away_run_defense
    )
    away_run_diff = (
        None if away_rb is None or home_run_defense is None else away_rb - home_run_defense
    )

    home_pass_adj, away_pass_adj = phase_matchup_adj(
        home_pass_diff, away_pass_diff, pass_conversion,
    )
    home_run_adj, away_run_adj = phase_matchup_adj(home_run_diff, away_run_diff, run_conversion)

    return home_pass_adj + home_run_adj, away_pass_adj + away_run_adj
