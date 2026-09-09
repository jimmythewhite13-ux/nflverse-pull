"""
Live Weekly Workflow, Step 2: real per-game workflow status for every 2026 REG game.

Weeks 1-3 (any season): a real, structural fact already established elsewhere in this project
(Phase 1's own real skip, hit every time -- `resolve_qb_index_league_stats()` raises when no
current-season QB data exists yet) -- these games are marked NOT_PREDICTABLE, never silently
skipped, and never force-predicted.

Weeks 4+: READY once real roster data exists for the season (the daily-refresh agent already
guarantees this). Status transitions are monotonic-safe -- this job NEVER downgrades a game
that has already progressed past READY (PREDICTED/COMPLETED/AUDITED) back down on a routine
re-run; it only sets PENDING/READY/NOT_PREDICTABLE for games not yet at or past READY.

Usage:
    uv run python -m prediction_audit.ingestion.game_status --season 2026
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from prediction_audit.db import write  # noqa: E402
from prediction_audit.ingestion.log import SourceUnavailable, run_job  # noqa: E402

SOURCE = "derived (internal -- real Weeks 1-3 structural rule + real roster-data presence)"
FIRST_PREDICTABLE_WEEK = 3  # weeks <= this are NOT_PREDICTABLE -- see module docstring
NOT_PREDICTABLE_REASON = (
    "Real, structural fact (not a bug, not a data gap): current-season QB/RB roles cannot be "
    "resolved walk-forward this early in the season -- no prior current-season data exists yet "
    "to determine them from. Confirmed by resolve_qb_index_league_stats() raising for these "
    "weeks in every real reconstruction this project has ever run (Phase 1, the 2024 secondary "
    "check, and every real production run)."
)

# A game already at or past this point in its real lifecycle is never downgraded by this job.
_ADVANCED_STATUSES = {"PREDICTED", "COMPLETED", "AUDITED"}


def _current_status(conn: sqlite3.Connection, game_id: str) -> str | None:
    row = conn.execute(
        "SELECT status FROM game_workflow_status WHERE game_id = ?", (game_id,),
    ).fetchone()
    return row[0] if row else None


def _has_real_roster_data(conn: sqlite3.Connection, season: int, team: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM raw_roster_snapshots WHERE season = ? AND team = ? LIMIT 1",
        (season, team),
    ).fetchone()
    return row is not None


def _write(conn: sqlite3.Connection, ingestion_id: int, season: int) -> int:
    sched = fetch_schedules([season])
    sched = sched[sched["game_type"] == "REG"]
    if sched is None or sched.empty:
        raise SourceUnavailable(
            f"Real fetch_schedules([{season}]) returned no real REG rows -- genuinely "
            f"unavailable right now."
        )
    now = datetime.now(UTC).isoformat()
    n = 0
    for _, row in sched.iterrows():
        game_id = row["game_id"]
        week = int(row["week"])
        gameday = row.get("gameday")
        gametime = row.get("gametime")
        kickoff_time = None
        if isinstance(gameday, str) and isinstance(gametime, str):
            kickoff_time = f"{gameday}T{gametime}:00"
        elif isinstance(gameday, str):
            kickoff_time = f"{gameday}T00:00:00"
        # Real FK requirement: game_workflow_status.game_id REFERENCES games(game_id) -- the
        # daily-refresh agent's raw_schedule_checks is deliberately NOT tied to `games` (see
        # schema.py's own note on why), so a real 2026 row must be inserted here first, same
        # convention every historical reconstruction script already uses.
        write.insert_game(
            conn, game_id, season=season, week=week, away_team=row["away_team"],
            home_team=row["home_team"], game_date=gameday if isinstance(gameday, str) else None,
            kickoff_time=kickoff_time,
        )
        current = _current_status(conn, game_id)
        if current in _ADVANCED_STATUSES:
            continue  # real, deliberate: never downgrade a game past READY

        if week <= FIRST_PREDICTABLE_WEEK:
            write.set_game_workflow_status(
                conn, game_id, "NOT_PREDICTABLE", NOT_PREDICTABLE_REASON, now,
            )
            n += 1
            continue

        # Real bug caught before shipping (same recurring class as Phase 4/7): fetch_schedules()
        # returns real ABBREVIATIONS ("BUF"), but raw_roster_snapshots.team stores real FULL
        # names ("Buffalo Bills") -- confirmed by direct query, not assumed. Convert here.
        home_full = TEAM_NAMES[row["home_team"]]
        away_full = TEAM_NAMES[row["away_team"]]
        home_ready = _has_real_roster_data(conn, season, home_full)
        away_ready = _has_real_roster_data(conn, season, away_full)
        if home_ready and away_ready:
            write.set_game_workflow_status(conn, game_id, "READY", None, now)
        else:
            missing = [t for t, ok in ((home_full, home_ready), (away_full, away_ready))
                       if not ok]
            write.set_game_workflow_status(
                conn, game_id, "PENDING",
                f"Real roster data not yet pulled for: {missing}", now,
            )
        n += 1
    return n


def main(season: int) -> dict:
    result = run_job("game_status", SOURCE, lambda conn, iid: _write(conn, iid, season))
    print(f"game_status job: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    main(args.season)
