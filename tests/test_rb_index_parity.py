"""
Parity test for prediction_audit/engine/rb_index.py against v35's own real recalculated RB
Value Index values -- mirrors test_qb_index_parity.py's own structure, generalized to 5
metrics (Rushing EPA/Play, Rushing Success Rate, YPC, RYOE/Att NGS, Red-Zone Carry Share).

Ground truth (v35_rb_index_ground_truth.json) extracted the same way: a real LibreOffice
recalculation of the frozen v35 baseline, every real current-roster RB's real inputs and
Excel's own real computed values at every step, including RYOE/Att -- whose own real Y-1/Y-2/
Y-3 values already reflect v35's own partial-coverage substitution logic (an extra real
existence check + ISBLANK-guarded rookie fallback, confirmed in rb_index.py's own docstring),
which this test does not re-derive -- it uses Excel's own already-resolved values as input,
same scoping as every other metric.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.rb_index import (  # noqa: E402
    METRIC_KEYS,
    RBHistory,
    RBIndexConstants,
    compute_rb_index,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_rb_index_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> RBIndexConstants:
    c = GROUND_TRUTH["constants"]
    return RBIndexConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"], blend_base=c["blend_base"],
        blend_per_game=c["blend_per_game"], blend_cap=c["blend_cap"],
        weights=c["weights"], score_baseline=c["score_baseline"],
        points_per_sd=c["points_per_sd"], league_avg=c["league_avg"],
        league_std=c["league_std"],
    )


def _history(rb: dict) -> RBHistory:
    return RBHistory(
        player_id=rb["player_id"],
        y1={m: rb[f"{m}_y1"] for m in METRIC_KEYS},
        y2={m: rb[f"{m}_y2"] for m in METRIC_KEYS},
        y3={m: rb[f"{m}_y3"] for m in METRIC_KEYS},
        league_baseline_y1={m: rb[f"{m}_league_baseline_y1"] for m in METRIC_KEYS},
        games_played=int(rb["games_played"]),
        current_season={m: rb[f"current_season_{m}"] for m in METRIC_KEYS},
    )


def test_ground_truth_has_real_rbs():
    assert len(GROUND_TRUTH["rbs"]) == 64
    assert GROUND_TRUTH["rbs"][0]["player_name"]


@pytest.mark.parametrize(
    "rb", GROUND_TRUTH["rbs"], ids=[r["player_id"] for r in GROUND_TRUTH["rbs"]],
)
def test_rb_index_parity_full_chain(rb):
    constants = _constants()
    history = _history(rb)
    result = compute_rb_index(history, constants)

    for m in METRIC_KEYS:
        assert result.proj_baseline[m] == pytest.approx(
            rb[f"excel_{m}_proj_baseline"], abs=1e-6
        ), f"{rb['player_name']} {m} Projected Baseline mismatch"

    assert result.blend_weight == pytest.approx(rb["excel_blend_weight"], abs=1e-6), (
        f"{rb['player_name']} Blend Weight mismatch"
    )

    for m in METRIC_KEYS:
        assert result.blended[m] == pytest.approx(rb[f"excel_{m}_blended"], abs=1e-6), (
            f"{rb['player_name']} {m} Blended value mismatch"
        )
        assert result.z_scores[m] == pytest.approx(rb[f"excel_{m}_z"], abs=1e-6), (
            f"{rb['player_name']} {m} Z-score mismatch"
        )

    assert result.weighted_zsum == pytest.approx(rb["excel_weighted_zsum"], abs=1e-6), (
        f"{rb['player_name']} Weighted Z-Sum mismatch"
    )
    assert result.score == pytest.approx(rb["excel_score"], abs=1e-6), (
        f"{rb['player_name']} RB Index Score mismatch: "
        f"Python={result.score}, Excel={rb['excel_score']}"
    )


def test_all_metric_keys_covered():
    assert set(METRIC_KEYS) == {"rushing_epa", "rushing_sr", "ypc", "ryoe", "rz_share"}
