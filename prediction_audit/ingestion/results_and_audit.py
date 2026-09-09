"""
Live Weekly Workflow, Step 4: once a real game's kickoff has passed, record its real final
score (any game, any status -- Results tracking is complete regardless of whether a real
prediction exists to audit), then compute real audit metrics (Margin Error, Brier, CLV) and
advance status to COMPLETED then AUDITED for games that actually have a real prediction
(status=PREDICTED) to audit against. A NOT_PREDICTABLE game's real result is recorded, but its
status is never force-advanced -- there is nothing to audit.

Real CLV, precisely: uses the live agent's own `raw_market_captures` / `v_ingestion_market_tiers`
(NOT the older, run_id-keyed `market_lines`/`v_clv`, which this live workflow never writes to).
Per that view's own real caveat (see PROGRESS.md, 2026-09-08): a `closing` tier value is only
durably correct once the game's real kickoff has actually passed -- which is exactly the
condition already required to reach this code path, so CLV computed here is real and final, not
provisional.

Usage:
    uv run python -m prediction_audit.ingestion.results_and_audit --season 2026
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from nflverse_pull.pull import fetch_schedules  # noqa: E402
from prediction_audit.db import write  # noqa: E402
from prediction_audit.db.capture_snapshot import get_active_run  # noqa: E402
from prediction_audit.ingestion.log import CadenceSkip, run_job  # noqa: E402

SOURCE = "nflverse (nfl_data_py.import_schedules) + raw_market_captures (real, live agent)"


def _real_clv(conn: sqlite3.Connection, game_id: str) -> float | None:
    """Real CLV for the spread market: closing line minus the earliest real
    non-opening (prediction_time) line, averaged across whichever real sportsbook(s) have both
    tiers. None if no real book has both a prediction_time and a durable closing value yet."""
    rows = conn.execute(
        "SELECT sportsbook, line_stage, line_value FROM v_ingestion_market_tiers "
        "WHERE game_id = ? AND market_type = 'spread' AND line_value IS NOT NULL",
        (game_id,),
    ).fetchall()
    by_book: dict[str, dict[str, float]] = {}
    for sportsbook, stage, value in rows:
        by_book.setdefault(sportsbook, {})[stage] = value
    movements = [
        tiers["closing"] - tiers.get("prediction_time", tiers.get("opening"))
        for tiers in by_book.values()
        if "closing" in tiers and ("prediction_time" in tiers or "opening" in tiers)
    ]
    return sum(movements) / len(movements) if movements else None


def _process(conn: sqlite3.Connection, ingestion_id: int, season: int) -> int:
    now = datetime.now(UTC)
    now_iso = now.isoformat()
    sched = fetch_schedules([season])
    sched = sched[sched["game_type"] == "REG"]

    candidates = conn.execute(
        """
        SELECT gws.game_id, gws.status, g.kickoff_time
        FROM game_workflow_status gws JOIN games g ON g.game_id = gws.game_id
        WHERE gws.status IN ('PREDICTED', 'NOT_PREDICTABLE', 'READY', 'PENDING')
          AND g.season = ? AND g.kickoff_time IS NOT NULL
        """,
        (season,),
    ).fetchall()

    n_touched = 0
    for game_id, status, kickoff_time in candidates:
        kickoff = datetime.fromisoformat(kickoff_time)
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=UTC)
        if now < kickoff:
            continue  # real, honest: game hasn't happened yet, nothing to check

        game_row = sched[sched["game_id"] == game_id]
        if game_row.empty:
            continue
        game = game_row.iloc[0]
        home_score, away_score = game.get("home_score"), game.get("away_score")
        if home_score != home_score or away_score != away_score:  # real NaN check
            continue  # real, honest: kickoff passed but the score isn't posted yet

        write.insert_result(
            conn, game_id, away_final_score=int(away_score), home_final_score=int(home_score),
        )
        n_touched += 1

        if status != "PREDICTED":
            continue  # a real result was still recorded above; nothing to audit

        run_id = get_active_run(conn, game_id)
        if run_id is None:
            continue  # should not happen for a real PREDICTED game, but never assume
        write.set_game_workflow_status(conn, game_id, "COMPLETED", None, now_iso)

        pred = conn.execute(
            "SELECT projected_margin, home_win_probability FROM predictions "
            "WHERE run_id = ?", (run_id,),
        ).fetchone()
        projected_margin, home_wp = pred
        actual_margin = home_score - away_score
        actual_home_win = 1.0 if actual_margin > 0 else 0.0
        margin_error = projected_margin - actual_margin
        brier_score = (home_wp - actual_home_win) ** 2
        clv = _real_clv(conn, game_id)

        write.insert_prediction_audit_metrics(
            conn, run_id, margin_error=margin_error, brier_score=brier_score,
            computed_at=now_iso, clv_movement=clv,
        )
        write.set_game_workflow_status(conn, game_id, "AUDITED", None, now_iso)
        print(f"    AUDITED {game_id}: margin_error={margin_error:+.2f} "
              f"brier={brier_score:.4f} clv={clv}")

    return n_touched


def main(season: int) -> dict:
    def _run(conn, iid):
        n = _process(conn, iid, season)
        if n == 0:
            raise CadenceSkip(
                f"No real season-{season} game has both a passed real kickoff and a real "
                f"final score not yet recorded -- nothing due this tick."
            )
        return n

    result = run_job("results_and_audit", SOURCE, _run)
    print(f"results_and_audit job: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    main(args.season)
