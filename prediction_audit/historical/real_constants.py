"""
Step 7 rigor fix: extracts the REAL Model Assumptions constants (weights, conversions,
thresholds) directly from the frozen v35 workbook, replacing `demo_full_game_prediction.py`'s
own representative approximations. These constants are real, timeless MODEL DESIGN choices
(reusable for any historical target season, since they define how the model weighs signals,
not a season-specific fact) -- confirmed live against the real frozen file, not guessed.

Real corrections this caught versus the earlier representative demo constants (documented,
not silently fixed): QB Index ANY/A weight is really 0.3 (not 0.2); QB Index Points-to-Game-
Points Conversion (C39) is really 0.15 (not 0.3); RB Index RYOE/Att weight (C82) is really
0.35 (not 0.2); several Pass/Run Defense Matchup and Explosive Play Matchup weights were off
by small amounts. C92/C99 (Pass/Run Defense Matchup's own "Points-to-Game-Points Conversion")
are confirmed DEAD constants (Step 1's own real finding -- never read by any real formula);
those tabs' own real Score conversion uses the standard C37/C38 (score_baseline/points_per_sd)
instead, matching QB Index's own real conversion, not a separate constant.

Real, honest scope: `league_avg`/`league_std` for every tab are NOT extracted here -- those
are real, per-season COMPUTED values (each tab's own real Section 4), not fixed workbook
constants, and belong in a separate real per-target-season resolution
(`resolve_*_league_stats()`, already built for every tab in this package) rather than a
one-time extraction from the frozen file. This module still requires them as caller-supplied
arguments for that reason.
"""
from __future__ import annotations

import openpyxl

from prediction_audit.engine.core_formula_simple_terms import (
    RestEffectConstants,
    WeatherAdjConstants,
)
from prediction_audit.engine.explosive_play_matchup import ExplosivePlayMatchupConstants
from prediction_audit.engine.offensive_line_index import OLIndexConstants
from prediction_audit.engine.pass_defense_matchup import PassDefenseMatchupConstants
from prediction_audit.engine.pass_rush_generation_index import PassRushGenerationConstants
from prediction_audit.engine.qb_environment_model import QBEnvironmentModelConstants
from prediction_audit.engine.qb_index import QBIndexConstants
from prediction_audit.engine.rb_index import RBIndexConstants
from prediction_audit.engine.run_defense_matchup import RunDefenseMatchupConstants
from prediction_audit.engine.team_quality import TeamQualityConstants
from prediction_audit.engine.team_specific_hfa import TeamSpecificHFAConstants
from prediction_audit.historical.full_game_prediction import HistoricalGameModelConstants


def load_real_model_assumptions(frozen_xlsx_path: str) -> dict[int, float]:
    """Real Model Assumptions C-column values, keyed by row number, for every real constant
    this composition needs. A live, direct read of the frozen file -- never hardcoded."""
    wb = openpyxl.load_workbook(frozen_xlsx_path, data_only=True)
    ma = wb["Model Assumptions"]
    rows = [
        3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 20, 21, 22, 34, 35, 36, 37, 38, 39,
        44, 45, 46, 47, 58, 59, 67, 81, 82, 87, 88, 89, 90, 91, 94, 95, 96, 97, 98,
        101, 102, 119, 120, 121, 123, 124, 128, 129, 130, 131, 133, 134, 136, 137, 138,
        150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160,
    ]
    return {r: ma.cell(row=r, column=3).value for r in rows}


def _split(stats: dict[str, dict[str, float]]) -> tuple[dict[str, float], dict[str, float]]:
    """`resolve_*_league_stats()` returns {metric: {"avg":X, "std":Y}} -- splits that real
    shape into the (league_avg, league_std) dict pair every *Constants dataclass expects."""
    avg = {key: values["avg"] for key, values in stats.items()}
    std = {key: values["std"] for key, values in stats.items()}
    return avg, std


def build_real_constants(
    frozen_xlsx_path: str,
    qb_index_league_stats: dict[str, dict[str, float]],
    rb_index_league_stats: dict[str, dict[str, float]],
    ol_index_league_stats: dict[str, dict[str, float]],
    pass_rush_generation_league_stats: dict[str, dict[str, float]],
    pass_defense_matchup_league_stats: dict[str, dict[str, float]],
    run_defense_matchup_league_stats: dict[str, dict[str, float]],
    qb_environment_model_league_stats: dict[str, dict[str, float]],
    explosive_play_matchup_league_stats: dict[str, dict[str, float]],
) -> HistoricalGameModelConstants:
    """Assembles a real `HistoricalGameModelConstants` from the frozen file's own real weight/
    conversion/threshold constants, plus caller-supplied real per-target-season league stats
    (each from this package's own `resolve_*_league_stats()` for the real target season --
    never approximated here)."""
    c = load_real_model_assumptions(frozen_xlsx_path)

    qb_avg, qb_std = _split(qb_index_league_stats)
    rb_avg, rb_std = _split(rb_index_league_stats)
    ol_avg, ol_std = _split(ol_index_league_stats)
    prg_avg, prg_std = _split(pass_rush_generation_league_stats)
    pd_avg, pd_std = _split(pass_defense_matchup_league_stats)
    rd_avg, rd_std = _split(run_defense_matchup_league_stats)
    qbe_avg, qbe_std = _split(qb_environment_model_league_stats)
    ep_avg, ep_std = _split(explosive_play_matchup_league_stats)

    return HistoricalGameModelConstants(
        team_quality=TeamQualityConstants(
            decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
            blend_base=c[12], blend_per_game=c[13], blend_cap=c[14],
        ),
        team_specific_hfa=TeamSpecificHFAConstants(
            decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
        ),
        rest_effect=RestEffectConstants(
            low_threshold=c[150], high_threshold=c[151], low_val=c[152], mid_val=c[153],
            high_val=c[154],
        ),
        weather_adj=WeatherAdjConstants(
            wind_threshold=c[6], wind_adj=c[7], cold_threshold=c[8], cold_adj=c[9],
            precip_adj=c[10], snow_adj=c[158], humidity_threshold=c[159],
            humidity_adj=c[160],
        ),
        division_adj_const=c[11],
        qb_index=QBIndexConstants(
            decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
            blend_base=c[12], blend_per_game=c[13], blend_cap=c[14],
            weights={"epa": c[34], "cpoe": c[35], "anya": c[36]},
            score_baseline=c[37], points_per_sd=c[38],
            league_avg=qb_avg, league_std=qb_std,
        ),
        ol_index=OLIndexConstants(
            decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
            blend_base=c[12], blend_per_game=c[13], blend_cap=c[14],
            weights={"pass_protection": c[58], "run_blocking": c[59],
                     "sack_free_rate": c[81]},
            score_baseline=c[37], points_per_sd=c[38],
            league_avg=ol_avg, league_std=ol_std,
        ),
        pass_rush_generation=PassRushGenerationConstants(
            decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
            weights={"sack_rate": c[119], "pressure_proxy": c[120], "blitz_rate": c[121]},
            league_avg=prg_avg, league_std=prg_std,
        ),
        pass_defense_matchup=PassDefenseMatchupConstants(
            decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
            weights={"epa_dropback": c[87], "pass_success": c[88], "completion_pct": c[89],
                     "nya": c[90], "explosive_pass": c[91]},
            score_baseline=c[37], points_per_sd=c[38],
            league_avg=pd_avg, league_std=pd_std,
        ),
        run_defense_matchup=RunDefenseMatchupConstants(
            decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
            weights={"epa_rush": c[94], "run_success": c[95], "ypc": c[96],
                     "explosive_run": c[97], "stuff_rate": c[98]},
            score_baseline=c[37], points_per_sd=c[38],
            league_avg=rd_avg, league_std=rd_std,
        ),
        rb_index=RBIndexConstants(
            decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
            blend_base=c[12], blend_per_game=c[13], blend_cap=c[14],
            weights={"rushing_epa": c[44], "rushing_sr": c[45], "ypc": c[46],
                     "ryoe": c[82], "rz_share": c[124]},
            score_baseline=c[37], points_per_sd=c[38],
            league_avg=rb_avg, league_std=rb_std,
        ),
        qb_environment_model=QBEnvironmentModelConstants(
            decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
            league_avg=qbe_avg, league_std=qbe_std,
            success_weight=c[128], explosive_weight=c[129], epa_weight=c[34],
            cpoe_weight=c[35], anya_weight=c[36], score_baseline=c[37],
            points_per_sd=c[38], new_team_penalty=c[130],
            recently_injured_penalty=c[131],
        ),
        explosive_play_matchup=ExplosivePlayMatchupConstants(
            decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
            league_avg_pass_off=ep_avg["pass_off"], league_std_pass_off=ep_std["pass_off"],
            league_avg_run_off=ep_avg["run_off"], league_std_run_off=ep_std["run_off"],
            league_avg_deep_pass_allowed=ep_avg["deep_pass_allowed"],
            league_std_deep_pass_allowed=ep_std["deep_pass_allowed"],
            league_avg_yac_allowed=ep_avg["yac_allowed"],
            league_std_yac_allowed=ep_std["yac_allowed"],
            pass_prevention_w_explosive_pass_allowed=c[136],
            pass_prevention_w_deep_pass_allowed=c[137],
            pass_prevention_w_yac_allowed=c[138],
        ),
        flat_hfa=c[3], pass_matchup_conversion=c[101], run_matchup_conversion=c[102],
        ol_pressure_conversion=c[123], ol_modifier_scaling=c[133],
        weather_modifier_scaling=c[134], road_fatigue_threshold=c[155],
        road_fatigue_penalty=c[156], qb_replacement_conversion=c[39],
        travel_coefficient=c[5], west_to_east_penalty=c[157],
    )
