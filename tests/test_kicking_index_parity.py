"""
Parity test for prediction_audit/engine/kicking_index.py against v35's own real recalculated
Kicking Index values -- 32 real kickers, 3 real metrics.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.kicking_index import (  # noqa: E402
    METRIC_KEYS,
    KickerHistory,
    KickingIndexConstants,
    compute_kicking_index,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_kicking_index_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> KickingIndexConstants:
    c = GROUND_TRUTH["constants"]
    return KickingIndexConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"], blend_base=c["blend_base"],
        blend_per_game=c["blend_per_game"], blend_cap=c["blend_cap"],
        weights=c["weights"], score_baseline=c["score_baseline"],
        points_per_sd=c["points_per_sd"], league_avg=c["league_avg"],
        league_std=c["league_std"],
    )


def _history(k: dict) -> KickerHistory:
    return KickerHistory(
        player_id=k["player_id"],
        y1={m: k[f"{m}_y1"] for m in METRIC_KEYS},
        y2={m: k[f"{m}_y2"] for m in METRIC_KEYS},
        y3={m: k[f"{m}_y3"] for m in METRIC_KEYS},
        league_baseline_y1={m: k[f"{m}_league_baseline_y1"] for m in METRIC_KEYS},
        games_played=int(k["games_played"]),
        current_season={m: k[f"current_season_{m}"] for m in METRIC_KEYS},
    )


def test_ground_truth_has_all_32_kickers():
    assert len(GROUND_TRUTH["kickers"]) == 32


@pytest.mark.parametrize(
    "kicker", GROUND_TRUTH["kickers"], ids=[k["player_id"] for k in GROUND_TRUTH["kickers"]],
)
def test_kicking_index_parity_full_chain(kicker):
    constants = _constants()
    history = _history(kicker)
    result = compute_kicking_index(history, constants)

    for m in METRIC_KEYS:
        assert result.proj_baseline[m] == pytest.approx(
            kicker[f"excel_{m}_proj_baseline"], abs=1e-6
        ), f"{kicker['player_name']} {m} Projected Baseline mismatch"

    assert result.blend_weight == pytest.approx(kicker["excel_blend_weight"], abs=1e-6), (
        f"{kicker['player_name']} Blend Weight mismatch"
    )

    for m in METRIC_KEYS:
        assert result.blended[m] == pytest.approx(
            kicker[f"excel_{m}_blended"], abs=1e-6
        ), f"{kicker['player_name']} {m} Blended value mismatch"
        assert result.z_scores[m] == pytest.approx(
            kicker[f"excel_{m}_z"], abs=1e-6
        ), f"{kicker['player_name']} {m} Z-score mismatch"

    assert result.weighted_zsum == pytest.approx(kicker["excel_weighted_zsum"], abs=1e-6), (
        f"{kicker['player_name']} Weighted Z-Sum mismatch"
    )
    assert result.score == pytest.approx(kicker["excel_score"], abs=1e-6), (
        f"{kicker['player_name']} Kicking Index Score mismatch: "
        f"Python={result.score}, Excel={kicker['excel_score']}"
    )
