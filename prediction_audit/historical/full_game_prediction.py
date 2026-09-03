"""
Step 6's own culminating deliverable: a real, end-to-end historical Model Home/Away Score for
an arbitrary real past game, composing every one of the 16 real Z/AA components this session
built (see PROGRESS.md's own summary table) exactly as `season_matchups.py`'s own real,
Excel-proven `compute_model_home_away_score()` sums them -- but sourced from real historical
nflverse data instead of the frozen 2026 Excel snapshot.

Travel Effect and Travel Direction Adj are now real, resolved terms (`stadium_locations.py`,
verified against v35's own real 272-game ground truth to within 0.5mi/exact-offset on every
game -- see that module's docstring), not the earlier placeholder 0.0 default. Both are still
exposed as optional overrides for a caller with a more specific real venue than the schedule
row implies. Injury Adj is not a gap -- it is confirmed to be a real, permanent constant 0 in
the live workbook itself (core_formula_simple_terms.py's own `injury_adj()`).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from prediction_audit.engine.core_formula_simple_terms import (
    RestEffectConstants,
    WeatherAdjConstants,
    hfa_delta_away,
    hfa_delta_home,
    injury_adj,
    qb_replacement_adj,
    travel_direction_adj,
    travel_effect,
)
from prediction_audit.engine.core_formula_simple_terms import (
    road_fatigue_adj as _road_fatigue_adj_fn,
)
from prediction_audit.engine.explosive_play_matchup import ExplosivePlayMatchupConstants
from prediction_audit.engine.offensive_line_index import OLIndexConstants
from prediction_audit.engine.pass_defense_matchup import PassDefenseMatchupConstants
from prediction_audit.engine.pass_rush_generation_index import PassRushGenerationConstants
from prediction_audit.engine.qb_environment_model import QBEnvironmentModelConstants
from prediction_audit.engine.qb_index import QBIndexConstants
from prediction_audit.engine.rb_index import RBIndexConstants
from prediction_audit.engine.run_defense_matchup import RunDefenseMatchupConstants
from prediction_audit.engine.season_matchups import compute_model_home_away_score
from prediction_audit.engine.team_quality import TeamQualityConstants, base_team_quality
from prediction_audit.engine.team_specific_hfa import TeamSpecificHFAConstants
from prediction_audit.historical.explosive_play_adj_historical import (
    resolve_explosive_play_adj,
)
from prediction_audit.historical.game_context import (
    resolve_consecutive_road_games,
    resolve_division_adj_for_game,
    resolve_rest_effect_for_game,
    resolve_weather_adj_for_game,
)
from prediction_audit.historical.ol_pressure_adj_historical import resolve_ol_pressure_diff
from prediction_audit.historical.phase_matchup_historical import resolve_phase_matchup_adj
from prediction_audit.historical.qb_replacement_value_historical import (
    resolve_qb_replacement_value,
)
from prediction_audit.historical.stadium_locations import (
    resolve_travel_direction_offsets,
    resolve_travel_effect_miles,
)
from prediction_audit.historical.team_hfa import resolve_team_specific_hfa_for_game
from prediction_audit.historical.walk_forward import (
    WalkForwardTarget,
    resolve_team_quality_for_game,
)


@dataclass
class HistoricalGameModelConstants:
    """Every real Model Assumptions constant this composition needs, grouped by the engine
    object each already-built resolver expects -- one object per already-proven tab, not
    flattened, so each nested constants object stays exactly what its own tab's tests use."""
    team_quality: TeamQualityConstants
    team_specific_hfa: TeamSpecificHFAConstants
    rest_effect: RestEffectConstants
    weather_adj: WeatherAdjConstants
    division_adj_const: float
    qb_index: QBIndexConstants
    ol_index: OLIndexConstants
    pass_rush_generation: PassRushGenerationConstants
    pass_defense_matchup: PassDefenseMatchupConstants
    run_defense_matchup: RunDefenseMatchupConstants
    rb_index: RBIndexConstants
    qb_environment_model: QBEnvironmentModelConstants
    explosive_play_matchup: ExplosivePlayMatchupConstants
    # Coaching Index deliberately NOT included -- confirmed real formula text shows it feeds
    # Team Ratings' own Net Home Advantage/display composite, never Z/AA directly (same real
    # "out of scope for Z/AA" finding as Advanced Efficiency Metrics).
    flat_hfa: float                          # Model Assumptions C3
    pass_matchup_conversion: float           # C101
    run_matchup_conversion: float            # C102
    ol_pressure_conversion: float            # C123
    ol_modifier_scaling: float               # C133
    weather_modifier_scaling: float          # C134
    road_fatigue_threshold: float            # C150-family (Road Fatigue's own threshold)
    road_fatigue_penalty: float
    qb_replacement_conversion: float         # C39
    travel_coefficient: float                # C5
    west_to_east_penalty: float              # C157


@dataclass
class HistoricalGameDataBundle:
    """Every real pre-fetched DataFrame this composition needs -- fetched once by the caller,
    reused across every sub-resolver (each already designed to take pre-fetched real data
    rather than fetch its own, per this project's established fetch/transform split)."""
    pbp_3yr_prior: pd.DataFrame
    pbp_current_season: pd.DataFrame
    sched_current_season: pd.DataFrame
    sched_3yr_prior: pd.DataFrame
    pfr_pass_3yr: pd.DataFrame
    pfr_rush_3yr: pd.DataFrame
    ftn_3yr: pd.DataFrame
    ngs_rushing_3yr_prior: pd.DataFrame
    ngs_rushing_current: pd.DataFrame


def resolve_historical_model_home_away_score(
    bundle: HistoricalGameDataBundle, constants: HistoricalGameModelConstants,
    target_season: int, target_week: int,
    home_team: str, home_abbr: str, away_team: str, away_abbr: str,
    home_backup_in: bool = False, away_backup_in: bool = False,
    travel_effect_away: float | None = None, travel_direction_away: float | None = None,
) -> tuple[float, float]:
    """Returns (model_home_score, model_away_score) -- a real, end-to-end historical Z/AA
    prediction for one real past game, using only real data available before its own kickoff.
    `home_backup_in`/`away_backup_in`: real, live roster-status facts for THIS specific game
    (whether the primary starter was out) -- not derivable from season-to-date stats alone,
    so still a required caller input, matching this project's established scoping.
    `travel_effect_away`/`travel_direction_away`: real values are resolved automatically from
    `stadium_locations.py` when left as None; pass an explicit value only to override (e.g. a
    genuine international/neutral-site venue that module's own alias table does not cover).
    """
    game_row = bundle.sched_current_season[
        (bundle.sched_current_season["season"] == target_season)
        & (bundle.sched_current_season["week"] == target_week)
        & (bundle.sched_current_season["home_team"] == home_abbr)
        & (bundle.sched_current_season["away_team"] == away_abbr)
    ]
    if game_row.empty:
        raise ValueError(
            f"No real scheduled game found for {away_abbr}@{home_abbr}, season "
            f"{target_season} week {target_week} (never fabricated)."
        )
    game_row = game_row.iloc[0]

    # ---- Base Team Quality -------------------------------------------------------------
    # resolve_team_quality_for_game() needs real Y1/Y2/Y3 (3 full prior seasons) AND the
    # real current-season-so-far slice from the SAME sched DataFrame -- combines the bundle's
    # two real schedule slices rather than passing either alone (an earlier version of this
    # composer passed sched_current_season only, which genuinely can't resolve Y1/Y2/Y3 and
    # correctly raised rather than silently using a truncated real history).
    sched_all_years = pd.concat(
        [bundle.sched_3yr_prior, bundle.sched_current_season], ignore_index=True,
    )
    target = WalkForwardTarget(
        season=target_season, week=target_week, home_team=home_team, away_team=away_team,
    )
    home_tq, away_tq = resolve_team_quality_for_game(
        sched_all_years, target, constants.team_quality,
    )
    home_base_quality, away_base_quality = base_team_quality(
        home_tq.blended_off, away_tq.blended_def, away_tq.blended_off, home_tq.blended_def,
    )

    # ---- Rest / Weather / Division / Injury (direct arithmetic) -----------------------
    rest_effect_value = resolve_rest_effect_for_game(game_row, constants.rest_effect)
    weather_adj_value = resolve_weather_adj_for_game(game_row, constants.weather_adj)
    weather_adj_value = 0.0 if weather_adj_value is None else weather_adj_value
    division_adj_value = resolve_division_adj_for_game(game_row, constants.division_adj_const)
    injury_adj_home = injury_adj()
    injury_adj_away = injury_adj()

    # ---- QB Replacement Value -----------------------------------------------------------
    home_replacement = resolve_qb_replacement_value(
        bundle.pbp_3yr_prior, bundle.pbp_current_season, bundle.sched_current_season,
        target_season, target_week, home_team, constants.qb_index,
    )
    away_replacement = resolve_qb_replacement_value(
        bundle.pbp_3yr_prior, bundle.pbp_current_season, bundle.sched_current_season,
        target_season, target_week, away_team, constants.qb_index,
    )
    qb_replacement_home = qb_replacement_adj(
        "Backup In" if home_backup_in else "", 0.0 if home_replacement is None
        else home_replacement * constants.qb_replacement_conversion,
    )
    qb_replacement_away = qb_replacement_adj(
        "Backup In" if away_backup_in else "", 0.0 if away_replacement is None
        else away_replacement * constants.qb_replacement_conversion,
    )

    # ---- Phase Matchup Adj (Effective QB Rating vs opposing Pass/Run Defense) ----------
    phase_matchup_home, phase_matchup_away = resolve_phase_matchup_adj(
        bundle.pbp_3yr_prior, bundle.pbp_current_season, bundle.sched_current_season,
        bundle.pfr_pass_3yr, bundle.pfr_rush_3yr, bundle.ftn_3yr,
        bundle.ngs_rushing_3yr_prior, bundle.ngs_rushing_current,
        target_season, target_week, home_team, home_abbr, away_team, away_abbr,
        weather_adj_value, weather_adj_value,
        constants.qb_environment_model, constants.ol_index, constants.pass_rush_generation,
        constants.pass_defense_matchup, constants.run_defense_matchup, constants.rb_index,
        constants.ol_modifier_scaling, constants.weather_modifier_scaling,
        constants.pass_matchup_conversion, constants.run_matchup_conversion,
    )

    # ---- OL Pressure Adj (OL Index Pass Protection Z vs opposing Pass Rush Generation) -
    home_ol_diff = resolve_ol_pressure_diff(
        bundle.pbp_3yr_prior, bundle.pfr_pass_3yr, bundle.pfr_rush_3yr, bundle.ftn_3yr,
        target_season, home_team, away_team, constants.ol_index,
        constants.pass_rush_generation,
    )
    away_ol_diff = resolve_ol_pressure_diff(
        bundle.pbp_3yr_prior, bundle.pfr_pass_3yr, bundle.pfr_rush_3yr, bundle.ftn_3yr,
        target_season, away_team, home_team, constants.ol_index,
        constants.pass_rush_generation,
    )
    ol_pressure_home = (
        0.0 if home_ol_diff is None else home_ol_diff * constants.ol_pressure_conversion
    )
    ol_pressure_away = (
        0.0 if away_ol_diff is None else away_ol_diff * constants.ol_pressure_conversion
    )

    # ---- Explosive Play Adj --------------------------------------------------------------
    explosive_play_home, explosive_play_away = resolve_explosive_play_adj(
        bundle.pbp_3yr_prior, target_season, home_team, away_team,
        constants.pass_defense_matchup, constants.run_defense_matchup,
        constants.explosive_play_matchup, constants.pass_matchup_conversion,
        constants.run_matchup_conversion,
    )

    # ---- HFA Delta + Road Fatigue Adj (home-team-specific) -------------------------------
    hfa_result = resolve_team_specific_hfa_for_game(
        bundle.sched_3yr_prior, target_season, home_team, constants.team_specific_hfa,
    )
    home_hfa_delta_value = hfa_delta_home(hfa_result.regressed_hfa, constants.flat_hfa)
    away_hfa_delta_value = hfa_delta_away(home_hfa_delta_value)

    home_road_games = resolve_consecutive_road_games(
        bundle.sched_current_season, target_season, target_week, home_abbr,
    )
    away_road_games = resolve_consecutive_road_games(
        bundle.sched_current_season, target_season, target_week, away_abbr,
    )
    home_road_fatigue = _road_fatigue_adj_fn(
        home_road_games, constants.road_fatigue_threshold, constants.road_fatigue_penalty,
    )
    away_road_fatigue = _road_fatigue_adj_fn(
        away_road_games, constants.road_fatigue_threshold, constants.road_fatigue_penalty,
    )

    # ---- Travel Effect / Travel Direction Adj (away side only) --------------------------
    if travel_effect_away is None:
        away_travel_miles = resolve_travel_effect_miles(away_team, home_team, game_row)
        travel_effect_away = travel_effect(away_travel_miles, constants.travel_coefficient)
    if travel_direction_away is None:
        home_utc, away_utc = resolve_travel_direction_offsets(home_team, away_team)
        travel_direction_away = travel_direction_adj(
            home_utc, away_utc, constants.west_to_east_penalty,
        )

    return compute_model_home_away_score(
        base_team_quality_home=home_base_quality,
        base_team_quality_away=away_base_quality,
        flat_hfa=constants.flat_hfa,
        rest_effect_value=rest_effect_value,
        weather_adj_value=weather_adj_value,
        injury_adj_home=injury_adj_home,
        injury_adj_away=injury_adj_away,
        division_adj_value=division_adj_value,
        qb_replacement_home=qb_replacement_home,
        qb_replacement_away=qb_replacement_away,
        phase_matchup_home=phase_matchup_home,
        phase_matchup_away=phase_matchup_away,
        ol_pressure_home=ol_pressure_home,
        ol_pressure_away=ol_pressure_away,
        explosive_play_home=explosive_play_home,
        explosive_play_away=explosive_play_away,
        hfa_delta_home=home_hfa_delta_value,
        hfa_delta_away=away_hfa_delta_value,
        road_fatigue_home=home_road_fatigue,
        road_fatigue_away=away_road_fatigue,
        travel_effect_away=travel_effect_away,
        travel_direction_away=travel_direction_away,
    )
