"""
Parity test for prediction_audit/engine/team_specific_hfa.py against v35's own real
recalculated Team-Specific HFA values -- 32 real teams, single metric, no blend, no
Z-scoring.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.team_specific_hfa import (  # noqa: E402
    TeamSpecificHFAConstants,
    TeamSpecificHFAHistory,
    compute_team_specific_hfa,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_team_specific_hfa_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> TeamSpecificHFAConstants:
    c = GROUND_TRUTH["constants"]
    return TeamSpecificHFAConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"],
    )


def _history(t: dict) -> TeamSpecificHFAHistory:
    return TeamSpecificHFAHistory(
        team=t["team"], y1=t["y1"], y2=t["y2"], y3=t["y3"],
        league_baseline_y1=t["league_baseline_y1"],
    )


def test_ground_truth_has_all_32_teams():
    assert len(GROUND_TRUTH["teams"]) == 32


@pytest.mark.parametrize(
    "team", GROUND_TRUTH["teams"], ids=[t["team"] for t in GROUND_TRUTH["teams"]],
)
def test_team_specific_hfa_parity_full_chain(team):
    constants = _constants()
    history = _history(team)
    result = compute_team_specific_hfa(history, constants)

    assert result.regressed_hfa == pytest.approx(team["excel_regressed_hfa"], abs=1e-6), (
        f"{team['team']} Regressed Team-Specific HFA mismatch: "
        f"Python={result.regressed_hfa}, Excel={team['excel_regressed_hfa']}"
    )


def test_real_hfa_values_are_genuinely_different_across_teams():
    # Sanity check matching the earlier live investigation this session (Bears highest,
    # Ravens lowest, 32 genuinely distinct real values) -- not a flat constant.
    values = {t["team"]: t["excel_regressed_hfa"] for t in GROUND_TRUTH["teams"]}
    assert len(set(round(v, 4) for v in values.values())) == 32
