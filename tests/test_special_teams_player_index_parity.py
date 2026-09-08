"""
Parity test for prediction_audit/engine/special_teams_player_index.py against v35's own real
recalculated Special Teams Player Index values -- 169 real players across 3 real slot types
(P/KR/PR), each scored against their own real slot-type-specific league baseline.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.special_teams_player_index import (  # noqa: E402
    SLOT_TYPES,
    SpecialTeamsPlayerHistory,
    SpecialTeamsPlayerIndexConstants,
    compute_special_teams_player_index,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_special_teams_player_index_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> SpecialTeamsPlayerIndexConstants:
    c = GROUND_TRUTH["constants"]
    return SpecialTeamsPlayerIndexConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"], score_baseline=c["score_baseline"],
        points_per_sd=c["points_per_sd"], league_avg=c["league_avg"],
        league_std=c["league_std"],
    )


def _history(p: dict) -> SpecialTeamsPlayerHistory:
    return SpecialTeamsPlayerHistory(
        player_id=p["player_id"], slot_type=p["slot_type"], y1=p["y1"], y2=p["y2"],
        y3=p["y3"], league_baseline_y1=p["league_baseline_y1"],
    )


def test_ground_truth_has_real_players():
    assert len(GROUND_TRUTH["players"]) == 169
    slot_types = {p["slot_type"] for p in GROUND_TRUTH["players"]}
    assert slot_types == set(SLOT_TYPES)


@pytest.mark.parametrize(
    "player", GROUND_TRUTH["players"], ids=[p["player_id"] for p in GROUND_TRUTH["players"]],
)
def test_special_teams_player_index_parity_full_chain(player):
    constants = _constants()
    history = _history(player)
    result = compute_special_teams_player_index(history, constants)

    assert result.proj_baseline == pytest.approx(player["excel_proj_baseline"], abs=1e-6), (
        f"{player['player_name']} Projected Baseline mismatch"
    )
    assert result.z_score == pytest.approx(player["excel_z"], abs=1e-6), (
        f"{player['player_name']} Z-score mismatch"
    )
    assert result.score == pytest.approx(player["excel_score"], abs=1e-6), (
        f"{player['player_name']} Special Teams Player Index Score mismatch: "
        f"Python={result.score}, Excel={player['excel_score']}"
    )
