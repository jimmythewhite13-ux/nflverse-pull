"""
Phase 1 -- Multi-Season Baseline, real scope decision (2026-09-06): full 22-input reconstruction
for season 2025 only. OL Index's own real FTN-coverage constraint (FTN_MIN_SEASON=2022) means
the full composer needs target_season - 3 >= 2022, i.e. target_season >= 2025 -- 2019-2024
cannot run the real, complete 22-input model without fabricating OL/pass-rush data that does not
exist for those years. Documented as a real, structural gap, not filled with a lesser model, per
the user's own explicit choice.

Extends persist_step7_backtest.py's already-proven pattern with everything Phase 1 additionally
requires:
  - Every one of the 22 real model inputs per game (via resolve_historical_model_components(),
    already built for Step 9's ablation -- no new resolver logic, just persisting what it
    already returns), not just the final aggregate score.
  - Real kickoff timestamp (gameday+gametime combined into one real ISO8601 value).
  - Real opening AND closing market lines (opening_lines_2025.csv, from
    extract_opening_lines_2025.py -- 258 of 272 real games matched to a real opening line; the
    other 14, all real Week 5 games, are a real, honest gap where the two sources' dates differ
    by more than the 1-day fallback tolerance, left blank rather than guessed).
  - A distinct data_version tag ("phase1_full_season_reconstruction_2025") so this run's own
    complete-season query never collides with the earlier, partial Step 7 backtest runs
    (weeks 10-18) already in the same database under their own real tags.

Real HFA verification (the prompt's own "critical" requirement): this Python reconstruction was
independently confirmed NOT to have the double-counting bug found in the live Excel formula --
see the turn immediately preceding this script for the real spot-check (3 real teams, net HFA
contribution == regressed_hfa/2 exactly, matching the mathematically correct, single-counted
construction `compute_model_home_away_score()` has always used).

Usage:
    uv run python prediction_audit/phase1_reconstruction_2025.py
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
from prediction_audit.engine.season_matchups import compute_model_home_away_score  # noqa: E402
from prediction_audit.historical.full_game_prediction import (  # noqa: E402
    HistoricalGameDataBundle,
    resolve_historical_model_components,
)
from prediction_audit.historical.real_constants import (  # noqa: E402
    build_real_constants,
    load_real_model_assumptions,
)
from prediction_audit.market_data import REAL_SOURCE_NAME  # noqa: E402

FROZEN_XLSX = str(
    Path(__file__).resolve().parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
)
OPENING_LINES_CSV = str(Path.home() / "Downloads" / "opening_lines_2025.csv")
WIN_PROB_LOGISTIC_SLOPE_ROW = 171
MODEL_VERSION = "v35.0"
SEASON = 2025
DATA_VERSION = f"phase1_full_season_reconstruction_{SEASON}"


def main() -> None:
    conn = create_database(DEFAULT_DB_PATH)
    write.insert_model(
        conn, MODEL_VERSION,
        "Frozen v35 baseline formula (post RB Value Index range fix + HFA row-3 gap + HFA "
        "double-count fix, tagged v35-audit-passed-hfa-fix), scored via the real Python "
        "walk-forward historical reconstruction (Step 6) -- Phase 1 full-season run.",
        frozen_at="2026-09-06T00:00:00Z",
        workbook_sha256="ac54ed4b893a0aae818a5419496e2e69fe60614afee92dea40e8a4585acdcb7d",
    )

    print(f"Fetching real data for season {SEASON - 3}-{SEASON}...")
    pbp_3yr = fetch_pbp([SEASON - 3, SEASON - 2, SEASON - 1])
    pbp_current = fetch_pbp([SEASON])
    sched_current = fetch_schedules([SEASON])
    sched_3yr = fetch_schedules([SEASON - 3, SEASON - 2, SEASON - 1])
    pfr_pass = fetch_pfr_pass([SEASON - 3, SEASON - 2, SEASON - 1])
    pfr_rush = fetch_pfr_rush([SEASON - 3, SEASON - 2, SEASON - 1])
    ftn = fetch_ftn([SEASON - 3, SEASON - 2, SEASON - 1])
    ngs_rushing_3yr = fetch_ngs_rushing([SEASON - 3, SEASON - 2, SEASON - 1])
    ngs_rushing_current = fetch_ngs_rushing([SEASON])
    opening_lines = pd.read_csv(OPENING_LINES_CSV)
    opening_by_game = {row["game_id"]: row for _, row in opening_lines.iterrows()}
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
    per_season_counts: dict[int, int] = {}
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
            # Real, structural walk-forward gap: this early in the season, there is no real
            # prior current-season data to determine real Starter/Backup roles from (e.g. week
            # 1 has zero real current-season games played yet). Documented, not fabricated
            # around -- every prior backtest this session started at week 10, so this real
            # constraint was never actually hit before Phase 1.
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

            # Real kickoff timestamp -- gameday + gametime combined, real ISO8601. Falls back
            # to date-only (no real time-of-day) if gametime is genuinely absent for this row.
            gameday = game.get("gameday")
            gametime = game.get("gametime")
            if pd.notna(gameday) and pd.notna(gametime):
                kickoff_iso = f"{gameday}T{gametime}:00"
            elif pd.notna(gameday):
                kickoff_iso = f"{gameday}T00:00:00"
            else:
                kickoff_iso = None

            write.insert_game(
                conn, real_game_id, season=SEASON, week=week, away_team=away_team,
                home_team=home_team,
                game_date=str(gameday) if pd.notna(gameday) else None,
                neutral_site=(game.get("location") == "Neutral"),
                stadium=game.get("stadium"), surface=game.get("surface"),
            )
            # Real data cutoff: the walk-forward resolvers' own guarantee is that no data
            # dated on/after kickoff is ever used -- the real cutoff IS the kickoff timestamp
            # itself, not a separate, independently-tracked value.
            run_id = write.insert_prediction_run(
                conn, MODEL_VERSION, real_game_id, prediction_timestamp=run_timestamp,
                data_cutoff_timestamp=kickoff_iso, data_version=DATA_VERSION,
            )
            write.insert_prediction(
                conn, run_id, away_projected_points=away_score,
                home_projected_points=home_score, projected_margin=margin,
                projected_total=total, home_win_probability=home_wp,
                away_win_probability=away_wp,
            )

            # Real, full 22-input breakdown -- every named term compute_model_home_away_score()
            # summed, individually persisted (not just the final aggregate).
            contributions = []
            for name, value in components.items():
                side = "HOME" if name.endswith("_home") else (
                    "AWAY" if name.endswith("_away") else "SHARED"
                )
                contributions.append(
                    {"component_name": name, "contribution_value": float(value), "side": side},
                )
            write.insert_component_contributions(conn, run_id, contributions)

            if pd.notna(game.get("home_score")) and pd.notna(game.get("away_score")):
                write.insert_result(
                    conn, real_game_id, away_final_score=int(game["away_score"]),
                    home_final_score=int(game["home_score"]),
                )

            # Real closing lines -- nflverse's own real spread_line/total_line, same real
            # source/convention already used by every prior Step 7 backtest.
            if pd.notna(game.get("spread_line")) and pd.notna(game.get("total_line")):
                write.insert_market_line(
                    conn, run_id, sportsbook="market_consensus", market_type="spread",
                    line_stage="closing", line_value=float(game["spread_line"]),
                    source=REAL_SOURCE_NAME, market_data_status="VERIFIED",
                )
                write.insert_market_line(
                    conn, run_id, sportsbook="market_consensus", market_type="total",
                    line_stage="closing", line_value=float(game["total_line"]),
                    source=REAL_SOURCE_NAME, market_data_status="VERIFIED",
                )

            # Real opening lines -- aussportsbetting.com (bet365/betr), where matched.
            opening_row = opening_by_game.get(real_game_id)
            if opening_row is not None and pd.notna(opening_row.get("open_home_point_spread")):
                # Real sign convention reconciliation: opening_lines_2025.csv's own
                # open_home_point_spread uses standard sportsbook display (negative=favorite,
                # per Sample_2025's own real convention, verified this session); nflverse's own
                # spread_line convention is the opposite (positive=home favored). Flip here so
                # every real market_lines row in this DB shares nflverse's own convention.
                write.insert_market_line(
                    conn, run_id, sportsbook="aussportsbetting_consensus", market_type="spread",
                    line_stage="opening",
                    line_value=-float(opening_row["open_home_point_spread"]),
                    source="aussportsbetting.com (bet365/betr)", market_data_status="VERIFIED",
                )
            if opening_row is not None and pd.notna(opening_row.get("open_over_under")):
                write.insert_market_line(
                    conn, run_id, sportsbook="aussportsbetting_consensus", market_type="total",
                    line_stage="opening", line_value=float(opening_row["open_over_under"]),
                    source="aussportsbetting.com (bet365/betr)", market_data_status="VERIFIED",
                )

            n_persisted += 1
            per_season_counts[SEASON] = per_season_counts.get(SEASON, 0) + 1

        print(f"  Week {week}: {n_persisted} real predictions persisted so far.")

    print(f"\nDone. {n_persisted} real prediction_runs persisted "
          f"(model_version={MODEL_VERSION}, data_version={DATA_VERSION}).")
    print(f"Real per-season counts: {per_season_counts} "
          f"(expected: {{{SEASON}: 272}} -- 272 real REG games).")
    if skipped_weeks:
        print(f"\nReal, structural gap -- {len(skipped_weeks)} week(s) skipped entirely "
              f"(no real current-season data yet to determine QB/RB roles from):")
        for week, reason in skipped_weeks:
            print(f"  Week {week}: {reason}")
    conn.close()


if __name__ == "__main__":
    main()
