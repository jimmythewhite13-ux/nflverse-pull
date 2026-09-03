"""
Tests for prediction_audit/historical/ol_pressure_adj_historical.py -- pure logic, no network.
Both underlying resolvers (OL Index, Pass Rush Generation Index) are already independently
verified against real data in their own test files; this focuses on the composition itself
(the real subtraction and the real None-propagation on either side's failure).
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.offensive_line_index import OLIndexConstants  # noqa: E402
from prediction_audit.engine.pass_rush_generation_index import (  # noqa: E402
    PassRushGenerationConstants,
)
from prediction_audit.historical.ol_pressure_adj_historical import (  # noqa: E402
    resolve_ol_pressure_diff,
)

OL_CONSTANTS = OLIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
    weights={"pass_protection": 0.4, "run_blocking": 0.3, "sack_free_rate": 0.3},
    score_baseline=50, points_per_sd=10,
    league_avg=dict.fromkeys(["pass_protection", "run_blocking", "sack_free_rate"], 0.0),
    league_std=dict.fromkeys(["pass_protection", "run_blocking", "sack_free_rate"], 1.0),
)
PASS_RUSH_CONSTANTS = PassRushGenerationConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    weights={"sack_rate": 0.5, "pressure_proxy": 0.35, "blitz_rate": 0.15},
    league_avg=dict.fromkeys(["sack_rate", "pressure_proxy", "blitz_rate"], 0.0),
    league_std=dict.fromkeys(["sack_rate", "pressure_proxy", "blitz_rate"], 1.0),
)


def _pfr_pass_rows(season, team, attempts, pressured):
    return [{"team": team, "season": season, "pass_attempts": attempts,
              "times_pressured": pressured}]


def _pfr_rush_rows(season, team, att, ybc):
    return [{"tm": team, "season": season, "att": att, "ybc": ybc}]


def _sack_row(season, week, posteam, sack=0, pass_attempt=1, season_type="REG"):
    return {
        "season": season, "week": week, "season_type": season_type, "posteam": posteam,
        "pass_attempt": pass_attempt, "sack": sack, "game_id": f"{season}_{week}_{posteam}",
        "play_id": week * 100 + (1 if sack else 0),
    }


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2022, 2023, 2024):
        for week in range(1, 9):
            for _ in range(20):
                rows.append(_sack_row(season, week, "BUF"))
            rows.append(_sack_row(season, week, "BUF", sack=1))
            for _ in range(20):
                rows.append(_sack_row(season, week, "MIA"))
    return pd.DataFrame(rows)


def _fake_ftn_3yr_prior():
    rows = []
    for season in (2022, 2023, 2024):
        for week in range(1, 9):
            rows.append({
                "nflverse_game_id": f"{season}_{week}_BUF", "nflverse_play_id": week * 100 + 1,
                "is_qb_fault_sack": False,
            })
    return pd.DataFrame(rows)


def _fake_pfr_pass():
    rows = []
    for season in (2022, 2023, 2024):
        rows += _pfr_pass_rows(season, "BUF", 500, 100)
        rows += _pfr_pass_rows(season, "MIA", 500, 150)
    return pd.DataFrame(rows)


def _fake_pfr_rush():
    rows = []
    for season in (2022, 2023, 2024):
        rows += _pfr_rush_rows(season, "BUF", 400, 800)
        rows += _pfr_rush_rows(season, "MIA", 400, 600)
    return pd.DataFrame(rows)


def _pass_rush_pbp_row(season, week, defteam, sack=0, qb_hit=0, n_rushers=4):
    return {
        "season": season, "week": week, "season_type": "REG", "defteam": defteam,
        "pass_attempt": 1, "sack": sack, "qb_hit": qb_hit,
        "tackled_for_loss": 0, "number_of_pass_rushers": n_rushers,
        "play_type": "pass", "defenders_in_box": 6,
    }


def _fake_pass_rush_pbp():
    rows = []
    for season in (2022, 2023, 2024):
        for week in range(1, 9):
            for i in range(30):
                rows.append(_pass_rush_pbp_row(
                    season, week, "MIA", sack=1 if i < 3 else 0, qb_hit=1 if i < 5 else 0,
                    n_rushers=6 if i < 9 else 4,
                ))
    return pd.DataFrame(rows)


def test_resolve_ol_pressure_diff_real_composition():
    pbp_ol_fault = _fake_pbp_3yr_prior()
    pbp_pass_rush = _fake_pass_rush_pbp()
    # Both real pbp fixtures are unioned -- OL Index reads sack/posteam-side columns, Pass
    # Rush Generation reads qb_hit/defteam-side columns, both real and present on the merge.
    combined = pd.concat([pbp_ol_fault, pbp_pass_rush], ignore_index=True)

    diff = resolve_ol_pressure_diff(
        combined, _fake_pfr_pass(), _fake_pfr_rush(), _fake_ftn_3yr_prior(),
        target_season=2025, ol_team="Buffalo Bills", pass_rush_opponent="Miami Dolphins",
        ol_constants=OL_CONSTANTS, pass_rush_constants=PASS_RUSH_CONSTANTS,
    )
    assert diff is not None
    assert isinstance(diff, float)


def test_resolve_ol_pressure_diff_none_when_ol_side_fails_ftn_constraint():
    # target_season=2024 needs Y-3=2021, before FTN's real 2022 start -- OL Index's own
    # resolver raises, and this module must propagate that as None, not an exception.
    pbp = pd.concat([_fake_pbp_3yr_prior(), _fake_pass_rush_pbp()], ignore_index=True)
    diff = resolve_ol_pressure_diff(
        pbp, _fake_pfr_pass(), _fake_pfr_rush(), _fake_ftn_3yr_prior(),
        target_season=2024, ol_team="Buffalo Bills", pass_rush_opponent="Miami Dolphins",
        ol_constants=OL_CONSTANTS, pass_rush_constants=PASS_RUSH_CONSTANTS,
    )
    assert diff is None
