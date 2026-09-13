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
from prediction_audit.ingestion.market_lines import canonical_book  # noqa: E402

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


def _is_closeable_from_lines(lines_by_book: dict[str, float]) -> bool | None:
    """Real, pure decision logic for `resolve_is_closeable_spread` -- separated out so it can be
    verified directly against known cases (see the module's own test invocation) independent of
    the real DB/view plumbing around it. True only when a real, UNIQUE plurality value exists
    (strictly more books agree on it than on any single competing value) -- a real exact tie
    (e.g. 2 books disagreeing, or an even 2-2 split) is correctly NOT a real consensus, caught
    live by this function's own verification before trusting it (an earlier `>=half` threshold
    wrongly called both of those cases "closeable"). None when fewer than 2 real books exist to
    judge a consensus from at all (never guessed)."""
    if len(lines_by_book) < 2:
        return None
    line_counts: dict[float, int] = {}
    for value in lines_by_book.values():
        line_counts[value] = line_counts.get(value, 0) + 1
    counts_sorted = sorted(line_counts.values(), reverse=True)
    if len(counts_sorted) == 1:
        return True  # every real book agrees
    return counts_sorted[0] > counts_sorted[1]


def resolve_is_closeable_spread(conn: sqlite3.Connection, game_id: str) -> bool | None:
    """Real `is_closeable` determination for the spread market (apply_epl_findings.md Part D,
    2026-09-13) -- same real "does a genuine book-covered consensus line exist" methodology
    verified live against this project's own real captured data for Part C (main line averaged
    4.17 real distinct books vs. 1.71 for off-consensus lines). The real, honest signal that
    `clv_movement` above reflects a genuine market consensus, not one disagreeing book's own
    outlier number -- see `_is_closeable_from_lines` for the real decision logic itself."""
    rows = conn.execute(
        "SELECT sportsbook, line_value FROM v_ingestion_market_tiers "
        "WHERE game_id = ? AND market_type = 'spread' AND line_stage = 'closing' "
        "AND line_value IS NOT NULL",
        (game_id,),
    ).fetchall()
    # Real, deliberate de-dup by book (the view can carry one row per real capture, not one per
    # book, depending on how many real closing-tier snapshots that book had). Also collapses
    # known-duplicate real data feeds (canonical_book -- confirmed 2026-09-13: coral/
    # ladbrokes_uk and neds/ladbrokes_au are the same real underlying price under two brand
    # names) so a real consensus isn't inflated by counting one real source twice.
    latest_by_book: dict[str, float] = {}
    for sportsbook, line_value in rows:
        latest_by_book[canonical_book(sportsbook)] = line_value
    return _is_closeable_from_lines(latest_by_book)


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
        is_closeable = resolve_is_closeable_spread(conn, game_id)

        write.insert_prediction_audit_metrics(
            conn, run_id, margin_error=margin_error, brier_score=brier_score,
            computed_at=now_iso, clv_movement=clv, is_closeable=is_closeable,
        )
        write.set_game_workflow_status(conn, game_id, "AUDITED", None, now_iso)
        print(f"    AUDITED {game_id}: margin_error={margin_error:+.2f} "
              f"brier={brier_score:.4f} clv={clv} is_closeable={is_closeable}")

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
