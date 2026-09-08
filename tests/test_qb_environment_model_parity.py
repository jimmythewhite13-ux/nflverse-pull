"""
Parity test for prediction_audit/engine/qb_environment_model.py against v35's own real
recalculated QB Environment Model values -- 64 real QBs (same population QB Index itself
scores), full Section 3/5/6 chain including the real EPA/CPOE/ANY-A Z references from QB
Index's own Section 5.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.qb_environment_model import (  # noqa: E402
    METRIC_KEYS,
    QBEnvironmentModelConstants,
    QBEnvironmentModelHistory,
    compute_qb_environment_model,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_qb_environment_model_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> QBEnvironmentModelConstants:
    c = GROUND_TRUTH["constants"]
    return QBEnvironmentModelConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"],
        league_avg={
            "success": c["league_avg_success"], "explosive": c["league_avg_explosive"],
            "sack": c["league_avg_sack"],
        },
        league_std={
            "success": c["league_std_success"], "explosive": c["league_std_explosive"],
            "sack": c["league_std_sack"],
        },
        success_weight=c["success_weight"], explosive_weight=c["explosive_weight"],
        epa_weight=c["epa_weight"], cpoe_weight=c["cpoe_weight"], anya_weight=c["anya_weight"],
        score_baseline=c["score_baseline"], points_per_sd=c["points_per_sd"],
        new_team_penalty=c["new_team_penalty"],
        recently_injured_penalty=c["recently_injured_penalty"],
    )


def _history(q: dict) -> QBEnvironmentModelHistory:
    return QBEnvironmentModelHistory(
        player_id=q["player_id"],
        y1={m: q[f"{m}_y1"] for m in METRIC_KEYS},
        y2={m: q[f"{m}_y2"] for m in METRIC_KEYS},
        y3={m: q[f"{m}_y3"] for m in METRIC_KEYS},
        league_baseline_y1={m: q[f"{m}_league_baseline_y1"] for m in METRIC_KEYS},
        epa_z_ref=q["excel_epa_z_ref"], cpoe_z_ref=q["excel_cpoe_z_ref"],
        anya_z_ref=q["excel_anya_z_ref"],
        new_team_this_season=q["new_team_this_season"],
        recently_returned_from_injury=q["recently_returned_from_injury"],
    )


def test_ground_truth_has_all_64_qbs():
    assert len(GROUND_TRUTH["qbs"]) == 64


def test_ground_truth_has_real_new_team_and_injury_coverage():
    # Unlike several other edge-case terms in this project, this real snapshot has
    # substantial genuine coverage for both situational-adjustment branches.
    new_team = [q for q in GROUND_TRUTH["qbs"] if q["new_team_this_season"]]
    injured = [q for q in GROUND_TRUTH["qbs"] if q["recently_returned_from_injury"]]
    assert len(new_team) > 0
    assert len(injured) > 0


@pytest.mark.parametrize(
    "qb", GROUND_TRUTH["qbs"], ids=[f"{q['player_name']}_{q['team']}" for q in GROUND_TRUTH["qbs"]],
)
def test_qb_environment_model_parity_full_chain(qb):
    constants = _constants()
    history = _history(qb)
    result = compute_qb_environment_model(history, constants)

    for m in METRIC_KEYS:
        assert result.weighted_avg[m] == pytest.approx(
            qb[f"excel_{m}_weighted_avg"], abs=1e-6
        ), f"{qb['player_name']} {m} Weighted Avg mismatch"
        assert result.team_history[m] == pytest.approx(
            qb[f"excel_{m}_team_history"], abs=1e-6
        ), f"{qb['player_name']} {m} Team History mismatch"
        assert result.proj_baseline[m] == pytest.approx(
            qb[f"excel_{m}_proj_baseline"], abs=1e-6
        ), f"{qb['player_name']} {m} Projected Baseline mismatch"

    assert result.z_scores["success"] == pytest.approx(qb["excel_success_z"], abs=1e-6)
    assert result.z_scores["explosive"] == pytest.approx(qb["excel_explosive_z"], abs=1e-6)
    assert result.z_scores["sack"] == pytest.approx(qb["excel_sack_z_ref"], abs=1e-6)

    assert result.weighted_zsum == pytest.approx(qb["excel_weighted_zsum"], abs=1e-6), (
        f"{qb['player_name']} Weighted Talent Z-Sum mismatch: Python={result.weighted_zsum}, "
        f"Excel={qb['excel_weighted_zsum']}"
    )
    assert result.raw_talent_score == pytest.approx(qb["excel_raw_talent_score"], abs=1e-6), (
        f"{qb['player_name']} Raw QB Talent Score mismatch: Python={result.raw_talent_score}, "
        f"Excel={qb['excel_raw_talent_score']}"
    )
    assert result.situational_adj == pytest.approx(qb["excel_situational_adj"], abs=1e-6), (
        f"{qb['player_name']} Situational Adjustment mismatch"
    )
    assert result.adjusted_baseline == pytest.approx(qb["excel_adjusted_baseline"], abs=1e-6), (
        f"{qb['player_name']} QB Environment-Adjusted Baseline mismatch: "
        f"Python={result.adjusted_baseline}, Excel={qb['excel_adjusted_baseline']}"
    )
