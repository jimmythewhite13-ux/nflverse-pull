"""
Parity test for prediction_audit/engine/offensive_line_index.py against v35's own real
recalculated Offensive Line Index values -- 32 real teams, 3 real metrics.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.offensive_line_index import (  # noqa: E402
    METRIC_KEYS,
    OLIndexConstants,
    OLTeamHistory,
    compute_ol_index,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_offensive_line_index_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> OLIndexConstants:
    c = GROUND_TRUTH["constants"]
    return OLIndexConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"], blend_base=c["blend_base"],
        blend_per_game=c["blend_per_game"], blend_cap=c["blend_cap"],
        weights=c["weights"], score_baseline=c["score_baseline"],
        points_per_sd=c["points_per_sd"], league_avg=c["league_avg"],
        league_std=c["league_std"],
    )


def _history(t: dict) -> OLTeamHistory:
    return OLTeamHistory(
        team=t["team"],
        y1={m: t[f"{m}_y1"] for m in METRIC_KEYS},
        y2={m: t[f"{m}_y2"] for m in METRIC_KEYS},
        y3={m: t[f"{m}_y3"] for m in METRIC_KEYS},
        league_baseline_y1={m: t[f"{m}_league_baseline_y1"] for m in METRIC_KEYS},
        games_played=int(t["games_played"]),
        current_season={m: t[f"current_season_{m}"] for m in METRIC_KEYS},
    )


def test_ground_truth_has_all_32_teams():
    assert len(GROUND_TRUTH["teams"]) == 32


@pytest.mark.parametrize(
    "team", GROUND_TRUTH["teams"], ids=[t["team"] for t in GROUND_TRUTH["teams"]],
)
def test_ol_index_parity_full_chain(team):
    constants = _constants()
    history = _history(team)
    result = compute_ol_index(history, constants)

    for m in METRIC_KEYS:
        assert result.proj_baseline[m] == pytest.approx(
            team[f"excel_{m}_proj_baseline"], abs=1e-6
        ), f"{team['team']} {m} Projected Baseline mismatch"

    assert result.blend_weight == pytest.approx(team["excel_blend_weight"], abs=1e-6), (
        f"{team['team']} Blend Weight mismatch"
    )

    for m in METRIC_KEYS:
        assert result.blended[m] == pytest.approx(
            team[f"excel_{m}_blended"], abs=1e-6
        ), f"{team['team']} {m} Blended value mismatch"
        assert result.z_scores[m] == pytest.approx(
            team[f"excel_{m}_z"], abs=1e-6
        ), f"{team['team']} {m} Z-score mismatch"

    assert result.weighted_zsum == pytest.approx(team["excel_weighted_zsum"], abs=1e-6), (
        f"{team['team']} Weighted Z-Sum mismatch"
    )
    assert result.score == pytest.approx(team["excel_score"], abs=1e-6), (
        f"{team['team']} Team OL Score mismatch: "
        f"Python={result.score}, Excel={team['excel_score']}"
    )
