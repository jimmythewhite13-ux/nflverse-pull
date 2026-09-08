"""
Daily refresh Job 1, step 3: real schedule confirmation. Reuses `nflverse_pull.pull.
fetch_schedules()` (the same real `import_schedules()` call every other script in this project
already uses). Detects a real CHANGE (flex, postponement) by comparing each real game's current
kickoff time against the most recent PRIOR real check for that same game_id -- not against a
fixed baseline, so a change is always measured relative to the last real observation.

Usage:
    uv run python -m prediction_audit.ingestion.schedule --season 2026
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
from prediction_audit.ingestion.log import SourceUnavailable, run_job  # noqa: E402

SOURCE = "nflverse (nfl_data_py.import_schedules)"


def _last_known_kickoff(conn: sqlite3.Connection, game_id: str) -> str | None:
    cur = conn.execute(
        "SELECT kickoff_time FROM raw_schedule_checks WHERE game_id = ? "
        "ORDER BY checked_at DESC LIMIT 1",
        (game_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _write(conn: sqlite3.Connection, ingestion_id: int, season: int) -> int:
    sched = fetch_schedules([season])
    sched = sched[sched["game_type"] == "REG"]
    if sched is None or sched.empty:
        raise SourceUnavailable(
            f"Real fetch_schedules([{season}]) returned no real REG rows -- genuinely "
            f"unavailable right now."
        )
    checked_at = datetime.now(UTC).isoformat()
    n = 0
    for _, row in sched.iterrows():
        gameday = row.get("gameday")
        gametime = row.get("gametime")
        if pd_notna(gameday) and pd_notna(gametime):
            kickoff_time = f"{gameday}T{gametime}:00"
        elif pd_notna(gameday):
            kickoff_time = f"{gameday}T00:00:00"
        else:
            kickoff_time = None

        prior = _last_known_kickoff(conn, row["game_id"])
        change_detected = 1 if prior is not None and kickoff_time != prior else 0
        change_detail = (
            f"kickoff moved: {prior!r} -> {kickoff_time!r}" if change_detected else None
        )
        conn.execute(
            "INSERT INTO raw_schedule_checks (ingestion_id, game_id, season, week, "
            "home_team, away_team, kickoff_time, change_detected, change_detail, "
            "checked_at, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ingestion_id, row["game_id"], season, int(row["week"]), row["home_team"],
             row["away_team"], kickoff_time, change_detected, change_detail, checked_at,
             SOURCE),
        )
        n += 1
    conn.commit()
    return n


def pd_notna(v) -> bool:
    return v is not None and v == v and v != ""


def main(season: int) -> dict:
    result = run_job("schedule", SOURCE, lambda conn, iid: _write(conn, iid, season))
    print(f"schedule job: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    main(args.season)
