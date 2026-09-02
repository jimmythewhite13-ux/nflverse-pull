"""
Parity test for prediction_audit/engine/core_formula_simple_terms.py against v35's own real
recalculated Season Matchups values -- all 272 real games, ten simple direct-arithmetic Z/AA
components (Rest Effect, Weather Adj, Division Adj, QB Replacement Value, Phase Matchup Adj,
OL Pressure Adj, Travel Effect, HFA Delta, Road Fatigue Adj, Injury Adj). Unlike every other
tab's parity test, these take already-resolved real differentials/flags as given inputs (per
this project's "arithmetic only, not data sourcing" scoping) rather than chaining decay/blend/
Z-score steps themselves.
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

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_core_simple_terms_ground_truth.json"
)
HFA_TRAVEL_FATIGUE_GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_hfa_delta_travel_fatigue_ground_truth.json"
)
TRAVEL_DIRECTION_GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_travel_direction_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_hfa_travel_fatigue_ground_truth() -> dict:
    with open(HFA_TRAVEL_FATIGUE_GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_travel_direction_ground_truth() -> dict:
    with open(TRAVEL_DIRECTION_GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()
HFA_TRAVEL_FATIGUE_GROUND_TRUTH = _load_hfa_travel_fatigue_ground_truth()
TRAVEL_DIRECTION_GROUND_TRUTH = _load_travel_direction_ground_truth()


def _rest_constants() -> RestEffectConstants:
    c = GROUND_TRUTH["constants"]
    return RestEffectConstants(
        low_threshold=c["rest_low_threshold"], high_threshold=c["rest_high_threshold"],
        low_val=c["rest_low_val"], mid_val=c["rest_mid_val"], high_val=c["rest_high_val"],
    )


def _weather_constants() -> WeatherAdjConstants:
    c = GROUND_TRUTH["constants"]
    return WeatherAdjConstants(
        wind_threshold=c["wind_threshold"], wind_adj=c["wind_adj"],
        cold_threshold=c["cold_threshold"], cold_adj=c["cold_adj"],
        precip_adj=c["precip_adj"], snow_adj=c["snow_adj"],
        humidity_threshold=c["humidity_threshold"], humidity_adj=c["humidity_adj"],
    )


def test_ground_truth_has_all_272_games():
    assert len(GROUND_TRUTH["games"]) == 272


def _game_id(g: dict) -> str:
    return f"wk{g['week']}_{g['away']}_at_{g['home']}".replace(" ", "")


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_rest_effect_parity(game):
    c = _rest_constants()
    result = rest_effect(game["home_rest"], game["away_rest"], c)
    assert result == pytest.approx(game["excel_rest_effect"], abs=1e-6), (
        f"{_game_id(game)} Rest Effect mismatch: Python={result}, "
        f"Excel={game['excel_rest_effect']}"
    )


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_weather_adj_parity(game):
    c = _weather_constants()
    result = weather_adj(
        game["is_dome"], game["snow_flag"], game["precip_flag"],
        game["wind"], game["temp"], game["humidity"], c,
    )
    assert result == pytest.approx(game["excel_weather_adj"], abs=1e-6), (
        f"{_game_id(game)} Weather Adj mismatch: Python={result}, "
        f"Excel={game['excel_weather_adj']}"
    )


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_division_adj_parity(game):
    const = GROUND_TRUTH["constants"]["division_adj"]
    result = division_adj(game["is_divisional"], const)
    assert result == pytest.approx(game["excel_division_adj"], abs=1e-6), (
        f"{_game_id(game)} Division Adj mismatch: Python={result}, "
        f"Excel={game['excel_division_adj']}"
    )


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_qb_replacement_adj_parity(game):
    # Real snapshot has no "Backup In" games (see module docstring) -- replacement_value of 0
    # is passed since no real Starter/Backup differential exists to source in that case; the
    # branch that negates a nonzero value is exercised by test_qb_replacement_adj_backup_case.
    home = qb_replacement_adj(game["home_backup_in"], 0.0)
    away = qb_replacement_adj(game["away_backup_in"], 0.0)
    assert home == pytest.approx(game["excel_qb_repl_home"], abs=1e-6), (
        f"{_game_id(game)} home QB Replacement Value mismatch"
    )
    assert away == pytest.approx(game["excel_qb_repl_away"], abs=1e-6), (
        f"{_game_id(game)} away QB Replacement Value mismatch"
    )


def test_qb_replacement_adj_backup_case():
    # No real "Backup In" game exists in the current snapshot (see module docstring), so this
    # exercises the negation branch directly against the real formula logic rather than a real
    # ground-truth row: IF(AQ="Backup In", -replacement_value, 0).
    assert qb_replacement_adj("Backup In", 4.25) == pytest.approx(-4.25, abs=1e-6)
    assert qb_replacement_adj("Starter In", 4.25) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_phase_matchup_adj_parity(game):
    pass_conv = GROUND_TRUTH["constants"]["pass_conv"]
    run_conv = GROUND_TRUTH["constants"]["run_conv"]
    home_pass_adj, away_pass_adj = phase_matchup_adj(
        game["home_pass_diff"], game["away_pass_diff"], pass_conv,
    )
    home_run_adj, away_run_adj = phase_matchup_adj(
        game["home_run_diff"], game["away_run_diff"], run_conv,
    )
    home_total = home_pass_adj + home_run_adj
    away_total = away_pass_adj + away_run_adj
    assert home_total == pytest.approx(game["excel_phase_home"], abs=1e-6), (
        f"{_game_id(game)} home Phase Matchup Adj mismatch: Python={home_total}, "
        f"Excel={game['excel_phase_home']}"
    )
    assert away_total == pytest.approx(game["excel_phase_away"], abs=1e-6), (
        f"{_game_id(game)} away Phase Matchup Adj mismatch: Python={away_total}, "
        f"Excel={game['excel_phase_away']}"
    )


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_ol_pressure_adj_parity(game):
    conv = GROUND_TRUTH["constants"]["ol_press_conv"]
    home_result = ol_pressure_adj(game["home_ol_press_diff"], conv)
    away_result = ol_pressure_adj(game["away_ol_press_diff"], conv)
    assert home_result == pytest.approx(game["excel_ol_press_home"], abs=1e-6), (
        f"{_game_id(game)} home OL Pressure Adj mismatch: Python={home_result}, "
        f"Excel={game['excel_ol_press_home']}"
    )
    assert away_result == pytest.approx(game["excel_ol_press_away"], abs=1e-6), (
        f"{_game_id(game)} away OL Pressure Adj mismatch: Python={away_result}, "
        f"Excel={game['excel_ol_press_away']}"
    )


def test_hfa_travel_fatigue_ground_truth_has_all_272_games():
    assert len(HFA_TRAVEL_FATIGUE_GROUND_TRUTH["games"]) == 272


@pytest.mark.parametrize(
    "game", HFA_TRAVEL_FATIGUE_GROUND_TRUTH["games"],
    ids=[_game_id(g) for g in HFA_TRAVEL_FATIGUE_GROUND_TRUTH["games"]],
)
def test_travel_effect_parity(game):
    coeff = HFA_TRAVEL_FATIGUE_GROUND_TRUTH["constants"]["travel_coefficient"]
    result = travel_effect(game["away_travel_miles"], coeff)
    assert result == pytest.approx(game["excel_travel_effect"], abs=1e-6), (
        f"{_game_id(game)} Travel Effect mismatch: Python={result}, "
        f"Excel={game['excel_travel_effect']}"
    )


@pytest.mark.parametrize(
    "game", HFA_TRAVEL_FATIGUE_GROUND_TRUTH["games"],
    ids=[_game_id(g) for g in HFA_TRAVEL_FATIGUE_GROUND_TRUTH["games"]],
)
def test_hfa_delta_parity(game):
    flat_hfa = HFA_TRAVEL_FATIGUE_GROUND_TRUTH["constants"]["hfa_flat"]
    home_delta = hfa_delta_home(game["home_regressed_hfa_ref"], flat_hfa)
    away_delta = hfa_delta_away(home_delta)
    assert home_delta == pytest.approx(game["excel_home_hfa_delta"], abs=1e-6), (
        f"{_game_id(game)} Home HFA Delta mismatch: Python={home_delta}, "
        f"Excel={game['excel_home_hfa_delta']}"
    )
    assert away_delta == pytest.approx(game["excel_away_hfa_delta"], abs=1e-6), (
        f"{_game_id(game)} Away HFA Delta mismatch: Python={away_delta}, "
        f"Excel={game['excel_away_hfa_delta']}"
    )


@pytest.mark.parametrize(
    "game", HFA_TRAVEL_FATIGUE_GROUND_TRUTH["games"],
    ids=[_game_id(g) for g in HFA_TRAVEL_FATIGUE_GROUND_TRUTH["games"]],
)
def test_road_fatigue_adj_parity(game):
    c = HFA_TRAVEL_FATIGUE_GROUND_TRUTH["constants"]
    home_result = road_fatigue_adj(
        game["home_consec_road_games"], c["road_games_threshold"], c["road_games_penalty"],
    )
    away_result = road_fatigue_adj(
        game["away_consec_road_games"], c["road_games_threshold"], c["road_games_penalty"],
    )
    assert home_result == pytest.approx(game["excel_home_road_fatigue_adj"], abs=1e-6), (
        f"{_game_id(game)} Home Road Fatigue Adj mismatch"
    )
    assert away_result == pytest.approx(game["excel_away_road_fatigue_adj"], abs=1e-6), (
        f"{_game_id(game)} Away Road Fatigue Adj mismatch"
    )


def test_road_fatigue_adj_triggers_above_threshold():
    # No real game in the current snapshot reaches the 3-game threshold (max observed: 2 --
    # see module docstring), so this exercises the trigger branch directly against the real
    # formula logic rather than a real ground-truth row.
    assert road_fatigue_adj(3, 3, -1) == pytest.approx(-1.0, abs=1e-6)
    assert road_fatigue_adj(4, 3, -1) == pytest.approx(-1.0, abs=1e-6)
    assert road_fatigue_adj(2, 3, -1) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize(
    "game", HFA_TRAVEL_FATIGUE_GROUND_TRUTH["games"],
    ids=[_game_id(g) for g in HFA_TRAVEL_FATIGUE_GROUND_TRUTH["games"]],
)
def test_injury_adj_parity(game):
    result = injury_adj()
    assert result == pytest.approx(game["excel_home_injury_adj"], abs=1e-6)
    assert result == pytest.approx(game["excel_away_injury_adj"], abs=1e-6)


def test_travel_direction_ground_truth_has_all_272_games():
    assert len(TRAVEL_DIRECTION_GROUND_TRUTH["games"]) == 272


@pytest.mark.parametrize(
    "game", TRAVEL_DIRECTION_GROUND_TRUTH["games"],
    ids=[_game_id(g) for g in TRAVEL_DIRECTION_GROUND_TRUTH["games"]],
)
def test_travel_direction_adj_parity(game):
    penalty = TRAVEL_DIRECTION_GROUND_TRUTH["constants"]["west_to_east_penalty"]
    result = travel_direction_adj(game["home_utc_offset"], game["away_utc_offset"], penalty)
    assert result == pytest.approx(game["excel_da_travel_direction_adj"], abs=1e-6), (
        f"{_game_id(game)} Travel Direction Adj mismatch: Python={result}, "
        f"Excel={game['excel_da_travel_direction_adj']}"
    )
