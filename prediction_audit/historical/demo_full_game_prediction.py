"""
Step 6's own culminating proof of concept: a real, end-to-end historical Model Home/Away
Score for one real past game, composing all 16 real Z/AA components this session built
(see PROGRESS.md's own summary table) via `resolve_historical_model_home_away_score()`.

The target game is picked programmatically (first real game of the target week, by real
game_id sort order) -- not hand-selected -- to avoid any appearance of cherry-picking a result
that happens to look good.

Real, honest caveat on the constants below: these are real, plausible Model Assumptions-style
values matching what this session's own individual resolver verifications already used and
found sane (real league averages/std-devs discovered live against 2024/2025 data throughout
this session) -- NOT freshly re-extracted from a live 'Model Assumptions' sheet specifically
for this composition. A production run should pull them from the real frozen v35 Model
Assumptions sheet directly, the same way every ground-truth extraction elsewhere in this
project does.

Usage:
    uv run python prediction_audit/historical/demo_full_game_prediction.py [season] [week]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.oline_stats import fetch_ftn, fetch_pfr_pass, fetch_pfr_rush  # noqa: E402
from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from nflverse_pull.rb_stats import fetch_ngs_rushing  # noqa: E402
from prediction_audit.engine.core_formula_simple_terms import (  # noqa: E402
    RestEffectConstants,
    WeatherAdjConstants,
)
from prediction_audit.engine.explosive_play_matchup import (  # noqa: E402
    ExplosivePlayMatchupConstants,
)
from prediction_audit.engine.offensive_line_index import OLIndexConstants  # noqa: E402
from prediction_audit.engine.pass_defense_matchup import PassDefenseMatchupConstants  # noqa: E402
from prediction_audit.engine.pass_rush_generation_index import (  # noqa: E402
    PassRushGenerationConstants,
)
from prediction_audit.engine.qb_environment_model import QBEnvironmentModelConstants  # noqa: E402
from prediction_audit.engine.qb_index import QBIndexConstants  # noqa: E402
from prediction_audit.engine.rb_index import RBIndexConstants  # noqa: E402
from prediction_audit.engine.run_defense_matchup import RunDefenseMatchupConstants  # noqa: E402
from prediction_audit.engine.team_quality import TeamQualityConstants  # noqa: E402
from prediction_audit.engine.team_specific_hfa import TeamSpecificHFAConstants  # noqa: E402
from prediction_audit.historical.full_game_prediction import (  # noqa: E402
    HistoricalGameDataBundle,
    HistoricalGameModelConstants,
    resolve_historical_model_home_away_score,
)


def _build_constants() -> HistoricalGameModelConstants:
    return HistoricalGameModelConstants(
        team_quality=TeamQualityConstants(
            decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
            blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
        ),
        team_specific_hfa=TeamSpecificHFAConstants(
            decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        ),
        rest_effect=RestEffectConstants(
            low_threshold=4, high_threshold=10, low_val=-1.5, mid_val=0.0, high_val=1.0,
        ),
        weather_adj=WeatherAdjConstants(
            wind_threshold=15, wind_adj=-3, cold_threshold=32, cold_adj=-2,
            precip_adj=-2, snow_adj=-1.5, humidity_threshold=70, humidity_adj=-0.5,
        ),
        division_adj_const=-1.0,
        qb_index=QBIndexConstants(
            decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
            blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
            weights={"epa": 0.5, "cpoe": 0.3, "anya": 0.2}, score_baseline=50,
            points_per_sd=10, league_avg={"epa": 0.10, "cpoe": 1.5, "anya": 6.2},
            league_std={"epa": 0.10, "cpoe": 2.5, "anya": 1.0},
        ),
        ol_index=OLIndexConstants(
            decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
            blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
            weights={"pass_protection": 0.4, "run_blocking": 0.3, "sack_free_rate": 0.3},
            score_baseline=50, points_per_sd=10,
            league_avg={"pass_protection": 75.9, "run_blocking": 2.49,
                        "sack_free_rate": 0.957},
            league_std={"pass_protection": 1.31, "run_blocking": 0.11,
                        "sack_free_rate": 0.005},
        ),
        pass_rush_generation=PassRushGenerationConstants(
            decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
            weights={"sack_rate": 0.5, "pressure_proxy": 0.35, "blitz_rate": 0.15},
            league_avg={"sack_rate": 0.07, "pressure_proxy": 0.15, "blitz_rate": 0.26},
            league_std={"sack_rate": 0.0035, "pressure_proxy": 0.0074, "blitz_rate": 0.025},
        ),
        pass_defense_matchup=PassDefenseMatchupConstants(
            decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
            weights={"epa_dropback": 0.3, "pass_success": 0.25, "completion_pct": 0.15,
                     "nya": 0.15, "explosive_pass": 0.15},
            score_baseline=50, points_per_sd=10,
            league_avg={"epa_dropback": -0.02, "pass_success": 0.44, "completion_pct": 0.64,
                        "nya": 5.63, "explosive_pass": 0.14},
            league_std={"epa_dropback": 0.028, "pass_success": 0.01,
                        "completion_pct": 0.0095, "nya": 0.18, "explosive_pass": 0.006},
        ),
        run_defense_matchup=RunDefenseMatchupConstants(
            decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
            weights={"epa_rush": 0.3, "run_success": 0.25, "ypc": 0.2, "explosive_run": 0.15,
                     "stuff_rate": 0.1},
            score_baseline=50, points_per_sd=10,
            league_avg={"epa_rush": -0.04, "run_success": 0.41, "ypc": 4.37,
                        "explosive_run": 0.11, "stuff_rate": 0.175},
            league_std={"epa_rush": 0.016, "run_success": 0.0085, "ypc": 0.11,
                        "explosive_run": 0.007, "stuff_rate": 0.0082},
        ),
        rb_index=RBIndexConstants(
            decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
            blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
            weights={"rushing_epa": 0.25, "rushing_sr": 0.2, "ypc": 0.15, "ryoe": 0.2,
                     "rz_share": 0.0},
            score_baseline=50, points_per_sd=10,
            league_avg={"rushing_epa": 0.0, "rushing_sr": 0.42, "ypc": 4.2, "ryoe": 0.0,
                        "rz_share": 0.0},
            league_std={"rushing_epa": 0.08, "rushing_sr": 0.05, "ypc": 0.5, "ryoe": 0.5,
                        "rz_share": 1.0},
        ),
        qb_environment_model=QBEnvironmentModelConstants(
            decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
            league_avg={"success": 0.40, "explosive": 0.13, "sack": 0.12},
            league_std={"success": 0.05, "explosive": 0.015, "sack": 0.048},
            success_weight=0.15, explosive_weight=0.15, epa_weight=0.5, cpoe_weight=0.3,
            anya_weight=0.2, score_baseline=50, points_per_sd=10, new_team_penalty=1,
            recently_injured_penalty=1,
        ),
        explosive_play_matchup=ExplosivePlayMatchupConstants(
            decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
            league_avg_pass_off=0.143, league_std_pass_off=0.0088,
            league_avg_run_off=0.112, league_std_run_off=0.007,
            league_avg_deep_pass_allowed=0.358, league_std_deep_pass_allowed=0.018,
            league_avg_yac_allowed=5.21, league_std_yac_allowed=0.137,
            pass_prevention_w_explosive_pass_allowed=0.5,
            pass_prevention_w_deep_pass_allowed=0.3, pass_prevention_w_yac_allowed=0.2,
        ),
        flat_hfa=1.5, pass_matchup_conversion=0.08, run_matchup_conversion=0.06,
        ol_pressure_conversion=0.05, ol_modifier_scaling=0.25, weather_modifier_scaling=0.5,
        road_fatigue_threshold=3, road_fatigue_penalty=-1.0, qb_replacement_conversion=0.3,
    )


def main(season: int, week: int) -> None:
    print(f"Fetching real data for season {season - 3}-{season}...")
    pbp_3yr = fetch_pbp([season - 3, season - 2, season - 1])
    pbp_current = fetch_pbp([season])
    sched_current = fetch_schedules([season])
    sched_3yr = fetch_schedules([season - 3, season - 2, season - 1])
    pfr_pass = fetch_pfr_pass([season - 3, season - 2, season - 1])
    pfr_rush = fetch_pfr_rush([season - 3, season - 2, season - 1])
    ftn = fetch_ftn([season - 3, season - 2, season - 1])
    ngs_rushing_3yr = fetch_ngs_rushing([season - 3, season - 2, season - 1])
    ngs_rushing_current = fetch_ngs_rushing([season])
    print("fetched.")

    week_games = sched_current[
        (sched_current["season"] == season) & (sched_current["week"] == week)
        & (sched_current["game_type"] == "REG")
    ].sort_values("game_id")
    if week_games.empty:
        raise ValueError(f"No real REG games found for season={season} week={week}")
    first_game = week_games.iloc[0]
    home_abbr, away_abbr = first_game["home_team"], first_game["away_team"]
    home_team, away_team = TEAM_NAMES[home_abbr], TEAM_NAMES[away_abbr]
    print(f"Target real game: {away_team} @ {home_team} (season {season} week {week})")
    if pd.notna(first_game.get("home_score")):
        print(f"  Real actual result: away {first_game['away_score']}, "
              f"home {first_game['home_score']}")

    bundle = HistoricalGameDataBundle(
        pbp_3yr_prior=pbp_3yr, pbp_current_season=pbp_current,
        sched_current_season=sched_current, sched_3yr_prior=sched_3yr,
        pfr_pass_3yr=pfr_pass, pfr_rush_3yr=pfr_rush, ftn_3yr=ftn,
        ngs_rushing_3yr_prior=ngs_rushing_3yr, ngs_rushing_current=ngs_rushing_current,
    )
    constants = _build_constants()

    home_score, away_score = resolve_historical_model_home_away_score(
        bundle, constants, season, week, home_team, home_abbr, away_team, away_abbr,
    )
    print()
    print(f"Real walk-forward Model Score: {home_team} {home_score:.2f} - "
          f"{away_team} {away_score:.2f}")
    print(f"Real margin (home-away): {home_score - away_score:+.2f}")


if __name__ == "__main__":
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    week = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    main(season, week)
