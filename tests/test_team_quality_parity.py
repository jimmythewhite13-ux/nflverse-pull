"""
Parity test for prediction_audit/engine/team_quality.py against v35's own real recalculated
YoY Baseline Engine + Team Ratings + Season Matchups values -- 32 real teams (full
decay -> team-history -> projected-baseline -> current-season-blend chain, Off and Def each),
plus a full-272-game check that the real Season Matchups I/L/K/J lookups match the resulting
Blended Off/Def values for the correct real team.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.team_quality import (  # noqa: E402
    TeamQualityConstants,
    TeamQualityTeamHistory,
    base_team_quality,
    compute_team_quality,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_team_quality_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> TeamQualityConstants:
    c = GROUND_TRUTH["constants"]
    return TeamQualityConstants(
        decay_factor=c["decay_factor"], last_year_emphasis=c["last_year_emphasis"],
        regression_weight=c["regression_weight"], blend_base=c["blend_base"],
        blend_per_game=c["blend_per_game"], blend_cap=c["blend_cap"],
    )


def _history(t: dict) -> TeamQualityTeamHistory:
    return TeamQualityTeamHistory(
        team=t["team"],
        off_y1=t["off_y1"], off_y2=t["off_y2"], off_y3=t["off_y3"],
        def_y1=t["def_y1"], def_y2=t["def_y2"], def_y3=t["def_y3"],
        league_baseline_off_y1=t["league_baseline_off_y1"],
        league_baseline_def_y1=t["league_baseline_def_y1"],
        current_season_off_ppg=t["current_season_off_ppg"],
        current_season_def_ppg=t["current_season_def_ppg"],
        games_played=t["games_played"],
    )


def test_ground_truth_has_all_32_teams():
    assert len(GROUND_TRUTH["teams"]) == 32


def test_ground_truth_has_all_272_games():
    assert len(GROUND_TRUTH["games"]) == 272


@pytest.mark.parametrize(
    "team", GROUND_TRUTH["teams"], ids=[t["team"] for t in GROUND_TRUTH["teams"]],
)
def test_team_quality_parity_full_chain(team):
    constants = _constants()
    history = _history(team)
    result = compute_team_quality(history, constants)

    assert result.off_weighted_avg == pytest.approx(
        team["excel_off_weighted_avg"], abs=1e-6
    ), f"{team['team']} Off Weighted Avg mismatch"
    assert result.def_weighted_avg == pytest.approx(
        team["excel_def_weighted_avg"], abs=1e-6
    ), f"{team['team']} Def Weighted Avg mismatch"
    assert result.off_team_history == pytest.approx(
        team["excel_off_team_history"], abs=1e-6
    ), f"{team['team']} Off Team History mismatch"
    assert result.def_team_history == pytest.approx(
        team["excel_def_team_history"], abs=1e-6
    ), f"{team['team']} Def Team History mismatch"
    assert result.off_proj_baseline == pytest.approx(
        team["excel_off_proj_baseline"], abs=1e-6
    ), f"{team['team']} Off Projected Baseline mismatch"
    assert result.def_proj_baseline == pytest.approx(
        team["excel_def_proj_baseline"], abs=1e-6
    ), f"{team['team']} Def Projected Baseline mismatch"
    assert result.blend_weight == pytest.approx(
        team["excel_blend_weight"], abs=1e-6
    ), f"{team['team']} Blend Weight mismatch"
    assert result.blended_off == pytest.approx(
        team["excel_blended_off"], abs=1e-6
    ), f"{team['team']} Blended Off mismatch: Python={result.blended_off}, " \
       f"Excel={team['excel_blended_off']}"
    assert result.blended_def == pytest.approx(
        team["excel_blended_def"], abs=1e-6
    ), f"{team['team']} Blended Def mismatch: Python={result.blended_def}, " \
       f"Excel={team['excel_blended_def']}"


def _blended_by_team() -> dict:
    constants = _constants()
    out = {}
    for t in GROUND_TRUTH["teams"]:
        result = compute_team_quality(_history(t), constants)
        out[t["team"]] = result
    return out


BLENDED_BY_TEAM = _blended_by_team()


def _game_id(g: dict) -> str:
    return f"wk{g['week']}_{g['away']}_at_{g['home']}".replace(" ", "")


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_base_team_quality_parity_full_chain(game):
    home_result = BLENDED_BY_TEAM[game["home"]]
    away_result = BLENDED_BY_TEAM[game["away"]]

    # Season Matchups' own real I/L/K/J lookups must match the correct real team's Blended
    # Off/Def -- confirms the lookup wiring, not just the per-team arithmetic in isolation.
    assert home_result.blended_off == pytest.approx(game["excel_home_off_ppg"], abs=1e-6), (
        f"{_game_id(game)} Home Off PPG (I) lookup mismatch"
    )
    assert away_result.blended_def == pytest.approx(game["excel_away_def_ppg"], abs=1e-6), (
        f"{_game_id(game)} Away Def PPG (L) lookup mismatch"
    )
    assert away_result.blended_off == pytest.approx(game["excel_away_off_ppg"], abs=1e-6), (
        f"{_game_id(game)} Away Off PPG (K) lookup mismatch"
    )
    assert home_result.blended_def == pytest.approx(game["excel_home_def_ppg"], abs=1e-6), (
        f"{_game_id(game)} Home Def PPG (J) lookup mismatch"
    )

    home_bq, away_bq = base_team_quality(
        home_result.blended_off, away_result.blended_def,
        away_result.blended_off, home_result.blended_def,
    )
    excel_home_bq = (game["excel_home_off_ppg"] + game["excel_away_def_ppg"]) / 2
    excel_away_bq = (game["excel_away_off_ppg"] + game["excel_home_def_ppg"]) / 2
    assert home_bq == pytest.approx(excel_home_bq, abs=1e-6), (
        f"{_game_id(game)} Base Team Quality (Home) mismatch"
    )
    assert away_bq == pytest.approx(excel_away_bq, abs=1e-6), (
        f"{_game_id(game)} Base Team Quality (Away) mismatch"
    )
