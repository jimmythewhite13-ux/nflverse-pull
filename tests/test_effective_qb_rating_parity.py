"""
Parity test for prediction_audit/engine/effective_qb_rating.py against v35's own real
recalculated Season Matchups values -- all 272 real games, both home and away sides.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.effective_qb_rating import (  # noqa: E402
    effective_qb_rating,
    ol_modifier,
    weather_on_passing_modifier,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_effective_qb_rating_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def test_ground_truth_has_all_272_games():
    assert len(GROUND_TRUTH["games"]) == 272


def _game_id(g: dict) -> str:
    return f"wk{g['week']}_{g['away']}_at_{g['home']}".replace(" ", "")


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_ol_modifier_parity(game):
    scaling = GROUND_TRUTH["constants"]["ol_modifier_scaling"]
    home = ol_modifier(
        game["home_ol_pressure_diff_bk"], game["home_sack_rate_z_bs"], scaling,
    )
    away = ol_modifier(
        game["away_ol_pressure_diff_bn"], game["away_sack_rate_z_bt"], scaling,
    )
    assert home == pytest.approx(game["excel_home_ol_modifier_bu"], abs=1e-6), (
        f"{_game_id(game)} Home OL Modifier mismatch"
    )
    assert away == pytest.approx(game["excel_away_ol_modifier_bv"], abs=1e-6), (
        f"{_game_id(game)} Away OL Modifier mismatch"
    )


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_weather_on_passing_modifier_parity(game):
    scaling = GROUND_TRUTH["constants"]["weather_passing_scaling"]
    home = weather_on_passing_modifier(
        game["weather_adj_u"], game["home_team_pass_rate_bq"], scaling,
    )
    away = weather_on_passing_modifier(
        game["weather_adj_u"], game["away_team_pass_rate_br"], scaling,
    )
    assert home == pytest.approx(game["excel_home_weather_passing_mod_bw"], abs=1e-6)
    assert away == pytest.approx(game["excel_away_weather_passing_mod_bx"], abs=1e-6)


def test_weather_on_passing_modifier_nonzero_weather_case():
    # No real game in the current snapshot has a non-Dome nonzero Weather Adj (see
    # core_formula_simple_terms.py's own module docstring), so this exercises the real
    # multiplication directly rather than a real ground-truth row.
    assert weather_on_passing_modifier(-3.0, 0.6, 0.5) == pytest.approx(-0.9, abs=1e-9)
    assert weather_on_passing_modifier(-3.0, None, 0.5) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_effective_qb_rating_parity(game):
    scaling_ol = GROUND_TRUTH["constants"]["ol_modifier_scaling"]
    scaling_wx = GROUND_TRUTH["constants"]["weather_passing_scaling"]

    home_ol = ol_modifier(
        game["home_ol_pressure_diff_bk"], game["home_sack_rate_z_bs"], scaling_ol,
    )
    home_wx = weather_on_passing_modifier(
        game["weather_adj_u"], game["home_team_pass_rate_bq"], scaling_wx,
    )
    home_rating = effective_qb_rating(game["home_qb_env_adj_baseline_by"], home_ol, home_wx)

    away_ol = ol_modifier(
        game["away_ol_pressure_diff_bn"], game["away_sack_rate_z_bt"], scaling_ol,
    )
    away_wx = weather_on_passing_modifier(
        game["weather_adj_u"], game["away_team_pass_rate_br"], scaling_wx,
    )
    away_rating = effective_qb_rating(game["away_qb_env_adj_baseline_bz"], away_ol, away_wx)

    assert home_rating == pytest.approx(
        game["excel_home_effective_qb_rating_ca"], abs=1e-6
    ), (
        f"{_game_id(game)} Home Effective QB Rating mismatch: Python={home_rating}, "
        f"Excel={game['excel_home_effective_qb_rating_ca']}"
    )
    assert away_rating == pytest.approx(
        game["excel_away_effective_qb_rating_cb"], abs=1e-6
    ), (
        f"{_game_id(game)} Away Effective QB Rating mismatch: Python={away_rating}, "
        f"Excel={game['excel_away_effective_qb_rating_cb']}"
    )


def test_effective_qb_rating_blank_baseline_returns_none():
    assert effective_qb_rating(None, 1.0, 0.5) is None
    assert effective_qb_rating("", 1.0, 0.5) is None
