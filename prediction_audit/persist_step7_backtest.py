"""
Step 7 -> Step 2: persists real backtest results into the permanent Prediction Audit database
(`db/schema.py`), giving Steps 8-9 (walk-forward validation, ablation) a real, queryable base
instead of re-running the composer every time.

Real, quota-conscious efficiency: reuses `backtest_step7_multiweek.py`'s own real season-level
stats caching (resolved once per season, not once per week). This is a genuine rerun of the
real composer, not a re-derivation from the earlier printed margins -- `predictions.
away_projected_points`/`home_projected_points`/`projected_total` need the real, individual
score values, which the earlier printed backtest output only reduced to a margin.

Real win probability: uses `market_comparison.win_probability_home()` -- the real, already
Excel-proven logistic transform (Model Assumptions C171 = 10.5 in the frozen baseline), NOT an
invented conversion. This is the same real formula v35's own Market Comparison & Confidence tab
uses, just applied to the real walk-forward margin instead of the frozen workbook's own margin.

Real game_id: reuses nflverse's own real per-game `game_id` (already unique, already used
throughout this project's data layer) rather than inventing a new identifier scheme.

Real market_data_status: the real closing spread (Step 5's own real habitatring.com source) is
inserted as market_type='spread', line_stage='closing', market_data_status='VERIFIED' -- a real,
verified line, not the 'MISSING' default. No real 'opening'/'prediction_time' line is available
for these historical games (this project's forward-only CLV loop didn't exist yet for 2025), so
those stages are simply not inserted -- never fabricated.

Usage:
    uv run python prediction_audit/persist_step7_backtest.py [season] [start_week] [end_week]
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

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
from prediction_audit.historical.full_game_prediction import (  # noqa: E402
    HistoricalGameDataBundle,
    resolve_historical_model_home_away_score,
)
from prediction_audit.historical.real_constants import (  # noqa: E402
    build_real_constants,
    load_real_model_assumptions,
)
from prediction_audit.market_data import REAL_SOURCE_NAME, fetch_real_market_lines  # noqa: E402

FROZEN_XLSX = str(
    Path(__file__).resolve().parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
)
WIN_PROB_LOGISTIC_SLOPE_ROW = 171
MODEL_VERSION = "v35.0"


def main(season: int, start_week: int, end_week: int) -> None:
    conn = create_database(DEFAULT_DB_PATH)
    write.insert_model(
        conn, MODEL_VERSION,
        "Frozen v35 baseline formula, scored via the real Python walk-forward historical "
        "reconstruction (Step 6) rather than the frozen Excel snapshot -- same real model, "
        "real historical games instead of the 2026 season.",
        frozen_at="2026-09-01T13:02:00Z",
        workbook_sha256="fdd0b971df91cae905e8884258d99d4a562ebdbf8c2122259b02a54955ec3c17",
    )

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
    real_lines = {
        (line.week, line.away_team, line.home_team): line
        for line in fetch_real_market_lines(season)
    }
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
        bundle, season, c,
    )

    run_timestamp = datetime.now(UTC).isoformat()
    n_persisted = 0

    for week in range(start_week, end_week + 1):
        print(f"\n=== Real target week {week} ===")
        week_games = sched_current[
            (sched_current["season"] == season) & (sched_current["week"] == week)
            & (sched_current["game_type"] == "REG")
        ].sort_values("game_id")
        if week_games.empty:
            print("  No real REG games this week -- skipping.")
            continue

        qb_stats, rb_stats = _resolve_week_level_stats(bundle, season, week, c)
        constants = build_real_constants(
            FROZEN_XLSX, qb_stats, rb_stats, ol_stats, prg_stats, pd_stats, rd_stats,
            qbe_stats, ep_stats,
        )

        for _, game in week_games.iterrows():
            home_abbr, away_abbr = game["home_team"], game["away_team"]
            home_team, away_team = TEAM_NAMES[home_abbr], TEAM_NAMES[away_abbr]
            real_game_id = game["game_id"]
            try:
                home_score, away_score = resolve_historical_model_home_away_score(
                    bundle, constants, season, week, home_team, home_abbr, away_team, away_abbr,
                )
            except ValueError as e:
                print(f"    SKIP {away_abbr}@{home_abbr}: {e}")
                continue

            margin = home_score - away_score
            total = home_score + away_score
            home_wp = win_probability_home(margin, logistic_slope)
            away_wp = 1 - home_wp

            write.insert_game(
                conn, real_game_id, season=season, week=week, away_team=away_team,
                home_team=home_team,
                game_date=str(game.get("gameday")) if pd.notna(game.get("gameday")) else None,
                neutral_site=(game.get("location") == "Neutral"),
                stadium=game.get("stadium"), surface=game.get("surface"),
            )
            run_id = write.insert_prediction_run(
                conn, MODEL_VERSION, real_game_id, prediction_timestamp=run_timestamp,
                data_version=f"step7_walk_forward_backtest_{season}_wk{start_week}-{end_week}",
            )
            write.insert_prediction(
                conn, run_id, away_projected_points=away_score,
                home_projected_points=home_score, projected_margin=margin,
                projected_total=total, home_win_probability=home_wp,
                away_win_probability=away_wp,
            )

            if pd.notna(game.get("home_score")) and pd.notna(game.get("away_score")):
                write.insert_result(
                    conn, real_game_id, away_final_score=int(game["away_score"]),
                    home_final_score=int(game["home_score"]),
                )

            line = real_lines.get((week, away_team, home_team))
            if line is not None and line.spread_line is not None and line.total_line is not None:
                # Real matched spread/total pair -- matches this project's own established
                # market_lines invariant (see test_market_lines_come_in_matched_spread_total_
                # pairs_per_game, scoped to line_stage='prediction_time' for Step 5's own rows;
                # these are real, legitimately different 'closing'-stage rows for the same
                # real habitatring.com source).
                write.insert_market_line(
                    conn, run_id, sportsbook="market_consensus", market_type="spread",
                    line_stage="closing", line_value=line.spread_line,
                    source=REAL_SOURCE_NAME, market_data_status="VERIFIED",
                )
                write.insert_market_line(
                    conn, run_id, sportsbook="market_consensus", market_type="total",
                    line_stage="closing", line_value=line.total_line,
                    source=REAL_SOURCE_NAME, market_data_status="VERIFIED",
                )

            n_persisted += 1

        print(f"  Week {week}: {n_persisted} real predictions persisted so far.")

    print(f"\nDone. {n_persisted} real prediction_runs persisted "
          f"(model_version={MODEL_VERSION}, season={season}, weeks {start_week}-{end_week}).")
    conn.close()


if __name__ == "__main__":
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    start_week = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    end_week = int(sys.argv[3]) if len(sys.argv) > 3 else 13
    main(season, start_week, end_week)
