"""
Full end-to-end reconstruction test: composes every real Z/AA term (each already individually
proven correct in its own parity test) via season_matchups.compute_model_home_away_score() and
checks the result against v35's own real Model Home/Away Score (Z/AA) for all 272 real games.

This is the culminating integration proof for the "simple arithmetic" and "team quality" and
"explosive play matchup" phases of the Python Model Engine: every term is computed fresh from
real per-team/per-game ground truth (not read pre-summed from Excel), summed exactly as the
real Z/AA formula does, and checked against the real final cell value -- not just each term in
isolation (already covered by test_core_formula_simple_terms_parity.py,
test_team_quality_parity.py, and test_explosive_play_matchup_parity.py).

Per this project's established "arithmetic only, not data sourcing" scoping, a handful of
upstream real inputs are still taken as given rather than re-derived from their own source
tabs in this pass (Phase Matchup / OL Pressure differentials, QB Replacement Values, per-team
UTC offsets, Consecutive Road Games counts) -- see core_formula_simple_terms.py's own module
docstring. Base Team Quality and Explosive Play Matchup ARE fully re-derived here from their
own real per-team ground truth via the already-ported engine functions, not read pre-summed.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.core_formula_simple_terms import (  # noqa: E402
    RestEffectConstants,
    WeatherAdjConstants,
    division_adj,
    hfa_delta_away,
    hfa_delta_home,
    injury_adj,
    ol_pressure_adj,
    phase_matchup_adj,
    qb_replacement_adj,
    rest_effect,
    road_fatigue_adj,
    travel_direction_adj,
    travel_effect,
    weather_adj,
)
from prediction_audit.engine.explosive_play_matchup import (  # noqa: E402
    ExplosivePlayMatchupConstants,
    ExplosivePlayMatchupTeamHistory,
    compute_explosive_play_matchup,
    explosive_play_matchup_adj,
)
from prediction_audit.engine.season_matchups import compute_model_home_away_score  # noqa: E402
from prediction_audit.engine.team_quality import (  # noqa: E402
    TeamQualityConstants,
    TeamQualityTeamHistory,
    base_team_quality,
    compute_team_quality,
)

MANIFESTS = Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"


def _load(name: str) -> dict:
    with open(MANIFESTS / name, encoding="utf-8") as f:
        return json.load(f)


CORE_SIMPLE = _load("v35_core_simple_terms_ground_truth.json")
HFA_TRAVEL_FATIGUE = _load("v35_hfa_delta_travel_fatigue_ground_truth.json")
TRAVEL_DIRECTION = _load("v35_travel_direction_ground_truth.json")
TEAM_QUALITY = _load("v35_team_quality_ground_truth.json")
EXPLOSIVE = _load("v35_explosive_play_matchup_ground_truth.json")
MODEL_SCORE = _load("v35_model_home_away_score_ground_truth.json")


def _key(g: dict) -> tuple:
    return (g["week"], g["away"], g["home"])


CORE_SIMPLE_BY_KEY = {_key(g): g for g in CORE_SIMPLE["games"]}
HFA_TRAVEL_FATIGUE_BY_KEY = {_key(g): g for g in HFA_TRAVEL_FATIGUE["games"]}
TRAVEL_DIRECTION_BY_KEY = {_key(g): g for g in TRAVEL_DIRECTION["games"]}


def _team_quality_by_team() -> dict:
    c = TEAM_QUALITY["constants"]
    constants = TeamQualityConstants(
        decay_factor=c["decay_factor"], last_year_emphasis=c["last_year_emphasis"],
        regression_weight=c["regression_weight"], blend_base=c["blend_base"],
        blend_per_game=c["blend_per_game"], blend_cap=c["blend_cap"],
    )
    out = {}
    for t in TEAM_QUALITY["teams"]:
        history = TeamQualityTeamHistory(
            team=t["team"],
            off_y1=t["off_y1"], off_y2=t["off_y2"], off_y3=t["off_y3"],
            def_y1=t["def_y1"], def_y2=t["def_y2"], def_y3=t["def_y3"],
            league_baseline_off_y1=t["league_baseline_off_y1"],
            league_baseline_def_y1=t["league_baseline_def_y1"],
            current_season_off_ppg=t["current_season_off_ppg"],
            current_season_def_ppg=t["current_season_def_ppg"],
            games_played=t["games_played"],
        )
        out[t["team"]] = compute_team_quality(history, constants)
    return out


def _explosive_by_team() -> dict:
    c = EXPLOSIVE["constants"]
    constants = ExplosivePlayMatchupConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"],
        league_avg_pass_off=c["league_avg_pass_off"], league_std_pass_off=c["league_std_pass_off"],
        league_avg_run_off=c["league_avg_run_off"], league_std_run_off=c["league_std_run_off"],
        league_avg_deep_pass_allowed=c["league_avg_deep_pass_allowed"],
        league_std_deep_pass_allowed=c["league_std_deep_pass_allowed"],
        league_avg_yac_allowed=c["league_avg_yac_allowed"],
        league_std_yac_allowed=c["league_std_yac_allowed"],
        pass_prevention_w_explosive_pass_allowed=c["pass_prevention_w_explosive_pass_allowed"],
        pass_prevention_w_deep_pass_allowed=c["pass_prevention_w_deep_pass_allowed"],
        pass_prevention_w_yac_allowed=c["pass_prevention_w_yac_allowed"],
    )
    sec5_by_team = {t["team"]: t for t in EXPLOSIVE["section5"]}
    out = {}
    for t in EXPLOSIVE["teams"]:
        sec5 = sec5_by_team[t["team"]]
        history = ExplosivePlayMatchupTeamHistory(
            team=t["team"],
            pass_off_y1=t["pass_off_y1"], pass_off_y2=t["pass_off_y2"],
            pass_off_y3=t["pass_off_y3"],
            pass_off_league_baseline_y1=t["pass_off_league_baseline_y1"],
            run_off_y1=t["run_off_y1"], run_off_y2=t["run_off_y2"], run_off_y3=t["run_off_y3"],
            run_off_league_baseline_y1=t["run_off_league_baseline_y1"],
            deep_pass_allowed_y1=t["deep_pass_allowed_y1"],
            deep_pass_allowed_y2=t["deep_pass_allowed_y2"],
            deep_pass_allowed_y3=t["deep_pass_allowed_y3"],
            deep_pass_allowed_league_baseline_y1=t["deep_pass_allowed_league_baseline_y1"],
            yac_allowed_y1=t["yac_allowed_y1"], yac_allowed_y2=t["yac_allowed_y2"],
            yac_allowed_y3=t["yac_allowed_y3"],
            yac_allowed_league_baseline_y1=t["yac_allowed_league_baseline_y1"],
            explosive_pass_allowed_z_ref=sec5["excel_explosive_pass_allowed_z_ref"],
            explosive_run_allowed_z_ref=sec5["excel_explosive_run_allowed_z_ref"],
        )
        out[t["team"]] = compute_explosive_play_matchup(history, constants)
    return out


TEAM_QUALITY_BY_TEAM = _team_quality_by_team()
EXPLOSIVE_BY_TEAM = _explosive_by_team()


def _game_id(g: dict) -> str:
    return f"wk{g['week']}_{g['away']}_at_{g['home']}".replace(" ", "")


def test_all_ground_truth_sources_cover_the_same_272_games():
    assert len(MODEL_SCORE["games"]) == 272
    for g in MODEL_SCORE["games"]:
        key = _key(g)
        assert key in CORE_SIMPLE_BY_KEY, f"{key} missing from core simple terms ground truth"
        assert key in HFA_TRAVEL_FATIGUE_BY_KEY, f"{key} missing from HFA/travel/fatigue GT"
        assert key in TRAVEL_DIRECTION_BY_KEY, f"{key} missing from travel direction ground truth"


@pytest.mark.parametrize(
    "game", MODEL_SCORE["games"], ids=[_game_id(g) for g in MODEL_SCORE["games"]],
)
def test_full_model_home_away_score_reconstruction(game):
    key = _key(game)
    core = CORE_SIMPLE_BY_KEY[key]
    hfa_travel = HFA_TRAVEL_FATIGUE_BY_KEY[key]
    travel_dir = TRAVEL_DIRECTION_BY_KEY[key]

    rest_c = RestEffectConstants(
        low_threshold=CORE_SIMPLE["constants"]["rest_low_threshold"],
        high_threshold=CORE_SIMPLE["constants"]["rest_high_threshold"],
        low_val=CORE_SIMPLE["constants"]["rest_low_val"],
        mid_val=CORE_SIMPLE["constants"]["rest_mid_val"],
        high_val=CORE_SIMPLE["constants"]["rest_high_val"],
    )
    weather_c = WeatherAdjConstants(
        wind_threshold=CORE_SIMPLE["constants"]["wind_threshold"],
        wind_adj=CORE_SIMPLE["constants"]["wind_adj"],
        cold_threshold=CORE_SIMPLE["constants"]["cold_threshold"],
        cold_adj=CORE_SIMPLE["constants"]["cold_adj"],
        precip_adj=CORE_SIMPLE["constants"]["precip_adj"],
        snow_adj=CORE_SIMPLE["constants"]["snow_adj"],
        humidity_threshold=CORE_SIMPLE["constants"]["humidity_threshold"],
        humidity_adj=CORE_SIMPLE["constants"]["humidity_adj"],
    )

    rest_effect_value = rest_effect(core["home_rest"], core["away_rest"], rest_c)
    weather_adj_value = weather_adj(
        core["is_dome"], core["snow_flag"], core["precip_flag"],
        core["wind"], core["temp"], core["humidity"], weather_c,
    )
    division_adj_value = division_adj(
        core["is_divisional"], CORE_SIMPLE["constants"]["division_adj"],
    )
    qb_repl_home = qb_replacement_adj(core["home_backup_in"], 0.0)
    qb_repl_away = qb_replacement_adj(core["away_backup_in"], 0.0)

    home_pass_adj, away_pass_adj = phase_matchup_adj(
        core["home_pass_diff"], core["away_pass_diff"], CORE_SIMPLE["constants"]["pass_conv"],
    )
    home_run_adj, away_run_adj = phase_matchup_adj(
        core["home_run_diff"], core["away_run_diff"], CORE_SIMPLE["constants"]["run_conv"],
    )
    phase_home = home_pass_adj + home_run_adj
    phase_away = away_pass_adj + away_run_adj

    ol_home = ol_pressure_adj(core["home_ol_press_diff"], CORE_SIMPLE["constants"]["ol_press_conv"])
    ol_away = ol_pressure_adj(core["away_ol_press_diff"], CORE_SIMPLE["constants"]["ol_press_conv"])

    travel_effect_away = travel_effect(
        hfa_travel["away_travel_miles"], HFA_TRAVEL_FATIGUE["constants"]["travel_coefficient"],
    )
    hfa_delta_h = hfa_delta_home(
        hfa_travel["home_regressed_hfa_ref"], HFA_TRAVEL_FATIGUE["constants"]["hfa_flat"],
    )
    hfa_delta_a = hfa_delta_away(hfa_delta_h)
    road_fatigue_home = road_fatigue_adj(
        hfa_travel["home_consec_road_games"],
        HFA_TRAVEL_FATIGUE["constants"]["road_games_threshold"],
        HFA_TRAVEL_FATIGUE["constants"]["road_games_penalty"],
    )
    road_fatigue_away = road_fatigue_adj(
        hfa_travel["away_consec_road_games"],
        HFA_TRAVEL_FATIGUE["constants"]["road_games_threshold"],
        HFA_TRAVEL_FATIGUE["constants"]["road_games_penalty"],
    )

    travel_direction_away = travel_direction_adj(
        travel_dir["home_utc_offset"], travel_dir["away_utc_offset"],
        TRAVEL_DIRECTION["constants"]["west_to_east_penalty"],
    )

    home_tq = TEAM_QUALITY_BY_TEAM[game["home"]]
    away_tq = TEAM_QUALITY_BY_TEAM[game["away"]]
    base_tq_home, base_tq_away = base_team_quality(
        home_tq.blended_off, away_tq.blended_def, away_tq.blended_off, home_tq.blended_def,
    )

    home_epm = EXPLOSIVE_BY_TEAM[game["home"]]
    away_epm = EXPLOSIVE_BY_TEAM[game["away"]]
    explosive_home, explosive_away = explosive_play_matchup_adj(
        home_epm.pass_off_z, away_epm.pass_prevention_composite_z,
        away_epm.pass_off_z, home_epm.pass_prevention_composite_z,
        home_epm.run_off_z, away_epm.run_prevention_z,
        away_epm.run_off_z, home_epm.run_prevention_z,
        EXPLOSIVE["constants"]["pass_conv"], EXPLOSIVE["constants"]["run_conv"],
    )

    model_home, model_away = compute_model_home_away_score(
        base_team_quality_home=base_tq_home,
        base_team_quality_away=base_tq_away,
        flat_hfa=MODEL_SCORE["constants"]["flat_hfa"],
        rest_effect_value=rest_effect_value,
        weather_adj_value=weather_adj_value,
        injury_adj_home=injury_adj(),
        injury_adj_away=injury_adj(),
        division_adj_value=division_adj_value,
        qb_replacement_home=qb_repl_home,
        qb_replacement_away=qb_repl_away,
        phase_matchup_home=phase_home,
        phase_matchup_away=phase_away,
        ol_pressure_home=ol_home,
        ol_pressure_away=ol_away,
        explosive_play_home=explosive_home,
        explosive_play_away=explosive_away,
        hfa_delta_home=hfa_delta_h,
        hfa_delta_away=hfa_delta_a,
        road_fatigue_home=road_fatigue_home,
        road_fatigue_away=road_fatigue_away,
        travel_effect_away=travel_effect_away,
        travel_direction_away=travel_direction_away,
    )

    assert model_home == pytest.approx(game["excel_Z_model_home_score"], abs=1e-6), (
        f"{_game_id(game)} Model Home Score mismatch: Python={model_home}, "
        f"Excel={game['excel_Z_model_home_score']}"
    )
    assert model_away == pytest.approx(game["excel_AA_model_away_score"], abs=1e-6), (
        f"{_game_id(game)} Model Away Score mismatch: Python={model_away}, "
        f"Excel={game['excel_AA_model_away_score']}"
    )
