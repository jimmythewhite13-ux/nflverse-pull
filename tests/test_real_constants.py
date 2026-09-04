"""
Tests for prediction_audit/historical/real_constants.py -- pure logic where possible.
`load_real_model_assumptions`/`build_real_constants` are verified against the real frozen
workbook live in this test (fast -- a single real file read, no network); the real end-to-end
composition itself was verified live via backtest_step7_real_constants.py (see its own commit
message: real MAE=10.68pts, real winner-pick accuracy=64.3%, real closing-line agreement=
78.6%, all 14 real week-10 2025 games).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.historical.real_constants import (  # noqa: E402
    _split,
    load_real_model_assumptions,
)

FROZEN_XLSX = str(
    Path(__file__).resolve().parent.parent / "prediction_audit" / "frozen_baselines"
    / "NFL_Prediction_Model_v35.xlsx"
)


def test_split_separates_avg_and_std_by_metric():
    stats = {
        "epa": {"avg": 0.1, "std": 0.05}, "cpoe": {"avg": 1.5, "std": 2.0},
    }
    avg, std = _split(stats)
    assert avg == {"epa": 0.1, "cpoe": 1.5}
    assert std == {"epa": 0.05, "cpoe": 2.0}


def test_load_real_model_assumptions_returns_real_known_values():
    c = load_real_model_assumptions(FROZEN_XLSX)
    # Spot-check a handful of real, already-verified-elsewhere-this-session constants.
    assert c[3] == 1.5       # flat HFA
    assert c[5] == 0.4       # travel coefficient
    assert c[157] == -0.5    # west-to-east travel direction penalty
    assert c[20] == 0.5      # decay factor
    assert c[21] == 0.4      # carryover weight
    assert c[22] == 0.3      # last-year emphasis
    assert c[37] == 50       # score baseline
    assert c[38] == 10       # points per SD
    assert c[39] == 0.15     # QB replacement conversion
    assert c[36] == 0.3      # ANY/A weight -- the real value that differed from this
    # session's earlier representative demo constant (0.2)
    assert c[82] == 0.35     # RB RYOE/Att weight -- also differed from the demo (0.2)
    assert c[155] == 3       # road fatigue threshold
    assert c[156] == -1      # road fatigue penalty
    assert c[171] == 10.5    # win probability logistic slope


def test_load_real_model_assumptions_covers_every_row_build_real_constants_needs():
    c = load_real_model_assumptions(FROZEN_XLSX)
    required_rows = [
        3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 20, 21, 22, 34, 35, 36, 37, 38, 39,
        44, 45, 46, 47, 58, 59, 67, 81, 82, 87, 88, 89, 90, 91, 94, 95, 96, 97, 98,
        101, 102, 119, 120, 121, 123, 124, 128, 129, 130, 131, 133, 134, 136, 137, 138,
        150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 171,
    ]
    for row in required_rows:
        assert row in c, f"real row C{row} missing from load_real_model_assumptions()"
        assert c[row] is not None, f"real row C{row} is None -- a genuine data gap"
