"""
Parity test for prediction_audit/engine/lb_index.py against v35's own real recalculated LB
Index values -- 192 real players, 2 real metrics, no blend step.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.lb_index import (  # noqa: E402
    METRIC_KEYS,
    LBIndexConstants,
    LBPlayerHistory,
    compute_lb_index,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_lb_index_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> LBIndexConstants:
    c = GROUND_TRUTH["constants"]
    return LBIndexConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"], weights=c["weights"],
        score_baseline=c["score_baseline"], points_per_sd=c["points_per_sd"],
        league_avg=c["league_avg"], league_std=c["league_std"],
    )


def _history(p: dict) -> LBPlayerHistory:
    return LBPlayerHistory(
        player_id=p["player_id"],
        y1={m: p[f"{m}_y1"] for m in METRIC_KEYS},
        y2={m: p[f"{m}_y2"] for m in METRIC_KEYS},
        y3={m: p[f"{m}_y3"] for m in METRIC_KEYS},
        league_baseline_y1={m: p[f"{m}_league_baseline_y1"] for m in METRIC_KEYS},
    )


def test_ground_truth_has_real_players():
    assert len(GROUND_TRUTH["players"]) == 192


@pytest.mark.parametrize(
    "player", GROUND_TRUTH["players"], ids=[p["player_id"] for p in GROUND_TRUTH["players"]],
)
def test_lb_index_parity_full_chain(player):
    constants = _constants()
    history = _history(player)
    result = compute_lb_index(history, constants)

    for m in METRIC_KEYS:
        assert result.proj_baseline[m] == pytest.approx(
            player[f"excel_{m}_proj_baseline"], abs=1e-6
        ), f"{player['player_name']} {m} Projected Baseline mismatch"
        assert result.z_scores[m] == pytest.approx(
            player[f"excel_{m}_z"], abs=1e-6
        ), f"{player['player_name']} {m} Z-score mismatch"

    assert result.weighted_zsum == pytest.approx(player["excel_weighted_zsum"], abs=1e-6), (
        f"{player['player_name']} Weighted Z-Sum mismatch"
    )
    assert result.score == pytest.approx(player["excel_score"], abs=1e-6), (
        f"{player['player_name']} LB Index Score mismatch: "
        f"Python={result.score}, Excel={player['excel_score']}"
    )
