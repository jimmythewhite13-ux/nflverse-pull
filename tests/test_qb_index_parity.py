"""
Parity test for the Python Model Engine's first fully-wired tab (prediction_audit/engine/
qb_index.py) against v35's own real recalculated QB Index values -- not synthetic examples.

Ground truth (prediction_audit/manifests/v35_qb_index_ground_truth.json) was extracted
directly from a real LibreOffice recalculation of the frozen v35 baseline: every real
current-roster QB's real Y-1/Y-2/Y-3 inputs, real league baselines, real games-played/
current-season blend inputs, and Excel's own real computed intermediate values and final
Score for all 64 real QBs. This test recomputes every one of those intermediate values in
pure Python and checks EXACT match (to floating-point tolerance) against Excel's own real
numbers -- not just the final Score, every step of the chain, so a mismatch points at exactly
which formula diverged rather than just "the total is wrong somewhere."
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.qb_index import (  # noqa: E402
    METRIC_KEYS,
    QBHistory,
    QBIndexConstants,
    compute_qb_index,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_qb_index_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> QBIndexConstants:
    c = GROUND_TRUTH["constants"]
    return QBIndexConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"], blend_base=c["blend_base"],
        blend_per_game=c["blend_per_game"], blend_cap=c["blend_cap"],
        weights={"epa": c["epa_weight"], "cpoe": c["cpoe_weight"], "anya": c["anya_weight"]},
        score_baseline=c["score_baseline"], points_per_sd=c["points_per_sd"],
        league_avg={
            "epa": c["epa_league_avg"], "cpoe": c["cpoe_league_avg"],
            "anya": c["anya_league_avg"],
        },
        league_std={
            "epa": c["epa_league_std"], "cpoe": c["cpoe_league_std"],
            "anya": c["anya_league_std"],
        },
    )


def _history(qb: dict) -> QBHistory:
    return QBHistory(
        player_id=qb["player_id"],
        y1={"epa": qb["epa_y1"], "cpoe": qb["cpoe_y1"], "anya": qb["anya_y1"]},
        y2={"epa": qb["epa_y2"], "cpoe": qb["cpoe_y2"], "anya": qb["anya_y2"]},
        y3={"epa": qb["epa_y3"], "cpoe": qb["cpoe_y3"], "anya": qb["anya_y3"]},
        league_baseline_y1={
            "epa": qb["epa_league_baseline_y1"], "cpoe": qb["cpoe_league_baseline_y1"],
            "anya": qb["anya_league_baseline_y1"],
        },
        games_played=int(qb["games_played"]),
        current_season={
            "epa": qb["current_season_epa"], "cpoe": qb["current_season_cpoe"],
            "anya": qb["current_season_anya"],
        },
    )


def test_ground_truth_has_real_qbs():
    # Sanity check the fixture itself is real and non-trivial before trusting any parity
    # result built on it.
    assert len(GROUND_TRUTH["qbs"]) == 64
    assert GROUND_TRUTH["qbs"][0]["player_name"] == "Jacoby Brissett"


@pytest.mark.parametrize(
    "qb", GROUND_TRUTH["qbs"], ids=[qb["player_id"] for qb in GROUND_TRUTH["qbs"]],
)
def test_qb_index_parity_full_chain(qb):
    constants = _constants()
    history = _history(qb)
    result = compute_qb_index(history, constants)

    for m, excel_key in (
        ("epa", "excel_epa_proj_baseline"), ("cpoe", "excel_cpoe_proj_baseline"),
        ("anya", "excel_anya_proj_baseline"),
    ):
        assert result.proj_baseline[m] == pytest.approx(qb[excel_key], abs=1e-6), (
            f"{qb['player_name']} {m} Projected Baseline mismatch"
        )

    assert result.blend_weight == pytest.approx(qb["excel_blend_weight"], abs=1e-6), (
        f"{qb['player_name']} Blend Weight mismatch"
    )

    for m, excel_key in (
        ("epa", "excel_epa_blended"), ("cpoe", "excel_cpoe_blended"),
        ("anya", "excel_anya_blended"),
    ):
        assert result.blended[m] == pytest.approx(qb[excel_key], abs=1e-6), (
            f"{qb['player_name']} {m} Blended value mismatch"
        )

    for m, excel_key in (
        ("epa", "excel_epa_z"), ("cpoe", "excel_cpoe_z"), ("anya", "excel_anya_z"),
    ):
        assert result.z_scores[m] == pytest.approx(qb[excel_key], abs=1e-6), (
            f"{qb['player_name']} {m} Z-score mismatch"
        )

    assert result.weighted_zsum == pytest.approx(qb["excel_weighted_zsum"], abs=1e-6), (
        f"{qb['player_name']} Weighted Z-Sum mismatch"
    )
    assert result.score == pytest.approx(qb["excel_score"], abs=1e-6), (
        f"{qb['player_name']} QB Index Score mismatch: "
        f"Python={result.score}, Excel={qb['excel_score']}"
    )


def test_all_metric_keys_covered():
    assert set(METRIC_KEYS) == {"epa", "cpoe", "anya"}
