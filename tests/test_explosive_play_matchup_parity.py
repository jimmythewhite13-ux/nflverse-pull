"""
Parity test for prediction_audit/engine/explosive_play_matchup.py against v35's own real
recalculated Explosive Play Matchup + Season Matchups values -- 32 real teams' full Section
3/4/5 chain (4 metrics, 2 composites), plus all 272 real games' Season Matchups CO/CP wiring.
This closes out the last previously-unported real term in the Z/AA formula.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.explosive_play_matchup import (  # noqa: E402
    ExplosivePlayMatchupConstants,
    ExplosivePlayMatchupTeamHistory,
    compute_explosive_play_matchup,
    explosive_play_matchup_adj,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_explosive_play_matchup_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()


def _constants() -> ExplosivePlayMatchupConstants:
    c = GROUND_TRUTH["constants"]
    return ExplosivePlayMatchupConstants(
        decay_factor=c["decay_factor"], regression_weight=c["regression_weight"],
        last_year_emphasis=c["last_year_emphasis"],
        league_avg_pass_off=c["league_avg_pass_off"], league_std_pass_off=c["league_std_pass_off"],
        league_avg_run_off=c["league_avg_run_off"], league_std_run_off=c["league_std_run_off"],
        league_avg_deep_pass_allowed=c["league_avg_deep_pass_allowed"],
        league_std_deep_pass_allowed=c["league_std_deep_pass_allowed"],
        league_avg_yac_allowed=c["league_avg_yac_allowed"],
        league_std_yac_allowed=c["league_std_yac_allowed"],
        pass_prevention_w_explosive_pass_allowed=c["pass_prevention_w_explosive_pass_allowed"],
        pass_prevention_w_deep_pass_allowed=c["pass_prevention_w_deep_pass_allowed"],
        pass_prevention_w_yac_allowed=c["pass_prevention_w_yac_allowed"],
    )


SEC5_BY_TEAM = {t["team"]: t for t in GROUND_TRUTH["section5"]}


def _history(t: dict) -> ExplosivePlayMatchupTeamHistory:
    sec5 = SEC5_BY_TEAM[t["team"]]
    return ExplosivePlayMatchupTeamHistory(
        team=t["team"],
        pass_off_y1=t["pass_off_y1"], pass_off_y2=t["pass_off_y2"], pass_off_y3=t["pass_off_y3"],
        pass_off_league_baseline_y1=t["pass_off_league_baseline_y1"],
        run_off_y1=t["run_off_y1"], run_off_y2=t["run_off_y2"], run_off_y3=t["run_off_y3"],
        run_off_league_baseline_y1=t["run_off_league_baseline_y1"],
        deep_pass_allowed_y1=t["deep_pass_allowed_y1"],
        deep_pass_allowed_y2=t["deep_pass_allowed_y2"],
        deep_pass_allowed_y3=t["deep_pass_allowed_y3"],
        deep_pass_allowed_league_baseline_y1=t["deep_pass_allowed_league_baseline_y1"],
        yac_allowed_y1=t["yac_allowed_y1"], yac_allowed_y2=t["yac_allowed_y2"],
        yac_allowed_y3=t["yac_allowed_y3"],
        yac_allowed_league_baseline_y1=t["yac_allowed_league_baseline_y1"],
        explosive_pass_allowed_z_ref=sec5["excel_explosive_pass_allowed_z_ref"],
        explosive_run_allowed_z_ref=sec5["excel_explosive_run_allowed_z_ref"],
    )


def test_ground_truth_has_all_32_teams():
    assert len(GROUND_TRUTH["teams"]) == 32
    assert len(GROUND_TRUTH["section5"]) == 32


def test_ground_truth_has_all_272_games():
    assert len(GROUND_TRUTH["games"]) == 272


@pytest.mark.parametrize(
    "team", GROUND_TRUTH["teams"], ids=[t["team"] for t in GROUND_TRUTH["teams"]],
)
def test_explosive_play_matchup_parity_full_chain(team):
    constants = _constants()
    history = _history(team)
    result = compute_explosive_play_matchup(history, constants)
    sec5 = SEC5_BY_TEAM[team["team"]]

    assert result.pass_off_weighted_avg == pytest.approx(
        team["excel_pass_off_weighted_avg"], abs=1e-6
    )
    assert result.pass_off_team_history == pytest.approx(
        team["excel_pass_off_team_history"], abs=1e-6
    )
    assert result.pass_off_proj_baseline == pytest.approx(
        team["excel_pass_off_proj_baseline"], abs=1e-6
    )
    assert result.pass_off_z == pytest.approx(sec5["excel_pass_off_z"], abs=1e-6)

    assert result.run_off_weighted_avg == pytest.approx(
        team["excel_run_off_weighted_avg"], abs=1e-6
    )
    assert result.run_off_team_history == pytest.approx(
        team["excel_run_off_team_history"], abs=1e-6
    )
    assert result.run_off_proj_baseline == pytest.approx(
        team["excel_run_off_proj_baseline"], abs=1e-6
    )
    assert result.run_off_z == pytest.approx(sec5["excel_run_off_z"], abs=1e-6)

    assert result.deep_pass_allowed_weighted_avg == pytest.approx(
        team["excel_deep_pass_allowed_weighted_avg"], abs=1e-6
    )
    assert result.deep_pass_allowed_team_history == pytest.approx(
        team["excel_deep_pass_allowed_team_history"], abs=1e-6
    )
    assert result.deep_pass_allowed_proj_baseline == pytest.approx(
        team["excel_deep_pass_allowed_proj_baseline"], abs=1e-6
    )
    assert result.deep_pass_allowed_z == pytest.approx(
        sec5["excel_deep_pass_allowed_z"], abs=1e-6
    )

    assert result.yac_allowed_weighted_avg == pytest.approx(
        team["excel_yac_allowed_weighted_avg"], abs=1e-6
    )
    assert result.yac_allowed_team_history == pytest.approx(
        team["excel_yac_allowed_team_history"], abs=1e-6
    )
    assert result.yac_allowed_proj_baseline == pytest.approx(
        team["excel_yac_allowed_proj_baseline"], abs=1e-6
    )
    assert result.yac_allowed_z == pytest.approx(sec5["excel_yac_allowed_z"], abs=1e-6)

    assert result.pass_prevention_composite_z == pytest.approx(
        sec5["excel_pass_prevention_composite_z"], abs=1e-6
    ), (
        f"{team['team']} Pass Prevention Composite Z mismatch: "
        f"Python={result.pass_prevention_composite_z}, "
        f"Excel={sec5['excel_pass_prevention_composite_z']}"
    )
    assert result.run_prevention_z == pytest.approx(
        sec5["excel_run_prevention_z"], abs=1e-6
    ), (
        f"{team['team']} Run Prevention Z mismatch: Python={result.run_prevention_z}, "
        f"Excel={sec5['excel_run_prevention_z']}"
    )


def _results_by_team() -> dict:
    constants = _constants()
    return {
        t["team"]: compute_explosive_play_matchup(_history(t), constants)
        for t in GROUND_TRUTH["teams"]
    }


RESULTS_BY_TEAM = _results_by_team()


def _game_id(g: dict) -> str:
    return f"wk{g['week']}_{g['away']}_at_{g['home']}".replace(" ", "")


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_explosive_play_matchup_adj_parity(game):
    home = RESULTS_BY_TEAM[game["home"]]
    away = RESULTS_BY_TEAM[game["away"]]
    conv = GROUND_TRUTH["constants"]

    # Confirm each side's own real Z-scores match what Season Matchups' own CC/CF/CI/CL
    # real lookups resolved to, before checking the diff/adj wiring itself.
    assert home.pass_off_z == pytest.approx(game["excel_CC_home_pass_off_z"], abs=1e-6)
    assert away.pass_prevention_composite_z == pytest.approx(
        game["excel_CD_away_pass_prevention_z"], abs=1e-6
    )
    assert away.pass_off_z == pytest.approx(game["excel_CF_away_pass_off_z"], abs=1e-6)
    assert home.pass_prevention_composite_z == pytest.approx(
        game["excel_CG_home_pass_prevention_z"], abs=1e-6
    )
    assert home.run_off_z == pytest.approx(game["excel_CI_home_run_off_z"], abs=1e-6)
    assert away.run_prevention_z == pytest.approx(game["excel_CJ_away_run_prevention_z"], abs=1e-6)
    assert away.run_off_z == pytest.approx(game["excel_CL_away_run_off_z"], abs=1e-6)
    assert home.run_prevention_z == pytest.approx(game["excel_CM_home_run_prevention_z"], abs=1e-6)

    home_adj, away_adj = explosive_play_matchup_adj(
        home.pass_off_z, away.pass_prevention_composite_z,
        away.pass_off_z, home.pass_prevention_composite_z,
        home.run_off_z, away.run_prevention_z,
        away.run_off_z, home.run_prevention_z,
        conv["pass_conv"], conv["run_conv"],
    )
    assert home_adj == pytest.approx(game["excel_CO_home_adj"], abs=1e-6), (
        f"{_game_id(game)} Home Explosive Play Matchup Adj mismatch: "
        f"Python={home_adj}, Excel={game['excel_CO_home_adj']}"
    )
    assert away_adj == pytest.approx(game["excel_CP_away_adj"], abs=1e-6), (
        f"{_game_id(game)} Away Explosive Play Matchup Adj mismatch: "
        f"Python={away_adj}, Excel={game['excel_CP_away_adj']}"
    )
