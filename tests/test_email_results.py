import os
from unittest.mock import patch

import pandas as pd
import pytest

from nflverse_pull.email_results import combine_ppg_and_efficiency, send_report_email


def test_combine_ppg_and_efficiency_merges_on_team_and_drops_season():
    season_label = "2023-2025 combined"
    ppg = pd.DataFrame([
        {"Team": "Buffalo Bills", "Season": season_label, "Off PPG": 28.6, "Def PPG": 20.5},
        {"Team": "Miami Dolphins", "Season": season_label, "Off PPG": 23.3, "Def PPG": 23.1},
    ])
    raw_eff = pd.DataFrame([
        {"Team": "Buffalo Bills", "epa_off": 0.14, "epa_def": -0.03, "success_off": 0.48,
         "success_def": 0.43, "nya_off": 6.6, "nya_def": 5.3, "proe": -0.02},
        {"Team": "Miami Dolphins", "epa_off": 0.01, "epa_def": 0.01, "success_off": 0.45,
         "success_def": 0.45, "nya_off": 6.1, "nya_def": 5.7, "proe": -0.03},
    ])
    weighted_eff = pd.DataFrame([
        {"Team": "Buffalo Bills", "Weighted Efficiency Adjustment": 2.87, "PROE": -0.02},
        {"Team": "Miami Dolphins", "Weighted Efficiency Adjustment": -0.03, "PROE": -0.03},
    ])

    out = combine_ppg_and_efficiency(ppg, raw_eff, weighted_eff)

    assert "Season" not in out.columns
    assert list(out["Team"]) == ["Buffalo Bills", "Miami Dolphins"]  # sorted
    buf = out[out["Team"] == "Buffalo Bills"].iloc[0]
    assert buf["Off PPG"] == pytest.approx(28.6)
    assert buf["Weighted Efficiency Adjustment"] == pytest.approx(2.87)
    assert buf["epa_off"] == pytest.approx(0.14)


def test_send_report_email_raises_when_credentials_missing():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError, match="NFLVERSE_SMTP_FROM_EMAIL"):
            send_report_email("Team,Off PPG\n", row_count=32)
