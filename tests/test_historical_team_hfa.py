"""
Tests for prediction_audit/historical/team_hfa.py -- pure logic, no network. A synthetic
multi-season fake schedule proves the real Y1/Y2/Y3 (3 full prior seasons, no current-season
blend) assembly and the real franchise-relocation normalization.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.team_specific_hfa import TeamSpecificHFAConstants  # noqa: E402
from prediction_audit.historical.relocations import (  # noqa: E402
    normalize_relocated_abbreviations,
)
from prediction_audit.historical.team_hfa import (  # noqa: E402
    resolve_team_specific_hfa_for_game,
    resolve_team_specific_hfa_history,
)

CONSTANTS = TeamSpecificHFAConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
)


def _fake_schedule():
    rows = []
    # BUF home games: consistently strong home margin. BUF away games: weaker.
    for season, home_margin_pair, away_margin_pair in (
        (2021, (30, 10), (17, 24)), (2022, (28, 14), (13, 20)), (2023, (24, 10), (10, 17)),
    ):
        rows.append({"season": season, "game_type": "REG", "week": 1, "home_team": "BUF",
                      "away_team": "NYJ", "home_score": home_margin_pair[0],
                      "away_score": home_margin_pair[1]})
        rows.append({"season": season, "game_type": "REG", "week": 2, "home_team": "NE",
                      "away_team": "BUF", "home_score": away_margin_pair[0],
                      "away_score": away_margin_pair[1]})
    return pd.DataFrame(rows)


def test_resolve_team_specific_hfa_history_uses_real_3yr_raw_hfa():
    sched = _fake_schedule()
    history = resolve_team_specific_hfa_history(sched, target_season=2024, team="Buffalo Bills")
    # Away Margin = away_score - home_score (BUF's own real margin as the visitor). Real, fixed
    # 2026-09-09: raw HFA is (Home Margin - Away Margin) / 2, not the unhalved difference -- see
    # PROGRESS.md's "Real bug found and fixed" entry (Home Margin ~= strength + h, Away Margin
    # ~= strength - h, so their unhalved difference is 2h, not h).
    # 2023 (Y1): home margin 24-10=14, BUF away margin 17-10=7 -> HFA=(14-7)/2=3.5
    assert history.y1 == pytest.approx(3.5)
    # 2022 (Y2): home margin 28-14=14, BUF away margin 20-13=7 -> HFA=(14-7)/2=3.5
    assert history.y2 == pytest.approx(3.5)
    # 2021 (Y3): home margin 30-10=20, BUF away margin 24-17=7 -> HFA=(20-7)/2=6.5
    assert history.y3 == pytest.approx(6.5)


def test_resolve_team_specific_hfa_history_raises_on_missing_team():
    sched = _fake_schedule()
    with pytest.raises(ValueError, match="No real home/away split found"):
        resolve_team_specific_hfa_history(sched, target_season=2024, team="Denver Broncos")


def test_resolve_team_specific_hfa_for_game_end_to_end():
    sched = _fake_schedule()
    result = resolve_team_specific_hfa_for_game(sched, 2024, "Buffalo Bills", CONSTANTS)
    assert result.team == "Buffalo Bills"
    assert isinstance(result.regressed_hfa, float)


def test_normalize_relocated_abbreviations_real_franchise_continuity():
    sched = pd.DataFrame([
        {"season": 2019, "game_type": "REG", "week": 1, "home_team": "OAK", "away_team": "DEN",
         "home_score": 24, "away_score": 16},
        {"season": 2016, "game_type": "REG", "week": 1, "home_team": "SD", "away_team": "KC",
         "home_score": 27, "away_score": 24},
        {"season": 2015, "game_type": "REG", "week": 1, "home_team": "STL", "away_team": "SEA",
         "home_score": 34, "away_score": 31},
    ])
    normalized = normalize_relocated_abbreviations(sched)
    assert "OAK" not in set(normalized["home_team"])
    assert "SD" not in set(normalized["home_team"])
    assert "STL" not in set(normalized["home_team"])
    assert {"LV", "LAC", "LA"} <= set(normalized["home_team"])
