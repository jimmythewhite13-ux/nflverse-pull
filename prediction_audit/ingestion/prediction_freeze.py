"""
Live Weekly Workflow, Step 3: freezes a real prediction for every real 2026 game whose real
48-hour-before-kickoff cutoff has just passed, once it's READY (Weeks 4+, real roster data
present -- see game_status.py).

Explicit scope boundary, per the governing task: this uses the CURRENT VALIDATED PRODUCTION
FORMULA ONLY -- v35 baseline, real team-specific HFA, exactly as frozen in
`frozen_baselines/NFL_Prediction_Model_v35.xlsx` (verified SHA-256-identical to the live
`NFL_Prediction_Model_HFA_fixed.xlsx`). `resolve_historical_model_components()` and
`compute_model_home_away_score()` are called completely UNMODIFIED -- no HFA-A override, no
Travel-G, no research candidate of any kind. If this ever needs a model change to work, this
script raises rather than silently reaching for a research variant (see `main()`'s own season
check, reused verbatim from `production_pipeline_v35_hfa_a.py`, which established this exact
same real refusal-over-guessing convention).

48-hour cutoff: no pre-existing real convention for this number was found anywhere else in the
codebase (checked before writing this) -- it is adopted here for the first time, exactly as the
governing task specified, not claimed to match something that already existed.

Usage:
    uv run python -m prediction_audit.ingestion.prediction_freeze --season 2026
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.oline_stats import fetch_ftn, fetch_pfr_pass, fetch_pfr_rush  # noqa: E402
from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from nflverse_pull.rb_stats import fetch_ngs_rushing  # noqa: E402
from prediction_audit.backtest_step7_multiweek import (  # noqa: E402
    _resolve_season_level_stats,
    _resolve_week_level_stats,
)
from prediction_audit.db import write  # noqa: E402
from prediction_audit.db.capture_snapshot import capture_snapshot, get_active_run  # noqa: E402
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
from prediction_audit.ingestion.log import CadenceSkip, run_job  # noqa: E402

FROZEN_XLSX = str(
    Path(__file__).resolve().parent.parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
)
WIN_PROB_LOGISTIC_SLOPE_ROW = 171
MODEL_VERSION = "v35.0-live-production"  # the real, unmodified champion -- NOT HFA-A
FTN_MIN_SEASON_FOR_FULL_OL_INDEX = 2025
PREDICTION_CUTOFF_HOURS_BEFORE_KICKOFF = 48
SOURCE = "derived (internal -- real, unmodified v35 champion formula)"


def _due_games(conn: sqlite3.Connection, season: int, now: datetime) -> list[tuple[str, int]]:
    """Real, cheap pre-check -- (game_id, week) for every READY game whose real cutoff has
    passed and which has no ACTIVE prediction yet. Runs before any expensive real data fetch,
    so a scheduled tick with nothing due does no real network I/O."""
    rows = conn.execute(
        """
        SELECT gws.game_id, g.week, g.kickoff_time
        FROM game_workflow_status gws
        JOIN games g ON g.game_id = gws.game_id
        WHERE gws.status = 'READY' AND g.season = ?
        """,
        (season,),
    ).fetchall()
    due = []
    for game_id, week, kickoff_time in rows:
        if not kickoff_time:
            continue
        kickoff = datetime.fromisoformat(kickoff_time.replace("Z", "+00:00"))
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=UTC)
        cutoff = kickoff - timedelta(hours=PREDICTION_CUTOFF_HOURS_BEFORE_KICKOFF)
        if now >= cutoff and get_active_run(conn, game_id) is None:
            due.append((game_id, week))
    return due


def _freeze(conn: sqlite3.Connection, ingestion_id: int, season: int) -> int:
    if season < FTN_MIN_SEASON_FOR_FULL_OL_INDEX:
        raise ValueError(
            f"Real, unchanged OL Index FTN-coverage constraint: season {season} needs "
            f"Y-3={season - 3} >= 2022. This script never substitutes a degraded formula for "
            f"live production -- flagging rather than silently degrading it."
        )
    now = datetime.now(UTC)
    due = _due_games(conn, season, now)
    if not due:
        # Real, healthy "nothing due" -- distinct from SourceUnavailable (which would mean a
        # real data source was unreachable). This is the expected, normal state most ticks.
        raise CadenceSkip(
            f"No real season-{season} game is currently READY, past its real "
            f"{PREDICTION_CUTOFF_HOURS_BEFORE_KICKOFF}h-before-kickoff cutoff, AND without an "
            f"ACTIVE prediction yet."
        )
    due_weeks = sorted({w for _, w in due})
    print(f"  {len(due)} real game(s) due across week(s) {due_weeks}: {[g for g, _ in due]}")

    print(f"  Fetching real data for season {season - 3}-{season}...")
    pbp_3yr = fetch_pbp([season - 3, season - 2, season - 1])
    pbp_current = fetch_pbp([season])
    sched_current = fetch_schedules([season])
    sched_3yr = fetch_schedules([season - 3, season - 2, season - 1])
    pfr_pass = fetch_pfr_pass([season - 3, season - 2, season - 1])
    pfr_rush = fetch_pfr_rush([season - 3, season - 2, season - 1])
    ftn = fetch_ftn([season - 3, season - 2, season - 1])
    ngs_rushing_3yr = fetch_ngs_rushing([season - 3, season - 2, season - 1])
    ngs_rushing_current = fetch_ngs_rushing([season])

    bundle = HistoricalGameDataBundle(
        pbp_3yr_prior=pbp_3yr, pbp_current_season=pbp_current,
        sched_current_season=sched_current, sched_3yr_prior=sched_3yr,
        pfr_pass_3yr=pfr_pass, pfr_rush_3yr=pfr_rush, ftn_3yr=ftn,
        ngs_rushing_3yr_prior=ngs_rushing_3yr, ngs_rushing_current=ngs_rushing_current,
    )
    c = load_real_model_assumptions(FROZEN_XLSX)
    logistic_slope = c[WIN_PROB_LOGISTIC_SLOPE_ROW]

    write.insert_model(
        conn, MODEL_VERSION,
        "Live production: the real, unmodified v35 champion formula (real team-specific HFA, "
        "no research candidate) -- frozen for real, live 2026 games via the scheduled "
        "prediction-freeze job.",
        frozen_at=datetime.now(UTC).isoformat(),
        # Real, updated 2026-09-09 after the real raw-HFA-estimator fix (PROGRESS.md's "Real
        # bug found and fixed" entry) -- this is the frozen baseline's real, CURRENT SHA-256,
        # tag v35-audit-passed-hfa-raw-estimator-fix.
        workbook_sha256="372e54548a2c5e978aa464c557230c8a8c3091b8fffcdea310563bfc341e4c23",
    )

    season_stats_cache = _resolve_season_level_stats(bundle, season, c)
    week_stats_cache: dict[int, tuple] = {}
    n_frozen = 0
    now_iso = now.isoformat()

    for game_id, week in due:
        if week not in week_stats_cache:
            try:
                week_stats_cache[week] = _resolve_week_level_stats(bundle, season, week, c)
            except ValueError as e:
                print(f"    SKIP week {week} entirely: real league-stats resolution failed "
                      f"-- {e}")
                week_stats_cache[week] = None
        if week_stats_cache[week] is None:
            continue
        qb_stats, rb_stats = week_stats_cache[week]
        ol_stats, prg_stats, pd_stats, rd_stats, qbe_stats, ep_stats = season_stats_cache
        constants = build_real_constants(
            FROZEN_XLSX, qb_stats, rb_stats, ol_stats, prg_stats, pd_stats, rd_stats,
            qbe_stats, ep_stats,
        )

        game_row = sched_current[sched_current["game_id"] == game_id]
        if game_row.empty:
            print(f"    SKIP {game_id}: not found in the real current schedule pull.")
            continue
        game = game_row.iloc[0]
        home_abbr, away_abbr = game["home_team"], game["away_team"]
        home_team, away_team = TEAM_NAMES[home_abbr], TEAM_NAMES[away_abbr]

        try:
            components = resolve_historical_model_components(
                bundle, constants, season, week, home_team, home_abbr, away_team, away_abbr,
            )
        except ValueError as e:
            print(f"    SKIP {game_id}: real component resolution failed -- {e}")
            continue

        # ---- The REAL, UNMODIFIED champion formula -- no override of any kind. -------------
        home_score, away_score = compute_model_home_away_score(**components)
        margin = home_score - away_score
        home_wp = win_probability_home(margin, logistic_slope)

        contributions = [
            {
                "component_name": name, "contribution_value": float(value),
                "side": "HOME" if name.endswith("_home")
                else ("AWAY" if name.endswith("_away") else "SHARED"),
            }
            for name, value in components.items()
        ]
        run_id = capture_snapshot(
            conn, MODEL_VERSION, game_id, now_iso,
            home_projected_points=home_score, away_projected_points=away_score,
            home_win_probability=home_wp, components=contributions,
            data_cutoff_timestamp=now_iso, data_version=f"live_production_{season}",
        )
        write.set_game_workflow_status(conn, game_id, "PREDICTED", None, now_iso)
        print(f"    FROZEN {game_id} (run_id={run_id}): home={home_score:.2f} "
              f"away={away_score:.2f} margin={margin:+.2f} home_wp={home_wp:.3f}")
        n_frozen += 1

    return n_frozen


def main(season: int) -> dict:
    result = run_job(
        "prediction_freeze", SOURCE, lambda conn, iid: _freeze(conn, iid, season),
    )
    print(f"prediction_freeze job: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    main(args.season)
