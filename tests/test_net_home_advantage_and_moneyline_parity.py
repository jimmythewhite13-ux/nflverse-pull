"""
Parity test for prediction_audit/engine/net_home_advantage.py and
market_comparison.model_win_probability_to_moneyline() against v35's own real recalculated
Market Comparison & Confidence values -- all 272 real games.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.market_comparison import (  # noqa: E402
    model_win_probability_to_moneyline,
)
from prediction_audit.engine.net_home_advantage import (  # noqa: E402
    hfa_delta_net_home_adv,
    injury_net_home_adv,
    qb_replacement_net_home_adv,
    rest_net_home_adv,
    road_fatigue_net_home_adv,
    travel_direction_net_home_adv,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_net_home_advantage_and_ml_ground_truth.json"
)
CORE_SIMPLE_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_core_simple_terms_ground_truth.json"
)
HFA_TRAVEL_FATIGUE_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_hfa_delta_travel_fatigue_ground_truth.json"
)
TRAVEL_DIRECTION_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_travel_direction_ground_truth.json"
)


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load(GROUND_TRUTH_PATH)
CORE_SIMPLE_BY_KEY = {
    (g["week"], g["away"], g["home"]): g for g in _load(CORE_SIMPLE_PATH)["games"]
}
HFA_TRAVEL_FATIGUE_BY_KEY = {
    (g["week"], g["away"], g["home"]): g for g in _load(HFA_TRAVEL_FATIGUE_PATH)["games"]
}
TRAVEL_DIRECTION_BY_KEY = {
    (g["week"], g["away"], g["home"]): g for g in _load(TRAVEL_DIRECTION_PATH)["games"]
}


def _game_id(g: dict) -> str:
    return f"wk{g['week']}_{g['away']}_at_{g['home']}".replace(" ", "")


def test_ground_truth_has_all_272_games():
    assert len(GROUND_TRUTH["games"]) == 272


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_net_home_advantage_parity(game):
    key = (game["week"], game["away"], game["home"])
    core = CORE_SIMPLE_BY_KEY[key]
    hfa_travel = HFA_TRAVEL_FATIGUE_BY_KEY[key]
    travel_dir = TRAVEL_DIRECTION_BY_KEY[key]

    rest = rest_net_home_adv(core["excel_rest_effect"])
    assert rest == pytest.approx(game["excel_rest_net_v"], abs=1e-6)

    injury = injury_net_home_adv(
        hfa_travel["excel_home_injury_adj"], hfa_travel["excel_away_injury_adj"],
    )
    assert injury == pytest.approx(game["excel_injury_net_w"], abs=1e-6)

    qb_repl = qb_replacement_net_home_adv(
        core["excel_qb_repl_home"], core["excel_qb_repl_away"],
    )
    assert qb_repl == pytest.approx(game["excel_qb_repl_net_x"], abs=1e-6)

    # HFA Delta's own home/away values are already proven correct in
    # test_core_formula_simple_terms_parity.py; reused here directly rather than re-deriving.
    hfa_net = hfa_delta_net_home_adv(
        hfa_travel["excel_home_hfa_delta"], hfa_travel["excel_away_hfa_delta"],
    )
    assert hfa_net == pytest.approx(game["excel_hfa_delta_net_ab"], abs=1e-6), (
        f"{_game_id(game)} HFA Delta Net Home Adv mismatch"
    )

    road_fatigue = road_fatigue_net_home_adv(
        hfa_travel["excel_home_road_fatigue_adj"], hfa_travel["excel_away_road_fatigue_adj"],
    )
    assert road_fatigue == pytest.approx(game["excel_road_fatigue_net_ac"], abs=1e-6)

    travel_direction = travel_direction_net_home_adv(
        travel_dir["excel_da_travel_direction_adj"],
    )
    assert travel_direction == pytest.approx(game["excel_travel_direction_net_ad"], abs=1e-6), (
        f"{_game_id(game)} Travel Direction Net Home Adv mismatch"
    )


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_model_win_probability_to_moneyline_parity(game):
    wp_home = game["excel_win_probability_home"]
    home_ml = model_win_probability_to_moneyline(wp_home)
    away_ml = model_win_probability_to_moneyline(1 - wp_home)

    assert home_ml == pytest.approx(game["excel_model_wp_to_ml_home_bb"], abs=1e-6), (
        f"{_game_id(game)} Model WP->ML (Home) mismatch: Python={home_ml}, "
        f"Excel={game['excel_model_wp_to_ml_home_bb']}"
    )
    assert away_ml == pytest.approx(game["excel_model_wp_to_ml_away_bc"], abs=1e-6), (
        f"{_game_id(game)} Model WP->ML (Away) mismatch"
    )


def test_model_win_probability_to_moneyline_50_50_edge_case():
    # Excel's own real formula routes exactly 0.5 to the ">=0.5" (favorite) branch.
    assert model_win_probability_to_moneyline(0.5) == pytest.approx(-100.0, abs=1e-9)
