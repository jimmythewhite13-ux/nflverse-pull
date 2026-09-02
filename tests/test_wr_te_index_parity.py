"""
Parity test for prediction_audit/engine/wr_te_index.py against v35's own real recalculated
WR-TE Value Index values -- mirrors test_qb_index_parity.py/test_rb_index_parity.py's own
structure, generalized to 9 metrics and 128 real players (both WR and TE).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.wr_te_index import (  # noqa: E402
    METRIC_KEYS,
    WRTEHistory,
    WRTEIndexConstants,
    compute_wr_te_index,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_wr_te_index_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> WRTEIndexConstants:
    c = GROUND_TRUTH["constants"]
    return WRTEIndexConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"], blend_base=c["blend_base"],
        blend_per_game=c["blend_per_game"], blend_cap=c["blend_cap"],
        weights=c["weights"], score_baseline=c["score_baseline"],
        points_per_sd=c["points_per_sd"], league_avg=c["league_avg"],
        league_std=c["league_std"],
    )


def _history(p: dict) -> WRTEHistory:
    return WRTEHistory(
        player_id=p["player_id"], position=p["position"],
        y1={m: p[f"{m}_y1"] for m in METRIC_KEYS},
        y2={m: p[f"{m}_y2"] for m in METRIC_KEYS},
        y3={m: p[f"{m}_y3"] for m in METRIC_KEYS},
        league_baseline_y1={m: p[f"{m}_league_baseline_y1"] for m in METRIC_KEYS},
        games_played=int(p["games_played"]),
        current_season={m: p[f"current_season_{m}"] for m in METRIC_KEYS},
    )


def test_ground_truth_has_real_players():
    assert len(GROUND_TRUTH["players"]) == 128
    positions = {p["position"] for p in GROUND_TRUTH["players"]}
    assert positions == {"WR", "TE"}


@pytest.mark.parametrize(
    "player", GROUND_TRUTH["players"], ids=[p["player_id"] for p in GROUND_TRUTH["players"]],
)
def test_wr_te_index_parity_full_chain(player):
    constants = _constants()
    history = _history(player)
    result = compute_wr_te_index(history, constants)

    for m in METRIC_KEYS:
        assert result.proj_baseline[m] == pytest.approx(
            player[f"excel_{m}_proj_baseline"], abs=1e-6
        ), f"{player['player_name']} {m} Projected Baseline mismatch"

    assert result.blend_weight == pytest.approx(player["excel_blend_weight"], abs=1e-6), (
        f"{player['player_name']} Blend Weight mismatch"
    )

    for m in METRIC_KEYS:
        assert result.blended[m] == pytest.approx(
            player[f"excel_{m}_blended"], abs=1e-6
        ), f"{player['player_name']} {m} Blended value mismatch"
        assert result.z_scores[m] == pytest.approx(
            player[f"excel_{m}_z"], abs=1e-6
        ), f"{player['player_name']} {m} Z-score mismatch"

    assert result.weighted_zsum == pytest.approx(player["excel_weighted_zsum"], abs=1e-6), (
        f"{player['player_name']} Weighted Z-Sum mismatch"
    )
    assert result.score == pytest.approx(player["excel_score"], abs=1e-6), (
        f"{player['player_name']} WR/TE Index Score mismatch: "
        f"Python={result.score}, Excel={player['excel_score']}"
    )


def test_all_metric_keys_covered():
    assert set(METRIC_KEYS) == {
        "receiving_epa", "success_rate", "ypt", "avg_sep", "yac_oe", "pass_play_pct",
        "rz_target_share", "target_share", "catch_rate",
    }
