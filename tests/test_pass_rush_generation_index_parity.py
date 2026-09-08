"""
Parity test for prediction_audit/engine/pass_rush_generation_index.py against v35's own real
recalculated Pass Rush Generation Index values -- 32 real teams, 3 real metrics, no blend
step, no points-scale conversion (the weighted Z-sum IS the Score).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.pass_rush_generation_index import (  # noqa: E402
    METRIC_KEYS,
    PassRushGenerationConstants,
    PassRushGenerationTeamHistory,
    compute_pass_rush_generation_index,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_pass_rush_generation_index_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> PassRushGenerationConstants:
    c = GROUND_TRUTH["constants"]
    return PassRushGenerationConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"], weights=c["weights"],
        league_avg=c["league_avg"], league_std=c["league_std"],
    )


def _history(t: dict) -> PassRushGenerationTeamHistory:
    return PassRushGenerationTeamHistory(
        team=t["team"],
        y1={m: t[f"{m}_y1"] for m in METRIC_KEYS},
        y2={m: t[f"{m}_y2"] for m in METRIC_KEYS},
        y3={m: t[f"{m}_y3"] for m in METRIC_KEYS},
        league_baseline_y1={m: t[f"{m}_league_baseline_y1"] for m in METRIC_KEYS},
    )


def test_ground_truth_has_all_32_teams():
    assert len(GROUND_TRUTH["teams"]) == 32


@pytest.mark.parametrize(
    "team", GROUND_TRUTH["teams"], ids=[t["team"] for t in GROUND_TRUTH["teams"]],
)
def test_pass_rush_generation_index_parity_full_chain(team):
    constants = _constants()
    history = _history(team)
    result = compute_pass_rush_generation_index(history, constants)

    for m in METRIC_KEYS:
        assert result.proj_baseline[m] == pytest.approx(
            team[f"excel_{m}_proj_baseline"], abs=1e-6
        ), f"{team['team']} {m} Projected Baseline mismatch"
        assert result.z_scores[m] == pytest.approx(
            team[f"excel_{m}_z"], abs=1e-6
        ), f"{team['team']} {m} Z-score mismatch"

    assert result.score == pytest.approx(team["excel_score"], abs=1e-6), (
        f"{team['team']} Pass Rush Generation Score mismatch: "
        f"Python={result.score}, Excel={team['excel_score']}"
    )
