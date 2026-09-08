"""
Phase 8 secondary check -- real 2024 reconstruction, degraded-OL-Index path.

Real, user-confirmed scope (2026-09-07): 2024 cannot run the exact production 22-input formula
(OL Index's FTN-coverage constraint -- see `research/ol_index_degraded_pre2025.py`'s module
docstring for the full real trace proving this is safe). This script monkeypatches ONLY the two
OL Index resolver functions actually called during a real walk-forward run, for the duration of
this script's own process -- production code (`offensive_line_index_historical.py`) is untouched,
and this patch never applies to any target_season >= 2025 run since those are separate scripts
using separate Python processes.

Persisted under data_version="phase8_2024_secondary_check_degraded_olindex" -- a DISTINCT tag
from "phase1_full_season_reconstruction_2025" so nothing here can be confused with, or silently
mixed into, the real 2025 numbers already used for every Phase 2-10 decision. NOT usable as
Phase 11's untouched holdout (different formula fidelity than the literal selected model).

No market lines persisted -- Phase 8's matrix (MAE/RMSE/Win%/Brier/LL/ATS-dir) never needed them
(ATS-dir there is real-margin-direction agreement, not a spread comparison).

Usage:
    uv run python prediction_audit/phase8_2024_reconstruction.py
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import prediction_audit.backtest_step7_multiweek as b7  # noqa: E402
import prediction_audit.historical.ol_pressure_adj_historical as ol_pressure_mod  # noqa: E402
from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.oline_stats import fetch_ftn, fetch_pfr_pass, fetch_pfr_rush  # noqa: E402
from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from nflverse_pull.rb_stats import fetch_ngs_rushing  # noqa: E402
from prediction_audit.backtest_step7_multiweek import (  # noqa: E402
    _resolve_season_level_stats,
    _resolve_week_level_stats,
)
from prediction_audit.db import write  # noqa: E402
from prediction_audit.db.schema import DEFAULT_DB_PATH, create_database  # noqa: E402
from prediction_audit.engine.market_comparison import win_probability_home  # noqa: E402
from prediction_audit.engine.season_matchups import compute_model_home_away_score  # noqa: E402
from prediction_audit.historical.full_game_prediction import (  # noqa: E402
    HistoricalGameDataBundle,
    resolve_historical_model_components,
)
from prediction_audit.historical.real_constants import (  # noqa: E402
    build_real_constants,
    load_real_model_assumptions,
)
from prediction_audit.research.ol_index_degraded_pre2025 import (  # noqa: E402
    resolve_ol_index_history_degraded,
    resolve_ol_index_league_stats_degraded,
)

FROZEN_XLSX = str(
    Path(__file__).resolve().parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
)
WIN_PROB_LOGISTIC_SLOPE_ROW = 171
MODEL_VERSION = "v35.0-degraded-ol-2024-secondary-check"
SEASON = 2024
DATA_VERSION = "phase8_2024_secondary_check_degraded_olindex"


def _patched_history(pfr_pass_3yr, pfr_rush_3yr, pbp_3yr_prior, ftn_3yr, target_season, team):
    # Real signature match for ol_pressure_adj_historical's call site (5 real positional data
    # args + team) -- pbp_3yr_prior/ftn_3yr accepted but unused (real, not needed for the one
    # z-score this degraded path ever produces; see module docstring).
    return resolve_ol_index_history_degraded(pfr_pass_3yr, pfr_rush_3yr, target_season, team)


def _patched_league_stats(
    pfr_pass_3yr, pfr_rush_3yr, pbp_3yr_prior, ftn_3yr, target_season, constants,
):
    return resolve_ol_index_league_stats_degraded(
        pfr_pass_3yr, pfr_rush_3yr, target_season, constants,
    )


def main() -> None:
    # Real, scoped monkeypatch -- only these two module-level names, only in this process, only
    # for this one script. Documented in the module docstring above, not silent.
    ol_pressure_mod.resolve_ol_index_history = _patched_history
    b7.resolve_ol_index_league_stats = _patched_league_stats

    conn = create_database(DEFAULT_DB_PATH)
    write.insert_model(
        conn, MODEL_VERSION,
        "Real 2024 secondary check -- v35 baseline formula with OL Pressure Adj's own OL Index "
        "z-score computed via a degraded (PFR-only, no FTN) path since 2024 fails OL Index's "
        "real FTN-coverage constraint. NOT the production formula -- research/secondary-check "
        "only, not comparable 1:1 to the real 2025 Phase 1-10 numbers.",
        frozen_at=datetime.now(UTC).isoformat(),
        workbook_sha256="ac54ed4b893a0aae818a5419496e2e69fe60614afee92dea40e8a4585acdcb7d",
    )

    print(f"Fetching real data for season {SEASON - 3}-{SEASON}...")
    pbp_3yr = fetch_pbp([SEASON - 3, SEASON - 2, SEASON - 1])
    pbp_current = fetch_pbp([SEASON])
    sched_current = fetch_schedules([SEASON])
    sched_3yr = fetch_schedules([SEASON - 3, SEASON - 2, SEASON - 1])
    pfr_pass = fetch_pfr_pass([SEASON - 3, SEASON - 2, SEASON - 1])
    pfr_rush = fetch_pfr_rush([SEASON - 3, SEASON - 2, SEASON - 1])
    # Real, confirmed by tracing every consumer of `ftn_3yr` in the composer: every one of them
    # (effective_qb_rating_historical.py, phase_matchup_historical.py) routes into
    # `resolve_ol_pressure_diff`, which is monkeypatched above to the degraded path that never
    # reads ftn_3yr at all. So `bundle.ftn_3yr` is a dead parameter here -- fetch only the real
    # years FTN actually covers (2022+) within the 3yr-prior range, rather than crashing on the
    # real "Data not available before 2022" error for 2021.
    real_ftn_years = [y for y in (SEASON - 3, SEASON - 2, SEASON - 1) if y >= 2022]
    ftn = fetch_ftn(real_ftn_years) if real_ftn_years else fetch_ftn([2022])
    ngs_rushing_3yr = fetch_ngs_rushing([SEASON - 3, SEASON - 2, SEASON - 1])
    ngs_rushing_current = fetch_ngs_rushing([SEASON])
    print("fetched.")

    bundle = HistoricalGameDataBundle(
        pbp_3yr_prior=pbp_3yr, pbp_current_season=pbp_current,
        sched_current_season=sched_current, sched_3yr_prior=sched_3yr,
        pfr_pass_3yr=pfr_pass, pfr_rush_3yr=pfr_rush, ftn_3yr=ftn,
        ngs_rushing_3yr_prior=ngs_rushing_3yr, ngs_rushing_current=ngs_rushing_current,
    )
    c = load_real_model_assumptions(FROZEN_XLSX)
    logistic_slope = c[WIN_PROB_LOGISTIC_SLOPE_ROW]

    print("Resolving real season-level league stats (once, reused every target week)...")
    ol_stats, prg_stats, pd_stats, rd_stats, qbe_stats, ep_stats = _resolve_season_level_stats(
        bundle, SEASON, c,
    )

    run_timestamp = datetime.now(UTC).isoformat()
    n_persisted = 0
    skipped_weeks: list[tuple[int, str]] = []

    for week in range(1, 19):
        print(f"\n=== Real target week {week} ===")
        week_games = sched_current[
            (sched_current["season"] == SEASON) & (sched_current["week"] == week)
            & (sched_current["game_type"] == "REG")
        ].sort_values("game_id")
        if week_games.empty:
            print("  No real REG games this week -- skipping.")
            continue

        try:
            qb_stats, rb_stats = _resolve_week_level_stats(bundle, SEASON, week, c)
        except ValueError as e:
            print(f"  SKIP entire week {week}: real league-stats resolution failed -- {e}")
            skipped_weeks.append((week, str(e)))
            continue
        constants = build_real_constants(
            FROZEN_XLSX, qb_stats, rb_stats, ol_stats, prg_stats, pd_stats, rd_stats,
            qbe_stats, ep_stats,
        )

        for _, game in week_games.iterrows():
            home_abbr, away_abbr = game["home_team"], game["away_team"]
            home_team, away_team = TEAM_NAMES[home_abbr], TEAM_NAMES[away_abbr]
            real_game_id = game["game_id"]
            try:
                components = resolve_historical_model_components(
                    bundle, constants, SEASON, week, home_team, home_abbr, away_team, away_abbr,
                )
            except ValueError as e:
                print(f"    SKIP {away_abbr}@{home_abbr}: {e}")
                continue
            home_score, away_score = compute_model_home_away_score(**components)

            margin = home_score - away_score
            total = home_score + away_score
            home_wp = win_probability_home(margin, logistic_slope)
            away_wp = 1 - home_wp

            gameday = game.get("gameday")
            write.insert_game(
                conn, real_game_id, season=SEASON, week=week, away_team=away_team,
                home_team=home_team,
                game_date=str(gameday) if gameday == gameday else None,  # NaN-safe
                neutral_site=(game.get("location") == "Neutral"),
                stadium=game.get("stadium"), surface=game.get("surface"),
            )
            run_id = write.insert_prediction_run(
                conn, MODEL_VERSION, real_game_id, prediction_timestamp=run_timestamp,
                data_cutoff_timestamp=None, data_version=DATA_VERSION,
            )
            write.insert_prediction(
                conn, run_id, away_projected_points=away_score,
                home_projected_points=home_score, projected_margin=margin,
                projected_total=total, home_win_probability=home_wp,
                away_win_probability=away_wp,
            )

            contributions = [
                {
                    "component_name": name, "contribution_value": float(value),
                    "side": "HOME" if name.endswith("_home")
                    else ("AWAY" if name.endswith("_away") else "SHARED"),
                }
                for name, value in components.items()
            ]
            write.insert_component_contributions(conn, run_id, contributions)

            if game.get("home_score") == game.get("home_score") and \
                    game.get("away_score") == game.get("away_score"):  # NaN-safe
                write.insert_result(
                    conn, real_game_id, away_final_score=int(game["away_score"]),
                    home_final_score=int(game["home_score"]),
                )

            n_persisted += 1

        print(f"  Week {week}: {n_persisted} real predictions persisted so far.")

    print(f"\nDone. {n_persisted} real prediction_runs persisted "
          f"(model_version={MODEL_VERSION}, data_version={DATA_VERSION}).")
    if skipped_weeks:
        print("\nReal, structural gap (same as 2025 -- weeks with no current-season data yet):")
        for week, reason in skipped_weeks:
            print(f"  Week {week}: {reason}")
    conn.close()


if __name__ == "__main__":
    main()
