"""
Tests for prediction_audit/market_data.py's pure transform logic (no network access needed --
same fetch/transform split convention as test_pull.py). The synthetic schedule rows below are
clearly-labeled fake input data used only to test the transform's own arithmetic/mapping logic
-- not a substitute for or claim about any real market line.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.market_data import (  # noqa: E402
    REAL_SOURCE_NAME,
    RealMarketLine,
    transform_schedule_to_market_lines,
)


def _fake_schedule():
    return pd.DataFrame([
        {"season": 2025, "game_type": "REG", "week": 1, "home_team": "BUF", "away_team": "MIA",
         "spread_line": -3.0, "total_line": 47.5, "away_moneyline": 150.0,
         "home_moneyline": -180.0},
        {"season": 2025, "game_type": "REG", "week": 2, "home_team": "MIA", "away_team": "NYJ",
         "spread_line": None, "total_line": None, "away_moneyline": None,
         "home_moneyline": None},
        {"season": 2025, "game_type": "POST", "week": 20, "home_team": "BUF", "away_team": "MIA",
         "spread_line": -5.0, "total_line": 44.5, "away_moneyline": 200.0,
         "home_moneyline": -240.0},
    ])


def test_transform_maps_team_abbreviations_to_full_names():
    lines = transform_schedule_to_market_lines(_fake_schedule())
    reg_lines = [l for l in lines if l.week != 20]  # noqa: E741
    assert len(reg_lines) == 2

    buf_home = next(l for l in reg_lines if l.week == 1)  # noqa: E741
    assert buf_home.home_team == "Buffalo Bills"
    assert buf_home.away_team == "Miami Dolphins"
    assert buf_home.spread_line == pytest.approx(-3.0)
    assert buf_home.total_line == pytest.approx(47.5)
    assert buf_home.away_moneyline == pytest.approx(150.0)
    assert buf_home.home_moneyline == pytest.approx(-180.0)


def test_transform_excludes_postseason_games():
    lines = transform_schedule_to_market_lines(_fake_schedule())
    assert all(l.week != 20 for l in lines)  # noqa: E741


def test_transform_preserves_genuinely_null_lines_as_none():
    lines = transform_schedule_to_market_lines(_fake_schedule())
    not_yet_posted = next(l for l in lines if l.week == 2)  # noqa: E741
    assert not_yet_posted.spread_line is None
    assert not_yet_posted.total_line is None
    assert not_yet_posted.away_moneyline is None
    assert not_yet_posted.home_moneyline is None


def test_real_market_line_is_a_plain_dataclass():
    line = RealMarketLine(
        week=1, away_team="Miami Dolphins", home_team="Buffalo Bills",
        spread_line=-3.0, total_line=47.5, away_moneyline=150.0, home_moneyline=-180.0,
    )
    assert line.week == 1


def test_real_source_name_is_documented():
    assert "habitatring.com" in REAL_SOURCE_NAME
    assert "nfl_data_py" in REAL_SOURCE_NAME
