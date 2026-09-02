"""
Parity test for prediction_audit/engine/qb_index.py's Section 6 Replacement Value functions
against v35's own real recalculated QB Index values -- all 32 real teams.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.qb_index import (  # noqa: E402
    replacement_value_game_points,
    replacement_value_index_points,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_qb_replacement_value_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def test_ground_truth_has_all_32_teams():
    assert len(GROUND_TRUTH["teams"]) == 32


@pytest.mark.parametrize(
    "team", GROUND_TRUTH["teams"], ids=[t["team"] for t in GROUND_TRUTH["teams"]],
)
def test_replacement_value_parity(team):
    conversion = GROUND_TRUTH["constants"]["rv_conversion"]
    rv_index = replacement_value_index_points(team["starter_score"], team["backup_score"])
    rv_game = replacement_value_game_points(rv_index, conversion)

    assert rv_index == pytest.approx(team["excel_rv_index_points"], abs=1e-6), (
        f"{team['team']} Replacement Value (Index Points) mismatch"
    )
    assert rv_game == pytest.approx(team["excel_rv_game_points"], abs=1e-6), (
        f"{team['team']} Replacement Value (Game Points) mismatch: Python={rv_game}, "
        f"Excel={team['excel_rv_game_points']}"
    )


def test_replacement_value_blank_when_starter_or_backup_missing():
    assert replacement_value_index_points(None, 1.0) is None
    assert replacement_value_index_points(1.0, "") is None
    assert replacement_value_game_points(None, 0.15) is None
