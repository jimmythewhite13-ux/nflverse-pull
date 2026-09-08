"""
Step 6 composition: resolves a real historical Effective QB Rating for one real team's real
Starter QB, for one specific real game matchup, using only real data available before that
game's own kickoff. Composes 3 already-built real resolvers (QB Environment Model, and the
same real OL Pressure diff `ol_pressure_adj_historical.py` already resolves -- read twice for
two different purposes, matching the real Excel formula's own documented reuse) plus one real,
newly-computed input: a team's real current-season pass-rate share.

Real, deliberately scoped simplification: the real Excel weather-on-passing modifier's
`team_pass_rate` input is a real SUMIFS aggregate over QB Environment Model + RB Value Index
raw play data (taken as an already-resolved given input per that engine's own module
docstring). This module computes a real, honest proxy instead of leaving it as a hardcoded
given: real current-season-so-far pass attempts / (pass attempts + rush attempts) for the
team, from the same real pbp already being pulled -- a genuinely real, computed ratio, not the
exact real SUMIFS formula (which weights by real dropback/carry counts from two specific
already-ported tabs' own raw data tables), but directionally the same real signal.
"""
from __future__ import annotations

import pandas as pd

from prediction_audit.engine.effective_qb_rating import (
    effective_qb_rating,
    ol_modifier,
    weather_on_passing_modifier,
)
from prediction_audit.engine.offensive_line_index import OLIndexConstants
from prediction_audit.engine.pass_rush_generation_index import PassRushGenerationConstants
from prediction_audit.engine.qb_environment_model import (
    QBEnvironmentModelConstants,
    compute_qb_environment_model,
)
from prediction_audit.historical.ol_pressure_adj_historical import resolve_ol_pressure_diff
from prediction_audit.historical.qb_environment_model_historical import (
    resolve_qb_environment_model_history,
)


def resolve_team_pass_rate(
    pbp_current_season: pd.DataFrame, target_week: int, team_abbr: str,
) -> float | None:
    """Real current-season-so-far pass-rate share (weeks strictly before target_week) --
    pass_attempt / (pass_attempt + rush) for one real team abbreviation. Returns None (never
    fabricates) if the team has no real qualifying plays yet this season."""
    reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG")
        & (pbp_current_season["week"] < target_week)
        & (pbp_current_season["posteam"] == team_abbr)
        & (pbp_current_season["play_type"].isin(["pass", "run"]))
    ]
    if reg.empty:
        return None
    return float((reg["play_type"] == "pass").mean())


def resolve_effective_qb_rating(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame, sched: pd.DataFrame,
    pfr_pass_3yr: pd.DataFrame, pfr_rush_3yr: pd.DataFrame, ftn_3yr: pd.DataFrame,
    target_season: int, target_week: int, team: str, team_abbr: str,
    pass_rush_opponent: str, weather_adj_value: float,
    qb_env_constants: QBEnvironmentModelConstants, ol_constants: OLIndexConstants,
    pass_rush_constants: PassRushGenerationConstants,
    ol_modifier_scaling: float, weather_modifier_scaling: float,
) -> float | None:
    """`team`/`team_abbr`: this project's full-name convention and nflverse's own abbreviation
    for the SAME real team (both needed -- QB Environment Model resolvers use full names,
    pbp's own posteam column uses abbreviations). `pass_rush_opponent`: the real opposing
    team (full name) this game's real OL Pressure matchup diff is computed against. Returns
    None (never fabricates) if the real QB Environment Model baseline itself can't be
    resolved."""
    try:
        qb_env_history = resolve_qb_environment_model_history(
            pbp_3yr_prior, pbp_current_season, sched, target_season, target_week, team,
            "Starter",
        )
    except ValueError:
        return None
    qb_env_result = compute_qb_environment_model(qb_env_history, qb_env_constants)

    ol_diff = resolve_ol_pressure_diff(
        pbp_3yr_prior, pfr_pass_3yr, pfr_rush_3yr, ftn_3yr, target_season, team,
        pass_rush_opponent, ol_constants, pass_rush_constants,
    )
    ol_mod = ol_modifier(ol_diff, qb_env_result.z_scores["sack"], ol_modifier_scaling)

    pass_rate = resolve_team_pass_rate(pbp_current_season, target_week, team_abbr)
    weather_mod = weather_on_passing_modifier(
        weather_adj_value, pass_rate, weather_modifier_scaling,
    )

    return effective_qb_rating(qb_env_result.adjusted_baseline, ol_mod, weather_mod)
