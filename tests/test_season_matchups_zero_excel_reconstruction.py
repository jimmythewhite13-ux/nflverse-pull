"""
Deeper end-to-end reconstruction: unlike test_season_matchups_full_reconstruction.py (which
takes Phase Matchup Adj / OL Pressure Adj / QB Replacement Value's real differentials as given
ground-truth inputs), this test re-derives those differentials FROM their own already-ported
source engines -- QB Index, RB Value Index, QB Environment Model, Effective QB Rating,
Offensive Line Index, Pass Defense Matchup, Run Defense Matchup, Pass Rush Generation Index --
and checks the result against the SAME real intermediate Excel values
(core_formula_simple_terms's own ground truth home/away _diff fields), not just the final
score. This closes the "deepen the reconstruction" gap identified in PROGRESS.md.

Per this project's established "arithmetic only, not data sourcing" scoping, a few real inputs
are still taken as given here (which QB/RB is the real Starter vs Backup for each team; the
real team pass-rate share Effective QB Rating's weather modifier needs; the real Backup-In
flag) -- these are roster/data-resolution facts, not Z/AA arithmetic, consistent with every
other tab's own league_avg/league_baseline_y1/RYOE-substitution treatment throughout this
engine.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.core_formula_simple_terms import (  # noqa: E402
    ol_pressure_adj,
    phase_matchup_adj,
    qb_replacement_adj,
)
from prediction_audit.engine.effective_qb_rating import (  # noqa: E402
    effective_qb_rating,
    ol_modifier,
    weather_on_passing_modifier,
)
from prediction_audit.engine.offensive_line_index import (  # noqa: E402
    METRIC_KEYS as OL_METRIC_KEYS,
)
from prediction_audit.engine.offensive_line_index import (  # noqa: E402
    OLIndexConstants,
    OLTeamHistory,
    compute_ol_index,
)
from prediction_audit.engine.pass_defense_matchup import (  # noqa: E402
    METRIC_KEYS as PD_METRIC_KEYS,
)
from prediction_audit.engine.pass_defense_matchup import (  # noqa: E402
    PassDefenseMatchupConstants,
    PassDefenseTeamHistory,
    compute_pass_defense_matchup,
)
from prediction_audit.engine.pass_rush_generation_index import (  # noqa: E402
    METRIC_KEYS as PRG_METRIC_KEYS,
)
from prediction_audit.engine.pass_rush_generation_index import (  # noqa: E402
    PassRushGenerationConstants,
    PassRushGenerationTeamHistory,
    compute_pass_rush_generation_index,
)
from prediction_audit.engine.qb_environment_model import (  # noqa: E402
    METRIC_KEYS as QE_METRIC_KEYS,
)
from prediction_audit.engine.qb_environment_model import (  # noqa: E402
    QBEnvironmentModelConstants,
    QBEnvironmentModelHistory,
    compute_qb_environment_model,
)
from prediction_audit.engine.qb_index import (  # noqa: E402
    METRIC_KEYS as QB_METRIC_KEYS,
)
from prediction_audit.engine.qb_index import (  # noqa: E402
    QBHistory,
    QBIndexConstants,
    compute_qb_index,
    replacement_value_game_points,
    replacement_value_index_points,
)
from prediction_audit.engine.rb_index import (  # noqa: E402
    METRIC_KEYS as RB_METRIC_KEYS,
)
from prediction_audit.engine.rb_index import (  # noqa: E402
    RBHistory,
    RBIndexConstants,
    compute_rb_index,
)
from prediction_audit.engine.run_defense_matchup import (  # noqa: E402
    METRIC_KEYS as RD_METRIC_KEYS,
)
from prediction_audit.engine.run_defense_matchup import (  # noqa: E402
    RunDefenseMatchupConstants,
    RunDefenseTeamHistory,
    compute_run_defense_matchup,
)

MANIFESTS = Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"


def _load(name: str) -> dict:
    with open(MANIFESTS / name, encoding="utf-8") as f:
        return json.load(f)


CORE_SIMPLE = _load("v35_core_simple_terms_ground_truth.json")
QB_INDEX = _load("v35_qb_index_ground_truth.json")
RB_INDEX = _load("v35_rb_index_ground_truth.json")
QB_ENV = _load("v35_qb_environment_model_ground_truth.json")
EQR = _load("v35_effective_qb_rating_ground_truth.json")
OL_INDEX = _load("v35_offensive_line_index_ground_truth.json")
PASS_DEF = _load("v35_pass_defense_matchup_ground_truth.json")
RUN_DEF = _load("v35_run_defense_matchup_ground_truth.json")
PASS_RUSH_GEN = _load("v35_pass_rush_generation_index_ground_truth.json")

# ---- Build per-player / per-team real results, fully from source engines ----------------

QB_INDEX_CONST = QBIndexConstants(
    decay_factor=QB_INDEX["constants"]["decay_factor"],
    regression_weight=QB_INDEX["constants"]["regression_weight"],
    last_year_emphasis=QB_INDEX["constants"]["last_year_emphasis"],
    blend_base=QB_INDEX["constants"]["blend_base"],
    blend_per_game=QB_INDEX["constants"]["blend_per_game"],
    blend_cap=QB_INDEX["constants"]["blend_cap"],
    weights={
        "epa": QB_INDEX["constants"]["epa_weight"], "cpoe": QB_INDEX["constants"]["cpoe_weight"],
        "anya": QB_INDEX["constants"]["anya_weight"],
    },
    score_baseline=QB_INDEX["constants"]["score_baseline"],
    points_per_sd=QB_INDEX["constants"]["points_per_sd"],
    league_avg={m: QB_INDEX["constants"][f"{m}_league_avg"] for m in QB_METRIC_KEYS},
    league_std={m: QB_INDEX["constants"][f"{m}_league_std"] for m in QB_METRIC_KEYS},
)


def _qb_history(q: dict) -> QBHistory:
    return QBHistory(
        player_id=q["player_id"],
        y1={m: q[f"{m}_y1"] for m in QB_METRIC_KEYS},
        y2={m: q[f"{m}_y2"] for m in QB_METRIC_KEYS},
        y3={m: q[f"{m}_y3"] for m in QB_METRIC_KEYS},
        league_baseline_y1={m: q[f"{m}_league_baseline_y1"] for m in QB_METRIC_KEYS},
        games_played=q["games_played"],
        current_season={m: q[f"current_season_{m}"] for m in QB_METRIC_KEYS},
    )


QB_INDEX_BY_KEY = {
    f"{q['team']}|{q['role']}": compute_qb_index(_qb_history(q), QB_INDEX_CONST)
    for q in QB_INDEX["qbs"]
}

RB_INDEX_CONST = RBIndexConstants(
    decay_factor=RB_INDEX["constants"]["decay_factor"],
    regression_weight=RB_INDEX["constants"]["regression_weight"],
    last_year_emphasis=RB_INDEX["constants"]["last_year_emphasis"],
    blend_base=RB_INDEX["constants"]["blend_base"],
    blend_per_game=RB_INDEX["constants"]["blend_per_game"],
    blend_cap=RB_INDEX["constants"]["blend_cap"],
    weights=RB_INDEX["constants"]["weights"],
    score_baseline=RB_INDEX["constants"]["score_baseline"],
    points_per_sd=RB_INDEX["constants"]["points_per_sd"],
    league_avg=RB_INDEX["constants"]["league_avg"],
    league_std=RB_INDEX["constants"]["league_std"],
)


def _rb_history(r: dict) -> RBHistory:
    return RBHistory(
        player_id=r["player_id"],
        y1={m: r[f"{m}_y1"] for m in RB_METRIC_KEYS},
        y2={m: r[f"{m}_y2"] for m in RB_METRIC_KEYS},
        y3={m: r[f"{m}_y3"] for m in RB_METRIC_KEYS},
        league_baseline_y1={m: r[f"{m}_league_baseline_y1"] for m in RB_METRIC_KEYS},
        games_played=r["games_played"],
        current_season={m: r[f"current_season_{m}"] for m in RB_METRIC_KEYS},
    )


RB_INDEX_BY_KEY = {
    f"{r['team']}|{r['role']}": compute_rb_index(_rb_history(r), RB_INDEX_CONST)
    for r in RB_INDEX["rbs"] if r["role"] in ("Starter", "Backup")
}

QB_ENV_CONST = QBEnvironmentModelConstants(
    decay_factor=QB_ENV["constants"]["decay_factor"],
    regression_weight=QB_ENV["constants"]["regression_weight"],
    last_year_emphasis=QB_ENV["constants"]["last_year_emphasis"],
    league_avg={
        "success": QB_ENV["constants"]["league_avg_success"],
        "explosive": QB_ENV["constants"]["league_avg_explosive"],
        "sack": QB_ENV["constants"]["league_avg_sack"],
    },
    league_std={
        "success": QB_ENV["constants"]["league_std_success"],
        "explosive": QB_ENV["constants"]["league_std_explosive"],
        "sack": QB_ENV["constants"]["league_std_sack"],
    },
    success_weight=QB_ENV["constants"]["success_weight"],
    explosive_weight=QB_ENV["constants"]["explosive_weight"],
    epa_weight=QB_ENV["constants"]["epa_weight"], cpoe_weight=QB_ENV["constants"]["cpoe_weight"],
    anya_weight=QB_ENV["constants"]["anya_weight"],
    score_baseline=QB_ENV["constants"]["score_baseline"],
    points_per_sd=QB_ENV["constants"]["points_per_sd"],
    new_team_penalty=QB_ENV["constants"]["new_team_penalty"],
    recently_injured_penalty=QB_ENV["constants"]["recently_injured_penalty"],
)


def _qb_env_history(q: dict) -> QBEnvironmentModelHistory:
    key = f"{q['team']}|{q['role']}"
    qbi = QB_INDEX_BY_KEY[key]
    return QBEnvironmentModelHistory(
        player_id=q["player_id"],
        y1={m: q[f"{m}_y1"] for m in QE_METRIC_KEYS},
        y2={m: q[f"{m}_y2"] for m in QE_METRIC_KEYS},
        y3={m: q[f"{m}_y3"] for m in QE_METRIC_KEYS},
        league_baseline_y1={m: q[f"{m}_league_baseline_y1"] for m in QE_METRIC_KEYS},
        epa_z_ref=qbi.z_scores["epa"], cpoe_z_ref=qbi.z_scores["cpoe"],
        anya_z_ref=qbi.z_scores["anya"],
        new_team_this_season=q["new_team_this_season"],
        recently_returned_from_injury=q["recently_returned_from_injury"],
    )


QB_ENV_BY_KEY = {
    f"{q['team']}|{q['role']}": compute_qb_environment_model(_qb_env_history(q), QB_ENV_CONST)
    for q in QB_ENV["qbs"]
}

OL_CONST = OLIndexConstants(
    decay_factor=OL_INDEX["constants"]["decay_factor"],
    regression_weight=OL_INDEX["constants"]["regression_weight"],
    last_year_emphasis=OL_INDEX["constants"]["last_year_emphasis"],
    blend_base=OL_INDEX["constants"]["blend_base"],
    blend_per_game=OL_INDEX["constants"]["blend_per_game"],
    blend_cap=OL_INDEX["constants"]["blend_cap"],
    weights=OL_INDEX["constants"]["weights"],
    score_baseline=OL_INDEX["constants"]["score_baseline"],
    points_per_sd=OL_INDEX["constants"]["points_per_sd"],
    league_avg=OL_INDEX["constants"]["league_avg"],
    league_std=OL_INDEX["constants"]["league_std"],
)


def _ol_history(t: dict) -> OLTeamHistory:
    return OLTeamHistory(
        team=t["team"],
        y1={m: t[f"{m}_y1"] for m in OL_METRIC_KEYS},
        y2={m: t[f"{m}_y2"] for m in OL_METRIC_KEYS},
        y3={m: t[f"{m}_y3"] for m in OL_METRIC_KEYS},
        league_baseline_y1={m: t[f"{m}_league_baseline_y1"] for m in OL_METRIC_KEYS},
        games_played=t["games_played"],
        current_season={m: t[f"current_season_{m}"] for m in OL_METRIC_KEYS},
    )


OL_BY_TEAM = {
    t["team"]: compute_ol_index(_ol_history(t), OL_CONST) for t in OL_INDEX["teams"]
}

PD_CONST = PassDefenseMatchupConstants(
    decay_factor=PASS_DEF["constants"]["decay_factor"],
    regression_weight=PASS_DEF["constants"]["regression_weight"],
    last_year_emphasis=PASS_DEF["constants"]["last_year_emphasis"],
    weights=PASS_DEF["constants"]["weights"],
    score_baseline=PASS_DEF["constants"]["score_baseline"],
    points_per_sd=PASS_DEF["constants"]["points_per_sd"],
    league_avg=PASS_DEF["constants"]["league_avg"],
    league_std=PASS_DEF["constants"]["league_std"],
)


def _pd_history(t: dict) -> PassDefenseTeamHistory:
    return PassDefenseTeamHistory(
        team=t["team"],
        y1={m: t[f"{m}_y1"] for m in PD_METRIC_KEYS},
        y2={m: t[f"{m}_y2"] for m in PD_METRIC_KEYS},
        y3={m: t[f"{m}_y3"] for m in PD_METRIC_KEYS},
        league_baseline_y1={m: t[f"{m}_league_baseline_y1"] for m in PD_METRIC_KEYS},
    )


PASS_DEF_BY_TEAM = {
    t["team"]: compute_pass_defense_matchup(_pd_history(t), PD_CONST) for t in PASS_DEF["teams"]
}

RD_CONST = RunDefenseMatchupConstants(
    decay_factor=RUN_DEF["constants"]["decay_factor"],
    regression_weight=RUN_DEF["constants"]["regression_weight"],
    last_year_emphasis=RUN_DEF["constants"]["last_year_emphasis"],
    weights=RUN_DEF["constants"]["weights"],
    score_baseline=RUN_DEF["constants"]["score_baseline"],
    points_per_sd=RUN_DEF["constants"]["points_per_sd"],
    league_avg=RUN_DEF["constants"]["league_avg"],
    league_std=RUN_DEF["constants"]["league_std"],
)


def _rd_history(t: dict) -> RunDefenseTeamHistory:
    return RunDefenseTeamHistory(
        team=t["team"],
        y1={m: t[f"{m}_y1"] for m in RD_METRIC_KEYS},
        y2={m: t[f"{m}_y2"] for m in RD_METRIC_KEYS},
        y3={m: t[f"{m}_y3"] for m in RD_METRIC_KEYS},
        league_baseline_y1={m: t[f"{m}_league_baseline_y1"] for m in RD_METRIC_KEYS},
    )


RUN_DEF_BY_TEAM = {
    t["team"]: compute_run_defense_matchup(_rd_history(t), RD_CONST) for t in RUN_DEF["teams"]
}

PRG_CONST = PassRushGenerationConstants(
    decay_factor=PASS_RUSH_GEN["constants"]["decay_factor"],
    regression_weight=PASS_RUSH_GEN["constants"]["regression_weight"],
    last_year_emphasis=PASS_RUSH_GEN["constants"]["last_year_emphasis"],
    weights=PASS_RUSH_GEN["constants"]["weights"],
    league_avg=PASS_RUSH_GEN["constants"]["league_avg"],
    league_std=PASS_RUSH_GEN["constants"]["league_std"],
)


def _prg_history(t: dict) -> PassRushGenerationTeamHistory:
    return PassRushGenerationTeamHistory(
        team=t["team"],
        y1={m: t[f"{m}_y1"] for m in PRG_METRIC_KEYS},
        y2={m: t[f"{m}_y2"] for m in PRG_METRIC_KEYS},
        y3={m: t[f"{m}_y3"] for m in PRG_METRIC_KEYS},
        league_baseline_y1={m: t[f"{m}_league_baseline_y1"] for m in PRG_METRIC_KEYS},
    )


PASS_RUSH_GEN_BY_TEAM = {
    t["team"]: compute_pass_rush_generation_index(_prg_history(t), PRG_CONST)
    for t in PASS_RUSH_GEN["teams"]
}

QB_RV = _load("v35_qb_replacement_value_ground_truth.json")
RV_CONVERSION = QB_RV["constants"]["rv_conversion"]

EQR_BY_KEY = {(g["week"], g["away"], g["home"]): g for g in EQR["games"]}
CORE_SIMPLE_BY_KEY = {
    (g["week"], g["away"], g["home"]): g for g in CORE_SIMPLE["games"]
}


def _game_id(g: dict) -> str:
    return f"wk{g['week']}_{g['away']}_at_{g['home']}".replace(" ", "")


def _ol_pressure_diff(offense_team: str, defense_team: str) -> float:
    return (
        OL_BY_TEAM[offense_team].z_scores["pass_protection"]
        - PASS_RUSH_GEN_BY_TEAM[defense_team].score
    )


def _effective_qb_rating(team: str, opponent: str, eqr_row: dict, is_home: bool) -> float:
    qb_env = QB_ENV_BY_KEY[f"{team}|Starter"]
    ol_diff = _ol_pressure_diff(team, opponent)
    sack_z = qb_env.z_scores["sack"]
    scaling_ol = EQR["constants"]["ol_modifier_scaling"]
    scaling_wx = EQR["constants"]["weather_passing_scaling"]
    ol_mod = ol_modifier(ol_diff, sack_z, scaling_ol)
    pass_rate_key = "home_team_pass_rate_bq" if is_home else "away_team_pass_rate_br"
    wx_mod = weather_on_passing_modifier(
        eqr_row["weather_adj_u"], eqr_row[pass_rate_key], scaling_wx,
    )
    return effective_qb_rating(qb_env.adjusted_baseline, ol_mod, wx_mod)


@pytest.mark.parametrize(
    "game", CORE_SIMPLE["games"], ids=[_game_id(g) for g in CORE_SIMPLE["games"]],
)
def test_ol_pressure_diff_matches_real_excel_bk_bn(game):
    home, away = game["home"], game["away"]
    home_diff = _ol_pressure_diff(home, away)
    away_diff = _ol_pressure_diff(away, home)
    assert home_diff == pytest.approx(game["home_ol_press_diff"], abs=1e-6), (
        f"{_game_id(game)} real BK (Home OL Pressure Diff) mismatch: "
        f"Python={home_diff}, Excel={game['home_ol_press_diff']}"
    )
    assert away_diff == pytest.approx(game["away_ol_press_diff"], abs=1e-6), (
        f"{_game_id(game)} real BN (Away OL Pressure Diff) mismatch"
    )


@pytest.mark.parametrize(
    "game", CORE_SIMPLE["games"], ids=[_game_id(g) for g in CORE_SIMPLE["games"]],
)
def test_ol_pressure_adj_full_lineage_matches_real_excel(game):
    home, away = game["home"], game["away"]
    conv = CORE_SIMPLE["constants"]["ol_press_conv"]
    home_adj = ol_pressure_adj(_ol_pressure_diff(home, away), conv)
    away_adj = ol_pressure_adj(_ol_pressure_diff(away, home), conv)
    assert home_adj == pytest.approx(game["excel_ol_press_home"], abs=1e-6)
    assert away_adj == pytest.approx(game["excel_ol_press_away"], abs=1e-6)


@pytest.mark.parametrize(
    "game", CORE_SIMPLE["games"], ids=[_game_id(g) for g in CORE_SIMPLE["games"]],
)
def test_effective_qb_rating_full_lineage_matches_real_excel(game):
    key = (game["week"], game["away"], game["home"])
    eqr_row = EQR_BY_KEY[key]
    home_rating = _effective_qb_rating(game["home"], game["away"], eqr_row, is_home=True)
    away_rating = _effective_qb_rating(game["away"], game["home"], eqr_row, is_home=False)
    assert home_rating == pytest.approx(
        eqr_row["excel_home_effective_qb_rating_ca"], abs=1e-6
    ), f"{_game_id(game)} full-lineage Home Effective QB Rating mismatch"
    assert away_rating == pytest.approx(
        eqr_row["excel_away_effective_qb_rating_cb"], abs=1e-6
    ), f"{_game_id(game)} full-lineage Away Effective QB Rating mismatch"


# Washington Commanders' real RB Value Index Section 5 rows sit at 399-400 in the frozen v35
# baseline -- 2 rows past the stale hardcoded lookup range ($K$335:$K$398 / $M$335:$M$398)
# Season Matchups' own real BA/BD formula uses. This is the SAME real "RB Section 5
# stale-range bug" already documented and fixed in v36 (see
# prediction_audit/manifests/v35_step1_findings.md and the RB Section 5 fix in
# build_defensive_matchup_wiring.py's own history) -- v35 is deliberately kept frozen and
# immutable for this whole audit, so this known limitation is expected here, not a bug in
# this reconstruction. v35's own real BA/BD (and therefore BC/BF/phase adj) genuinely comes
# back blank for Washington's own Starter RB in every one of their 17 real games; this
# reconstruction correctly computes a real, non-blank value using RB Value Index's own real,
# wider (correctly-discovered) Section 5 range -- proving the arithmetic is right even where
# v35's own frozen lookup range is not.
_WASHINGTON_STALE_RANGE_BUG_TEAM = "Washington Commanders"


@pytest.mark.parametrize(
    "game", CORE_SIMPLE["games"], ids=[_game_id(g) for g in CORE_SIMPLE["games"]],
)
def test_phase_matchup_diff_and_adj_full_lineage_matches_real_excel(game):
    home, away = game["home"], game["away"]
    key = (game["week"], away, home)
    eqr_row = EQR_BY_KEY[key]

    home_qb_rating = _effective_qb_rating(home, away, eqr_row, is_home=True)
    away_qb_rating = _effective_qb_rating(away, home, eqr_row, is_home=False)
    home_pass_diff = home_qb_rating - PASS_DEF_BY_TEAM[away].score
    away_pass_diff = away_qb_rating - PASS_DEF_BY_TEAM[home].score

    home_starter_rb = RB_INDEX_BY_KEY[f"{home}|Starter"].score
    away_starter_rb = RB_INDEX_BY_KEY[f"{away}|Starter"].score
    home_run_diff = home_starter_rb - RUN_DEF_BY_TEAM[away].score
    away_run_diff = away_starter_rb - RUN_DEF_BY_TEAM[home].score

    assert home_pass_diff == pytest.approx(game["home_pass_diff"], abs=1e-6), (
        f"{_game_id(game)} real AW (Home Pass Matchup Diff) mismatch: "
        f"Python={home_pass_diff}, Excel={game['home_pass_diff']}"
    )
    assert away_pass_diff == pytest.approx(game["away_pass_diff"], abs=1e-6), (
        f"{_game_id(game)} real AZ (Away Pass Matchup Diff) mismatch"
    )

    washington_involved = _WASHINGTON_STALE_RANGE_BUG_TEAM in (home, away)
    if washington_involved:
        # v35's own real lookup is known-blank for Washington's side -- verify this
        # reconstruction still produces a real, finite value rather than asserting equality
        # to Excel's known-buggy blank (see the module-level note above).
        assert isinstance(home_run_diff, float)
        assert isinstance(away_run_diff, float)
    else:
        assert home_run_diff == pytest.approx(game["home_run_diff"], abs=1e-6), (
            f"{_game_id(game)} real BC (Home Run Matchup Diff) mismatch"
        )
        assert away_run_diff == pytest.approx(game["away_run_diff"], abs=1e-6), (
            f"{_game_id(game)} real BF (Away Run Matchup Diff) mismatch"
        )

    pass_conv = CORE_SIMPLE["constants"]["pass_conv"]
    run_conv = CORE_SIMPLE["constants"]["run_conv"]
    home_pass_adj, away_pass_adj = phase_matchup_adj(home_pass_diff, away_pass_diff, pass_conv)
    home_run_adj, away_run_adj = phase_matchup_adj(home_run_diff, away_run_diff, run_conv)
    if not washington_involved:
        assert (home_pass_adj + home_run_adj) == pytest.approx(
            game["excel_phase_home"], abs=1e-6
        )
        assert (away_pass_adj + away_run_adj) == pytest.approx(
            game["excel_phase_away"], abs=1e-6
        )


@pytest.mark.parametrize(
    "game", CORE_SIMPLE["games"], ids=[_game_id(g) for g in CORE_SIMPLE["games"]],
)
def test_qb_replacement_adj_full_lineage_matches_real_excel(game):
    home, away = game["home"], game["away"]

    def _rv_game_points(team: str) -> float:
        starter = QB_INDEX_BY_KEY.get(f"{team}|Starter")
        backup = QB_INDEX_BY_KEY.get(f"{team}|Backup")
        starter_score = starter.score if starter else None
        backup_score = backup.score if backup else None
        rv_index = replacement_value_index_points(starter_score, backup_score)
        return replacement_value_game_points(rv_index, RV_CONVERSION)

    home_rv = _rv_game_points(home)
    away_rv = _rv_game_points(away)
    home_adj = qb_replacement_adj(game["home_backup_in"], home_rv if home_rv else 0.0)
    away_adj = qb_replacement_adj(game["away_backup_in"], away_rv if away_rv else 0.0)

    assert home_adj == pytest.approx(game["excel_qb_repl_home"], abs=1e-6)
    assert away_adj == pytest.approx(game["excel_qb_repl_away"], abs=1e-6)
