"""
Parity test for prediction_audit/engine/market_comparison.py against v35's own real Win
Probability (Home) values -- all 272 real games, computed from the same real Model Home/Away
Score already proven in test_season_matchups_full_reconstruction.py.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.market_comparison import win_probability_home  # noqa: E402

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_win_probability_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _game_id(g: dict) -> str:
    return f"wk{g['week']}_{g['away']}_at_{g['home']}".replace(" ", "")


def test_ground_truth_has_all_272_games():
    assert len(GROUND_TRUTH["games"]) == 272


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_win_probability_home_parity(game):
    slope = GROUND_TRUTH["constants"]["win_prob_logistic_slope"]
    margin = game["excel_home_projected_score"] - game["excel_away_projected_score"]
    result = win_probability_home(margin, slope)
    assert result == pytest.approx(game["excel_win_probability_home"], abs=1e-6), (
        f"{_game_id(game)} Win Probability (Home) mismatch: Python={result}, "
        f"Excel={game['excel_win_probability_home']}"
    )


def test_win_probability_home_is_50_50_at_zero_margin():
    assert win_probability_home(0.0, 10.5) == pytest.approx(0.5, abs=1e-9)


def test_win_probability_home_increases_with_margin():
    assert win_probability_home(10.0, 10.5) > win_probability_home(0.0, 10.5)
    assert win_probability_home(-10.0, 10.5) < win_probability_home(0.0, 10.5)
