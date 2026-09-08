"""
Phase 13 -- production implementation of the Phase 10-selected, Phase 12-specified model
(v35 baseline, HFA Delta fixed at 0.0, everything else unchanged). Generalizes
`phase1_reconstruction_2025.py`'s already-proven real pipeline to any target season, with the
ONE production-code change Phase 12 specifies applied explicitly at a single, clearly-marked
point (`_apply_hfa_a_override`) -- nowhere else in this file deviates from the real, unmodified
resolvers this project has already validated.

Architecture (per phase10_11_12_13_selection_production.md):
    DATA INGESTION -> FEATURE ENGINE -> VALIDATED PREDICTION ENGINE -> PROBABILITY ENGINE
        -> CALIBRATION (none, by spec) -> MARKET/CLV -> AUDIT DATABASE

Every stage below reuses existing, already-tested code (Phase 12 Section 7) rather than
reimplementing it. Where the spec doesn't cover a choice, this script raises rather than
guessing (see `_apply_hfa_a_override`'s own docstring).

Usage:
    uv run python prediction_audit/production_pipeline_v35_hfa_a.py --season 2025
    uv run python prediction_audit/production_pipeline_v35_hfa_a.py --season 2026
"""
from __future__ import annotations

import argparse
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
WIN_PROB_LOGISTIC_SLOPE_ROW = 171
MODEL_VERSION = "v35.0-hfa-a-selected"  # Phase 10-selected candidate, not the raw v35 baseline
FTN_MIN_SEASON_FOR_FULL_OL_INDEX = 2025  # real, unchanged constraint -- see Phase 12 Section 4


def _apply_hfa_a_override(components: dict[str, float]) -> dict[str, float]:
    """The ONE production-code change Phase 12 specifies (Section 2): net home-field advantage
    fixed at 0.0, both sides, every game.

    Real correction (caught by this script's own 2025 consistency check, not assumed correct):
    `compute_model_home_away_score()` (season_matchups.py) sums `flat_hfa / 2` as a SEPARATE
    additive term from `hfa_delta_home`/`hfa_delta_away` (`+ flat_hfa/2` home, `- flat_hfa/2`
    away) -- confirmed by direct read of the real source, not the Phase 12 doc's own prior
    (WRONG) claim that flat_hfa "is not a separate additive term." Zeroing only
    hfa_delta_home/away leaves a residual +/-0.75 (flat_hfa/2, C3=1.5) home-field advantage in
    every game -- a real bug, now fixed here and in the Phase 12 spec doc. All three real keys
    must be zeroed to reach true "no HFA": `flat_hfa`, `hfa_delta_home`, `hfa_delta_away`.
    Every other one of the 22 real terms `resolve_historical_model_components()` returns is
    passed through completely unmodified -- this function does not touch, inspect, or recompute
    anything else."""
    components = dict(components)
    required = ("flat_hfa", "hfa_delta_home", "hfa_delta_away")
    missing = [k for k in required if k not in components]
    if missing:
        raise KeyError(
            f"resolve_historical_model_components() did not return {missing} -- the "
            f"production formula's real shape has changed since this spec was written "
            f"(Phase 12). Flagging rather than silently skipping the override."
        )
    components["flat_hfa"] = 0.0
    components["hfa_delta_home"] = 0.0
    components["hfa_delta_away"] = 0.0
    return components


def main(season: int, data_version: str | None = None) -> None:
    if season < FTN_MIN_SEASON_FOR_FULL_OL_INDEX:
        raise ValueError(
            f"Real, unchanged OL Index FTN-coverage constraint: season {season} needs "
            f"Y-3={season - 3} >= 2022 for the full 3-metric formula. This production pipeline "
            f"never substitutes a degraded path (that exists only in "
            f"research/ol_index_degraded_pre2025.py for Phase 8's secondary check) -- flagging "
            f"rather than silently degrading the real, selected production formula."
        )
    data_version = data_version or f"v35_hfa_a_production_{season}"

    conn = create_database(DEFAULT_DB_PATH)
    write.insert_model(
        conn, MODEL_VERSION,
        "Phase 10-selected, Phase 12-specified production model: v35 baseline with HFA Delta "
        "fixed at 0.0 (both sides), every other real term unchanged. See "
        "prediction_audit/phase_reports/phase12_final_specification.md.",
        frozen_at=datetime.now(UTC).isoformat(),
        workbook_sha256="ac54ed4b893a0aae818a5419496e2e69fe60614afee92dea40e8a4585acdcb7d",
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
    skipped_weeks: list[tuple[int, str]] = []

    for week in range(1, 19):
        print(f"\n=== Real target week {week} ===")
        week_games = sched_current[
            (sched_current["season"] == season) & (sched_current["week"] == week)
            & (sched_current["game_type"] == "REG")
        ].sort_values("game_id")
        if week_games.empty:
            print("  No real REG games this week -- skipping.")
            continue

        try:
            qb_stats, rb_stats = _resolve_week_level_stats(bundle, season, week, c)
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
                    bundle, constants, season, week, home_team, home_abbr, away_team, away_abbr,
                )
            except ValueError as e:
                print(f"    SKIP {away_abbr}@{home_abbr}: {e}")
                continue

            # ---- FEATURE ENGINE -> VALIDATED PREDICTION ENGINE boundary: the one real spec
            # override (Phase 12 Section 2) applied here, nowhere else. -----------------------
            components = _apply_hfa_a_override(components)
            home_score, away_score = compute_model_home_away_score(**components)

            margin = home_score - away_score
            total = home_score + away_score
            # ---- PROBABILITY ENGINE (unchanged, uncalibrated per Phase 12 Section 6) --------
            home_wp = win_probability_home(margin, logistic_slope)
            away_wp = 1 - home_wp
            # ---- CALIBRATION: none, by spec -- explicit no-op, not an oversight -------------

            gameday = game.get("gameday")
            gametime = game.get("gametime")
            if pd.notna(gameday) and pd.notna(gametime):
                kickoff_iso = f"{gameday}T{gametime}:00"
            elif pd.notna(gameday):
                kickoff_iso = f"{gameday}T00:00:00"
            else:
                kickoff_iso = None

            write.insert_game(
                conn, real_game_id, season=season, week=week, away_team=away_team,
                home_team=home_team,
                game_date=str(gameday) if pd.notna(gameday) else None,
                neutral_site=(game.get("location") == "Neutral"),
                stadium=game.get("stadium"), surface=game.get("surface"),
            )
            run_id = write.insert_prediction_run(
                conn, MODEL_VERSION, real_game_id, prediction_timestamp=run_timestamp,
                data_cutoff_timestamp=kickoff_iso, data_version=data_version,
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

            # ---- AUDIT DATABASE: real result + market/CLV, where available -----------------
            if pd.notna(game.get("home_score")) and pd.notna(game.get("away_score")):
                write.insert_result(
                    conn, real_game_id, away_final_score=int(game["away_score"]),
                    home_final_score=int(game["home_score"]),
                )
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

            n_persisted += 1

        print(f"  Week {week}: {n_persisted} real predictions persisted so far.")

    print(f"\nDone. {n_persisted} real prediction_runs persisted "
          f"(model_version={MODEL_VERSION}, data_version={data_version}).")
    if skipped_weeks:
        print(f"\nReal, structural gap -- {len(skipped_weeks)} week(s) skipped entirely "
              f"(no real current-season data yet to determine QB/RB roles from):")
        for week, reason in skipped_weeks:
            print(f"  Week {week}: {reason}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--data-version", type=str, default=None)
    args = parser.parse_args()
    main(args.season, args.data_version)
